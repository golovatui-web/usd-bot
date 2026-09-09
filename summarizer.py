"""
Генерація короткого висновку, опису та оцінки рівня доказовості для статті через Claude API.

ВАЖЛИВО щодо авторського права: модель отримує лише офіційну анотацію (abstract) статті
з PubMed і має ПЕРЕФРАЗУВАТИ її власними словами, а не копіювати. Повний текст статей
ніде не використовується. Кожна анотація в боті супроводжується посиланням на оригінал.

МОДЕЛЬ: гібридна двоетапна схема (вибір моделі — через .env, код міняти не потрібно).

  1) Кожна стаття СПОЧАТКУ обробляється швидкою/дешевою моделлю (типово Haiku 4.5).
     На цьому кроці Claude оцінює ДВА незалежні виміри статті:
       - evidence_level       — методологічна якість (дизайн дослідження: РКД/огляд/
                                 case report тощо). Формальна EBM-ієрархія. Показується
                                 читачам ЛИШЕ кольоровим гуртком (🟢🟡🔴).
       - practical_relevance  — чи змінює ця інформація дії лікаря УЗД-діагностики
                                 БЕЗПОСЕРЕДНЬО на прийомі (диф.-діагностичний критерій,
                                 порогове значення, пастка/артефакт, нова техніка
                                 сканування). НЕ те саме, що evidence_level: РКД може
                                 бути малокорисним для щоденної практики, а звичайний
                                 опис випадку — дуже корисним. Показується читачам
                                 бейджем "🩺" поряд із гуртком (див. bot.py).
  2) Якщо practical_relevance статті потрапляє у список UPGRADE_PRACTICAL_LEVELS
     (типово "High,Medium"), вона ДОДАТКОВО переобробляється якіснішою моделлю
     (типово Sonnet 5) — саме такі статті найбільше "виграють" від точнішого
     формулювання, бо їх реально застосують на прийомі.

  practical_relevance ЗБЕРІГАЄТЬСЯ в БД (див. db.py) і показується в каналі (bot.py).

Керування — виключно через змінні середовища (див. .env.example):
  SUMMARIZER_FAST_MODEL      — модель першого проходу      (типово: claude-haiku-4-5-20251001)
  SUMMARIZER_PREMIUM_MODEL   — модель "підвищення якості"  (типово: claude-sonnet-5)
  ENABLE_PREMIUM_UPGRADE     — "true"/"false"                (типово: true)
  UPGRADE_PRACTICAL_LEVELS   — рівні practical_relevance, що тригерять апгрейд
                               (типово: "High,Medium")
  UPGRADE_EVIDENCE_LEVELS    — рівні evidence_level, що ТАКОЖ тригерять апгрейд, якщо хочете
                               комбінувати обидва критерії через АБО (типово: вимкнено, "")

Шкала evidence_level — проста, власна (High / Medium / Low), а не формальна GRADE/Oxford CEBM.
  HIGH   — систематичні огляди, мета-аналізи, РКД, офіційні рекомендації асоціацій
  MEDIUM — проспективні когортні дослідження, великі ретроспективні серії з чіткою методологією
  LOW    — описи випадків, малі ретроспективні вибірки, пілотні дослідження, думка експертів

НАДІЙНІСТЬ: перший (fast) виклик робиться з 1 повторною спробою при тимчасовому збої
(мережа/API) — це найкритичніший виклик, він відбувається для КОЖНОЇ статті. Преміум-
виклик — без retry: якщо він не вдався, ми просто тихо лишаємо результат fast-моделі
(природний, безкоштовний fallback, повторювати немає сенсу). У ЖОДНОМУ разі сирий текст
винятку (стектрейс, JSON помилки API) не потрапляє в публічний канал — лише в консольний
лог (journalctl), користувачі бачать нейтральне повідомлення.
"""

import json
import os
import time

from anthropic import Anthropic

FAST_MODEL = os.environ.get("SUMMARIZER_FAST_MODEL", "claude-haiku-4-5-20251001")
PREMIUM_MODEL = os.environ.get("SUMMARIZER_PREMIUM_MODEL", "claude-sonnet-5")
ENABLE_PREMIUM_UPGRADE = os.environ.get("ENABLE_PREMIUM_UPGRADE", "true").strip().lower() == "true"
MAX_RETRIES = 2  # для fast-моделі: 1 повторна спроба при тимчасовому збої


def _parse_levels(env_value: str) -> set:
    return {lvl.strip().capitalize() for lvl in env_value.split(",") if lvl.strip()}


UPGRADE_PRACTICAL_LEVELS = _parse_levels(os.environ.get("UPGRADE_PRACTICAL_LEVELS", "High,Medium"))
UPGRADE_EVIDENCE_LEVELS = _parse_levels(os.environ.get("UPGRADE_EVIDENCE_LEVELS", ""))

SYSTEM_PROMPT = """Ти — асистент, який готує короткі анотації наукових статей з ультразвукової
діагностики (УЗД) для лікарів-практиків УЗД-діагностики в Україні. Це месенджер-дайджест,
не наукова стаття — будь МАКСИМАЛЬНО стислим.

Правила:
1. Пиши українською мовою, професійним, стислим стилем "лікар для лікаря".
2. НІКОЛИ не копіюй речення з анотації дослівно — формулюй власними словами.
3. Відповідай ЛИШЕ у форматі JSON, без жодного тексту до чи після, без markdown-огорожі.
4. "conclusion" — РІВНО 1 речення: найголовніший практичний висновок для лікаря УЗД (що це
   означає для щоденної практики). Це найважливіше поле в усій відповіді — має читатись за
   3 секунди і одразу давати зрозуміти, чи варто читати далі.
5. "description" — 2-3 речення: що саме досліджували, на якій вибірці/дизайні, і головний
   результат з конкретними цифрами (чутливість/специфічність/AUC/точність), якщо вони є
   в анотації.
6. "evidence_level" — лише одне з трьох значень: "High", "Medium", "Low". Оцінюй за дизайном
   дослідження, згаданим в анотації:
   - High: систематичний огляд, мета-аналіз, РКД (randomized controlled trial), офіційна
     рекомендація/консенсус асоціації.
   - Medium: проспективне когортне дослідження, велика ретроспективна серія з чіткою методологією.
   - Low: опис випадку/серія випадків, мала ретроспективна вибірка, пілотне дослідження,
     думка експертів, редакційна стаття, або якщо дизайн дослідження неможливо визначити.
7. "practical_relevance" — лише одне з трьох значень: "High", "Medium", "Low". ЦЕ НЕ ТЕ САМЕ,
   що evidence_level — тут оцінюй НЕ дизайн дослідження, а чи змінює ця інформація дії лікаря
   УЗД-діагностики БЕЗПОСЕРЕДНЬО під час прийому пацієнта:
   - High: стаття дає конкретний диференціально-діагностичний УЗД-критерій/патерн (як
     відрізнити схожі патології одна від одної), порогове чи референсне значення (напр.
     розмір/градація для скерування на біопсію), показники чутливості/специфічності/PPV/NPV,
     які впливають на рішення "робити пункцію чи спостерігати", опис типового артефакту чи
     пастки (false positive/negative), або нову/вдосконалену техніку сканування чи протокол —
     тобто те, що лікар реально застосує на наступному прийомі.
   - Medium: корисний контекст (епідеміологія, механізм, кореляція з клінічними даними),
     який розширює розуміння, але не змінює безпосередньо дії за апаратом сьогодні.
   - Low: переважно дослідницький інтерес (молекулярні/генетичні маркери без прямого
     УЗД-корелята, суто методологічна чи редакційна стаття, попередні/пілотні дані без
     готового практичного висновку для сонографіста).

Формат відповіді (валідний JSON, без пояснень):
{
  "conclusion": "1 речення — головний практичний висновок",
  "description": "2-3 речення — деталі дослідження",
  "evidence_level": "High" | "Medium" | "Low",
  "practical_relevance": "High" | "Medium" | "Low"
}
"""

_client = None


def _get_client() -> Anthropic:
    """Клієнт створюється лише один раз, при першому реальному зверненні (lazy) —
    працює незалежно від порядку імпортів/load_dotenv(), на відміну від eager-створення
    на рівні модуля."""
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def _generate(model: str, user_content: str) -> dict:
    """Один виклик Claude API. При будь-якій помилці (мережа, парсинг JSON тощо) —
    кидає виняток; обробка помилок винесена в _generate_with_retry / summarize_article."""
    response = _get_client().messages.create(
        model=model,
        max_tokens=400,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    raw_text = "".join(
        block.text for block in response.content if block.type == "text"
    ).strip()

    raw_text = raw_text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    parsed = json.loads(raw_text)

    level = parsed.get("evidence_level", "Low")
    if level not in ("High", "Medium", "Low"):
        level = "Low"

    practical = parsed.get("practical_relevance", "Low")
    if practical not in ("High", "Medium", "Low"):
        practical = "Low"

    return {
        "conclusion": parsed.get("conclusion", "Не вдалося сформувати висновок."),
        "description": parsed.get("description", ""),
        "evidence_level": level,
        "practical_relevance": practical,
    }


def _generate_with_retry(model: str, user_content: str) -> dict:
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            return _generate(model, user_content)
        except Exception as e:  # noqa: BLE001
            last_error = e
            if attempt < MAX_RETRIES - 1:
                time.sleep(2)
    raise last_error


def summarize_article(title: str, abstract: str, journal: str) -> dict:
    """Повертає dict {conclusion, description, evidence_level, practical_relevance}.

    Крок 1: завжди FAST_MODEL (з 1 повторною спробою), оцінює evidence_level і
    practical_relevance. Крок 2 (опційно): якщо practical_relevance (або, якщо
    налаштовано, evidence_level) потрапляє у список для апгрейду — повторний виклик
    PREMIUM_MODEL. Якщо преміум-виклик не вдався — тихо залишаємо результат fast-моделі.
    """
    user_content = (
        f"Назва статті: {title}\n"
        f"Журнал: {journal}\n"
        f"Офіційна анотація (abstract):\n{abstract}"
    )

    try:
        result = _generate_with_retry(FAST_MODEL, user_content)
    except Exception as e:  # noqa: BLE001 — навмисно широкий except для стабільності пайплайну
        # Сирий текст помилки НІКОЛИ не йде в публічний канал — лише в лог (journalctl).
        print(f"summarizer: остаточна помилка {FAST_MODEL} після {MAX_RETRIES} спроб — {e}")
        return {
            "conclusion": "⚠️ Не вдалося автоматично опрацювати цю статтю.",
            "description": "Технічна помилка при генерації анотації. Повний текст доступний за посиланням нижче.",
            "evidence_level": "Low",
            "practical_relevance": "Low",
        }

    should_upgrade = (
        ENABLE_PREMIUM_UPGRADE
        and PREMIUM_MODEL != FAST_MODEL
        and (
            result["practical_relevance"] in UPGRADE_PRACTICAL_LEVELS
            or result["evidence_level"] in UPGRADE_EVIDENCE_LEVELS
        )
    )

    if should_upgrade:
        try:
            premium_result = _generate(PREMIUM_MODEL, user_content)
            print(
                f"    ↳ practical_relevance={result['practical_relevance']}, "
                f"evidence={result['evidence_level']} → уточнено моделлю {PREMIUM_MODEL}"
            )
            return premium_result
        except Exception as e:  # noqa: BLE001
            print(f"    ↳ Підвищення якості не вдалося ({PREMIUM_MODEL}): {e}. "
                  f"Залишаю результат {FAST_MODEL}.")

    return result
