"""
Три задачі планувальника (main.py):

1. PubMed Feeder — кожні FEED_INTERVAL_MINUTES (типово 15) бере
   FEED_TOPICS_PER_TICK (типово 3) теми за круговим циклом, кладе нові PMID
   у article_queue зі статусом pending. Без викликів Gemini.
2. AI Worker — кожні WORKER_INTERVAL_SECONDS (типово 15) обробляє 1 pending
   статтю (див. worker.py). Gemini викликається з паузою 6 с і backoff на 429.
3. Publisher — раз на день о DIGEST_HOUR_KYIV публікує накопичене в канал
   і шле heartbeat адміну.

Важка синхронна частина (PubMed requests, Gemini SDK) ЗАВЖДИ у звичайній def
і викликається через asyncio.to_thread — інакше event loop бота блокується
і команди /topics, /search не відповідають.
"""

from __future__ import annotations

import asyncio
import os

from telegram.ext import ContextTypes

import db
from bot import post_digest_to_channel, send_heartbeat
from config.topics import TOPIC_KEYS, TOPICS
from fetcher import fetch_new_articles_for_topic
from worker import process_one_pending_article

RR_STATE_KEY = "rr_topic_index"


def _feed_next_topics() -> int:
    """Синхронна частина фідера. Повертає кількість доданих у чергу PMID."""
    lookback_days = int(os.environ.get("LOOKBACK_DAYS", "5"))
    max_per_topic = int(os.environ.get("MAX_ARTICLES_PER_TOPIC", "3"))
    per_tick = int(os.environ.get("FEED_TOPICS_PER_TICK", "3"))
    ncbi_key = os.environ.get("NCBI_API_KEY", "")

    n_topics = len(TOPIC_KEYS)
    if n_topics == 0:
        return 0

    try:
        start = int(db.get_state(RR_STATE_KEY, "0")) % n_topics
    except ValueError:
        start = 0

    added = 0
    for i in range(per_tick):
        key = TOPIC_KEYS[(start + i) % n_topics]
        topic = TOPICS[key]
        try:
            articles = fetch_new_articles_for_topic(
                query=topic["query"],
                days_back=lookback_days,
                retmax=max_per_topic,
                api_key=ncbi_key,
            )
        except Exception as e:  # noqa: BLE001
            print(f"[{key}] Помилка запиту до PubMed: {e}")
            continue

        topic_added = 0
        for art in articles:
            pmid = art.get("pmid")
            if not pmid:
                continue
            if db.article_exists(pmid) or db.queue_has_pmid(pmid):
                continue
            if db.enqueue_article(
                pmid=pmid,
                topic_key=key,
                title=art["title"],
                journal=art["journal"],
                pub_date=art["pub_date"],
                url=art["url"],
                abstract=art["abstract"],
            ):
                topic_added += 1
                added += 1
        print(f"[{key}] у чергу: {topic_added}")

    db.set_state(RR_STATE_KEY, str((start + per_tick) % n_topics))
    print(f"Фідер: додано {added}. pending={db.count_queue('pending')}")
    return added


async def feed_pubmed_round_robin(context: ContextTypes.DEFAULT_TYPE):
    await asyncio.to_thread(_feed_next_topics)


async def process_queue_tick(context: ContextTypes.DEFAULT_TYPE):
    status = await asyncio.to_thread(process_one_pending_article)
    if status not in ("idle", "capped"):
        print(f"worker tick: {status}")


async def publish_digest_and_heartbeat(context: ContextTypes.DEFAULT_TYPE):
    total_new = db.count_processed_today()
    await post_digest_to_channel(context)
    pending = db.count_queue("pending")
    failed = db.count_queue("failed")
    await send_heartbeat(context, total_new, pending=pending, failed=failed)


# Зворотна сумісність зі старим іменем джоби (якщо хтось лишив його в unit-файлі).
async def check_and_process_new_articles(context: ContextTypes.DEFAULT_TYPE):
    await feed_pubmed_round_robin(context)
    await process_queue_tick(context)
    await publish_digest_and_heartbeat(context)
