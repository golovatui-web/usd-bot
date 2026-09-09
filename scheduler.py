"""
Періодична задача, яку викликає JobQueue бота (див. main.py), раз на день у фіксований
час (run_daily у main.py, а не "кожні N годин від старту сервісу" — щоб час публікації
не "плавав" після кожного рестарту/деплою).

Для кожної теми з config/topics.py:
  1. шукає нові статті в PubMed за останні LOOKBACK_DAYS днів
  2. пропускає ті, що вже є в базі (за PMID)
  3. для нових — генерує висновок+опис+рівень доказовості+практичну цінність через Claude
  4. зберігає в базу
  5. публікує накопичені непубліковані статті в канал під заголовком дня
  6. шле heartbeat адміну (якщо налаштовано ADMIN_CHAT_ID)

MAX_ARTICLES_PER_DAY — жорсткий запобіжник: навіть якщо PubMed раптом поверне аномально
багато нових статей за один прохід, опрацювання зупиниться на цій кількості. Це напряму
обмежує максимальні витрати на Claude API за один цикл.

ВАЖЛИВО про продуктивність: PubMed-запити (requests) та виклики Claude API (синхронний
Anthropic SDK, тепер потенційно ДВІЧІ на статтю через гібридну fast/premium-схему в
summarizer.py) — блокуючі, синхронні операції. Якби вони виконувались прямо в цій async-
функції, event loop бота був би заблокований на весь час перевірки, і команди /topics,
/search тощо не відповідали б у цей час. Тому вся важка синхронна логіка винесена в
_fetch_and_summarize_all_topics() і викликається через asyncio.to_thread — в окремому
потоці, не блокуючи бота.
"""

import asyncio
import os

from telegram.ext import ContextTypes

import db
from bot import post_digest_to_channel, send_heartbeat
from config.topics import TOPICS
from fetcher import fetch_new_articles_for_topic
from summarizer import summarize_article


def _fetch_and_summarize_all_topics() -> int:
    """Синхронна важка частина циклу. Виконується в окремому потоці (див.
    check_and_process_new_articles нижче) — саме тому це звичайна `def`, а не `async def`."""
    lookback_days = int(os.environ.get("LOOKBACK_DAYS", 5))
    max_per_topic = int(os.environ.get("MAX_ARTICLES_PER_TOPIC", 5))
    max_per_day = int(os.environ.get("MAX_ARTICLES_PER_DAY", 40))
    ncbi_key = os.environ.get("NCBI_API_KEY", "")

    total_new = 0

    for topic_key, topic_data in TOPICS.items():
        if total_new >= max_per_day:
            print(f"Досягнуто денний ліміт {max_per_day} статей — решта тем перевіриться наступного разу.")
            break

        try:
            articles = fetch_new_articles_for_topic(
                query=topic_data["query"],
                days_back=lookback_days,
                retmax=max_per_topic,
                api_key=ncbi_key,
            )
        except Exception as e:  # noqa: BLE001
            print(f"[{topic_key}] Помилка запиту до PubMed: {e}")
            continue

        for art in articles:
            if total_new >= max_per_day:
                break
            if not art["pmid"]:
                continue
            if db.article_exists(art["pmid"]):
                # Стаття вже опрацьована — можливо, під ІНШОЮ темою, чиї критерії теж
                # збіглися раніше в переліку TOPICS (теми в config/topics.py навмисно
                # широкі й перетинаються, напр. "biopsy" є і в thyroid, і в breast_lymph).
                # Свідомий вибір дизайну: pmid глобально унікальний у таблиці articles,
                # тому перша тема, що "забрала" статтю в цьому проході, і залишається
                # її темою/хештегом — це гарантує, що жоден пост не продублюється в
                # каналі і жоден виклик Claude не витрачається повторно на той самий PMID.
                continue

            result = summarize_article(
                title=art["title"], abstract=art["abstract"], journal=art["journal"]
            )

            db.save_article(
                pmid=art["pmid"],
                topic_key=topic_key,
                title=art["title"],
                journal=art["journal"],
                pub_date=art["pub_date"],
                url=art["url"],
                conclusion=result["conclusion"],
                description=result["description"],
                evidence_level=result["evidence_level"],
                practical_relevance=result.get("practical_relevance", "Low"),
            )
            total_new += 1
            print(f"[{topic_key}] Додано: {art['title'][:70]}...")

    print(f"Перевірку завершено. Нових статей: {total_new}.")
    return total_new


async def check_and_process_new_articles(context: ContextTypes.DEFAULT_TYPE):
    total_new = await asyncio.to_thread(_fetch_and_summarize_all_topics)
    await post_digest_to_channel(context)
    await send_heartbeat(context, total_new)
