"""
Дворівнева генерація анотацій через Google Gemini API (google-genai SDK).

ВАЖЛИВО щодо авторського права: модель отримує лише офіційну анотацію (abstract)
з PubMed і має ПЕРЕФРАЗУВАТИ її власними словами. Повний текст статей ніде
не використовується. Кожна анотація супроводжується посиланням на оригінал.

Схема (Tier 1 + Tier 2):
  1) Кожна стаття СПОЧАТКУ обробляється gemini-2.5-flash (або SUMMARIZER_FAST_MODEL).
     Оцінюються ДВА незалежні виміри:
       - evidence_level      — методологічна якість (дизайн дослідження).
       - practical_relevance — чи змінює стаття дії лікаря УЗД на прийомі.
  2) Якщо practical_relevance у UPGRADE_PRACTICAL_LEVELS (типово High,Medium),
     стаття ДОДАТКОВО переобробляється gemini-2.5-pro — для чіткіших цифр,
     критеріїв і техніки сканування (бейдж 🩺 у каналі).

Structured Output: Pydantic DigestArticle передається як response_schema,
тому відповідь валідується SDK, а не парситься regex'ом.

НАДІЙНІСТЬ:
  - 429 Too Many Requests → tenacity, паузи 15 / 30 / 60 с.
  - Сирий текст винятку НІКОЛИ не потрапляє в канал — лише print() у лог.
  - Преміум-виклик без окремого retry-циклу: якщо впав — лишаємо результат Flash.
  - Клієнт лінивий (_get_client), щоб load_dotenv() встиг спрацювати до першого виклику.
"""

from __future__ import annotations

import os
import time
from typing import Literal

from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_chain, wait_fixed

FAST_MODEL = os.environ.get("SUMMARIZER_FAST_MODEL", "gemini-2.5-flash")
PREMIUM_MODEL = os.environ.get("SUMMARIZER_PREMIUM_MODEL", "gemini-2.5-pro")
ENABLE_PREMIUM_UPGRADE = os.environ.get("ENABLE_PREMIUM_UPGRADE", "true").strip().lower() == "true"
GEMINI_CALL_GAP_SECONDS = float(os.environ.get("GEMINI_CALL_GAP_SECONDS", "6"))
MAX_PREMIUM_PER_DAY = int(os.environ.get("MAX_PREMIUM_PER_DAY", "40"))


def _parse_levels(env_value: str) -> set[str]:
    return {lvl.strip().capitalize() for lvl in env_value.split(",") if lvl.strip()}


UPGRADE_PRACTICAL_LEVELS = _parse_levels(os.environ.get("UPGRADE_PRACTICAL_LEVELS", "High,Medium"))
UPGRADE_EVIDENCE_LEVELS = _parse_levels(os.environ.get("UPGRADE_EVIDENCE_LEVELS", ""))

Level = Literal["High", "Medium", "Low"]


class DigestArticle(BaseModel):
    title_ua: str = Field(description="Лаконічний переклад заголовка українською")
    summary_ua: str = Field(description="Структурована коротка анотація (3-5 речень)")
    evidence_level: Level
    evidence_justification: str = Field(
        description="Обґрунтування рівня доказовості на основі методології"
    )
    practical_relevance: Level
    clinical_takeaway: str = Field(
        description="Конкретна практична користь (якщо є) для лікаря на прийомі"
    )


SYSTEM_PROMPT = """Ти — асистент, який готує короткі анотації наукових статей з ультразвукової
діагностики (УЗД) для лікарів-практиків УЗД-діагностики в Україні. Це месенджер-дайджест,
не наукова стаття — будь МАКСИМАЛЬНО стислим.

Правила:
1. Пиши українською мовою, професійним, стислим стилем "лікар для лікаря".
2. НІКОЛИ не копіюй речення з анотації дослівно — формулюй власними словами.
3. "title_ua" — лаконічний переклад назви, без транслітерації абревіатур, які лікарі
   і так знають (TIRADS, CEUS, FNA, POCUS, AUC).
4. "summary_ua" — 3-5 речень: що досліджували, вибірка/дизайн, головний результат
   з конкретними цифрами (чутливість/специфічність/AUC/точність), якщо вони є в анотації.
5. "evidence_level" — лише High, Medium або Low. Оцінюй за дизайном дослідження:
   - High: систематичний огляд, мета-аналіз, РКД, офіційна рекомендація/консенсус.
   - Medium: проспективне когортне, велика ретроспективна серія з чіткою методологією.
   - Low: опис випадку, мала ретроспективна вибірка, пілот, думка експертів, або
     дизайн неможливо визначити.
6. "evidence_justification" — 1 коротке речення: чому саме цей рівень (назвати дизайн).
7. "practical_relevance" — НЕ те саме, що evidence_level. Оцінюй, чи змінює інформація
   дії лікаря УЗД БЕЗПОСЕРЕДНЬО під час прийому:
   - High: диф.-діагностичний УЗД-критерій/патерн, порогове значення для біопсії,
     чутливість/специфічність/PPV/NPV, що впливають на рішення, типовий артефакт/пастка,
     нова техніка сканування чи протокол.
   - Medium: корисний контекст (епідеміологія, кореляція), який не змінює дії сьогодні.
   - Low: дослідницький інтерес без готового висновку для сонографіста.
8. "clinical_takeaway" — РІВНО 1 речення: найголовніший практичний висновок. Має
   читатись за 3 секунди. Якщо practical_relevance = Low — все одно сформулюй,
   що саме стаття додає (навіть якщо це "не змінює протокол прийому").
"""

FALLBACK = DigestArticle(
    title_ua="Стаття (автообробка не вдалася)",
    summary_ua="Технічна помилка при генерації анотації. Повний текст доступний за посиланням нижче.",
    evidence_level="Low",
    evidence_justification="Рівень не визначено через технічну помилку обробки.",
    practical_relevance="Low",
    clinical_takeaway="Не вдалося автоматично опрацювати цю статтю.",
)

_client = None


def _get_client():
    """Клієнт створюється лише при першому зверненні (lazy) — незалежно від
    порядку імпортів / load_dotenv()."""
    global _client
    if _client is None:
        from google import genai

        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("Не задано GEMINI_API_KEY (або GOOGLE_API_KEY) у середовищі.")
        _client = genai.Client(api_key=api_key)
    return _client


def _is_rate_limit(exc: BaseException) -> bool:
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if code in (429, "429"):
        return True
    text = str(exc).lower()
    return (
        "429" in text
        or "resource_exhausted" in text
        or "too many requests" in text
        or "rate limit" in text
    )


def _build_config():
    from google.genai import types

    kwargs = {
        "system_instruction": SYSTEM_PROMPT,
        "response_mime_type": "application/json",
        "response_schema": DigestArticle,
        "temperature": 0.2,
    }
    try:
        kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
    except Exception:  # noqa: BLE001 — старіші версії SDK можуть не мати thinking_config
        pass
    return types.GenerateContentConfig(**kwargs)


def _to_digest(raw) -> DigestArticle:
    if isinstance(raw, DigestArticle):
        return raw
    if raw is None:
        raise ValueError("Порожня відповідь моделі")
    if isinstance(raw, dict):
        return DigestArticle.model_validate(raw)
    if isinstance(raw, str):
        return DigestArticle.model_validate_json(raw)
    # google-genai іноді повертає pydantic-подібний об'єкт без isinstance
    if hasattr(raw, "model_dump"):
        return DigestArticle.model_validate(raw.model_dump())
    raise ValueError(f"Невідомий тип відповіді: {type(raw)}")


@retry(
    retry=retry_if_exception(_is_rate_limit),
    wait=wait_chain(wait_fixed(15), wait_fixed(30), wait_fixed(60)),
    stop=stop_after_attempt(4),
    reraise=True,
)
def _generate(model: str, user_content: str) -> DigestArticle:
    """Один виклик Gemini. 429 → 15/30/60 с. Інші помилки — наверх."""
    response = _get_client().models.generate_content(
        model=model,
        contents=user_content,
        config=_build_config(),
    )
    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        return _to_digest(parsed)
    text = getattr(response, "text", None)
    if text:
        return _to_digest(text)
    raise ValueError("Модель не повернула ні parsed, ні text")


def _generate_resilient(model: str, user_content: str) -> DigestArticle:
    """Один повтор при не-429 збої (мережа/парсинг), плюс tenacity на 429."""
    last_error = None
    for attempt in range(2):
        try:
            return _generate(model, user_content)
        except Exception as e:  # noqa: BLE001
            last_error = e
            if _is_rate_limit(e):
                raise
            if attempt == 0:
                time.sleep(2)
    raise last_error


def _as_public_dict(article: DigestArticle) -> dict:
    """Поля для db.save_article / format_article. conclusion/description —
    зворотна сумісність зі старою схемою (колонки вже є в прод-БД)."""
    return {
        "title_ua": article.title_ua,
        "summary_ua": article.summary_ua,
        "conclusion": article.clinical_takeaway,
        "description": article.summary_ua,
        "evidence_level": article.evidence_level,
        "evidence_justification": article.evidence_justification,
        "practical_relevance": article.practical_relevance,
        "clinical_takeaway": article.clinical_takeaway,
        "upgraded": False,
    }


def summarize_article(
    title: str,
    abstract: str,
    journal: str,
    premium_used_today: int = 0,
) -> dict:
    """Повертає dict з полями DigestArticle + conclusion/description для старої схеми.

    Крок 1: завжди FAST_MODEL. Крок 2 (опційно): Pro, якщо practical_relevance
    (або evidence_level) у списках апгрейду і не вичерпано MAX_PREMIUM_PER_DAY.
    Якщо Pro не вдався — тихо лишаємо Flash.
    """
    user_content = (
        f"Назва статті: {title}\n"
        f"Журнал: {journal}\n"
        f"Офіційна анотація (abstract):\n{abstract}"
    )

    try:
        result = _generate_resilient(FAST_MODEL, user_content)
    except Exception as e:  # noqa: BLE001
        print(f"summarizer: остаточна помилка {FAST_MODEL} — {e}")
        fallback = FALLBACK.model_copy()
        fallback.title_ua = title[:180] if title else fallback.title_ua
        fallback.clinical_takeaway = "Не вдалося автоматично опрацювати цю статтю."
        return _as_public_dict(fallback)

    time.sleep(GEMINI_CALL_GAP_SECONDS)

    should_upgrade = (
        ENABLE_PREMIUM_UPGRADE
        and PREMIUM_MODEL != FAST_MODEL
        and premium_used_today < MAX_PREMIUM_PER_DAY
        and (
            result.practical_relevance in UPGRADE_PRACTICAL_LEVELS
            or result.evidence_level in UPGRADE_EVIDENCE_LEVELS
        )
    )

    if should_upgrade:
        try:
            premium = _generate(PREMIUM_MODEL, user_content)
            print(
                f"    ↳ practical_relevance={result.practical_relevance}, "
                f"evidence={result.evidence_level} → уточнено моделлю {PREMIUM_MODEL}"
            )
            time.sleep(GEMINI_CALL_GAP_SECONDS)
            out = _as_public_dict(premium)
            out["upgraded"] = True
            return out
        except Exception as e:  # noqa: BLE001
            print(
                f"    ↳ Підвищення якості не вдалося ({PREMIUM_MODEL}): {e}. "
                f"Залишаю результат {FAST_MODEL}."
            )

    return _as_public_dict(result)
