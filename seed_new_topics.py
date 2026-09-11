"""
seed_new_topics.py — ОДНОРАЗОВИЙ скрипт. Запустити ОДИН раз після оновлення
config/topics.py, потім видалити файл (rm seed_new_topics.py).

Навіщо: коли додаються нові теми, їхній перший пошук по PubMed із LOOKBACK_DAYS/
ширшим вікном знайде багато статей, яких ще НЕМАЄ в базі (бо старі теми їх не
покривали) — і при звичайному циклі бот спробує опублікувати їх ВСІ одразу, разом
із витратами на Claude API за кожну. Цей скрипт натомість:
  1. шукає по PubMed за розширеним вікном (SEED_LOOKBACK_DAYS) для кожної теми з
     переліку нижче,
  2. зберігає знайдені статті в БД ОДРАЗУ як "вже опубліковані" (posted_to_channel=1),
  3. БЕЗ звернення до Claude API (нуль витрат) і БЕЗ публікації в канал.

Результат: з наступного звичайного циклу бот бачитиме лише СПРАВДІ нові (майбутні)
публікації по цих темах, а не весь історичний бэклог.

Безпечно запускати повторно: article_exists(pmid) все одно захищає від дублів,
тому навіть якщо частина тем уже "бачила" ці статті раніше — просто пропустяться,
жодної шкоди.
"""

import os

from dotenv import load_dotenv

load_dotenv()

import db
from config.topics import TOPICS
from fetcher import fetch_new_articles_for_topic

# Ключі тем, які МОЖУТЬ бути новими відносно попередньої версії конфігурації
# (безпечно лишати тут теми, які насправді вже опрацьовувались раніше — скрипт
# просто знайде 0 нових для них і піде далі, жодних зайвих витрат).
NEW_TOPIC_KEYS = [
    "abdomen", "liver", "kidney", "pancreas_gi", "obstetrics",
    "vascular", "msk", "peripheral_nerves", "pediatric", "head_neck",
    "acute_emergency", "oncology",
]

SEED_LOOKBACK_DAYS = 30  # ширше за звичайний LOOKBACK_DAYS, щоб накрити весь бэклог
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
            query=topic["query"], days_back=SEED_LOOKBACK_DAYS, retmax=50, api_key=NCBI_KEY,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[{key}] помилка запиту до PubMed: {e}")
        continue

    added = 0
    for art in articles:
        if not art["pmid"] or db.article_exists(art["pmid"]):
            continue
        # ВАЖЛИВО: сигнатура save_article відповідає ПОТОЧНІЙ схемі БД
        # (conclusion/description/evidence_level/practical_relevance) —
        # не старій summary/evidence_reason.
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
        )
        db.mark_posted(art["pmid"])
        added += 1

    print(f"[{key}] позначено без публікації: {added}")
    total += added

print(f"Готово. Всього позначено: {total}")
