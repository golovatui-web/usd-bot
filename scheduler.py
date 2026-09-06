"""
Періодична задача, яку викликає JobQueue бота (див. main.py).

Для кожної теми з config/topics.py:
  1. шукає нові статті в PubMed за останні LOOKBACK_DAYS днів
  2. пропускає ті, що вже є в базі (за PMID)
  3. для нових — генерує анотацію + рівень доказовості через Claude
  4. зберігає в базу
  5. публікує накопичені непубліковані статті в канал
"""

import os

from telegram.ext import ContextTypes

import db
from bot import post_digest_to_channel
from config.topics import TOPICS
from fetcher import fetch_new_articles_for_topic
from summarizer import summarize_article


async def check_and_process_new_articles(context: ContextTypes.DEFAULT_TYPE):
    lookback_days = int(os.environ.get("LOOKBACK_DAYS", 14))
    max_per_topic = int(os.environ.get("MAX_ARTICLES_PER_TOPIC", 5))
    ncbi_key = os.environ.get("NCBI_API_KEY", "")

    total_new = 0

    for topic_key, topic_data in TOPICS.items():
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
            if not art["pmid"] or db.article_exists(art["pmid"]):
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
                summary=result["summary"],
                evidence_level=result["evidence_level"],
                evidence_reason=result["evidence_reason"],
            )
            total_new += 1
            print(f"[{topic_key}] Додано: {art['title'][:70]}...")

    print(f"Перевірку завершено. Нових статей: {total_new}.")

    # публікуємо все, що накопичилось і ще не опубліковано
    await post_digest_to_channel(context)
