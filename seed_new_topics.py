"""
Одноразовий скрипт після додавання нових тем у config/topics.py.
Запустити ОДИН раз, потім можна видалити.

Шукає статті за SEED_LOOKBACK_DAYS і зберігає їх як уже опубліковані
(posted_to_channel=1) БЕЗ Gemini і БЕЗ публікації в канал — щоб перший
звичайний цикл не злив увесь історичний беклог у безкоштовну квоту.
"""

import os

from dotenv import load_dotenv

load_dotenv()

import db
from config.topics import TOPICS
from fetcher import fetch_new_articles_for_topic

NEW_TOPIC_KEYS = [
    "lung_pocus",
    "ceus",
    "elastography",
    "ai_tech",
    "abdomen",
    "liver",
    "kidney",
    "pancreas_gi",
    "obstetrics",
    "vascular",
    "msk",
    "peripheral_nerves",
    "pediatric",
    "head_neck",
    "acute_emergency",
    "oncology",
]

SEED_LOOKBACK_DAYS = 30
NCBI_KEY = os.environ.get("NCBI_API_KEY", "")

db.init_db()
total = 0

for key in NEW_TOPIC_KEYS:
    topic = TOPICS.get(key)
    if not topic:
        print(f"[{key}] немає в поточному TOPICS, пропускаю")
        continue

    try:
        articles = fetch_new_articles_for_topic(
            query=topic["query"],
            days_back=SEED_LOOKBACK_DAYS,
            retmax=50,
            api_key=NCBI_KEY,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[{key}] помилка запиту до PubMed: {e}")
        continue

    added = 0
    for art in articles:
        if not art["pmid"] or db.article_exists(art["pmid"]):
            continue
        db.save_article(
            pmid=art["pmid"],
            topic_key=key,
            title=art["title"],
            journal=art["journal"],
            pub_date=art["pub_date"],
            url=art["url"],
            conclusion="(seed: позначено як переглянуте при додаванні теми, без AI-анотації)",
            description="",
            evidence_level="Low",
            practical_relevance="Low",
            title_ua="",
            summary_ua="",
            evidence_justification="",
            clinical_takeaway="",
        )
        db.mark_posted(art["pmid"])
        added += 1

    print(f"[{key}] позначено без публікації: {added}")
    total += added

print(f"Готово. Всього позначено: {total}")
