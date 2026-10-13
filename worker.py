"""
AI-воркер черги: бере 1 pending-статтю, викликає Gemini (Flash → Pro),
пише в articles. Синхронний — викликається через asyncio.to_thread,
щоб не блокувати event loop бота.

Пауза GEMINI_CALL_GAP_SECONDS між викликами API живе всередині
gemini_service.summarize_article. Тут додатково:
  - денний ліміт MAX_ARTICLES_PER_DAY
  - tenacity/429 обробляє gemini_service
  - після max спроб стаття йде в failed і НЕ публікується
    (сирий текст помилки лише в лог / article_queue.last_error)
"""

from __future__ import annotations

import os

import db
from gemini_service import summarize_article

MAX_QUEUE_ATTEMPTS = int(os.environ.get("MAX_QUEUE_ATTEMPTS", "3"))


def process_one_pending_article() -> str:
    """Повертає idle | ok | failed | capped. Звичайна def — для to_thread."""
    max_per_day = int(os.environ.get("MAX_ARTICLES_PER_DAY", "40"))

    if db.count_processed_today() >= max_per_day:
        return "capped"

    db.reclaim_stale_processing()
    item = db.claim_next_pending()
    if not item:
        return "idle"

    pmid = item["pmid"]
    if db.article_exists(pmid):
        db.mark_queue_processed(pmid)
        return "ok"

    premium_used = db.count_premium_today()
    try:
        result = summarize_article(
            title=item["title"],
            abstract=item["abstract"],
            journal=item.get("journal") or "",
            premium_used_today=premium_used,
        )
    except Exception as e:  # noqa: BLE001
        print(f"worker: помилка обробки PMID {pmid}: {e}")
        db.mark_queue_failed(pmid, str(e), max_attempts=MAX_QUEUE_ATTEMPTS)
        return "failed"

    # Якщо Fast уже віддав нейтральний fallback — все одно зберігаємо,
    # щоб не крутити ту саму статтю вічно. Користувач бачить нейтральний текст.
    db.save_article(
        pmid=pmid,
        topic_key=item["topic_key"],
        title=item["title"],
        journal=item.get("journal") or "",
        pub_date=item.get("pub_date") or "",
        url=item["url"],
        conclusion=result["conclusion"],
        description=result["description"],
        evidence_level=result["evidence_level"],
        practical_relevance=result.get("practical_relevance", "Low"),
        title_ua=result.get("title_ua", ""),
        summary_ua=result.get("summary_ua", ""),
        evidence_justification=result.get("evidence_justification", ""),
        clinical_takeaway=result.get("clinical_takeaway", result["conclusion"]),
    )
    if result.get("upgraded"):
        db.bump_premium_today()

    db.mark_queue_processed(pmid)
    print(f"[{item['topic_key']}] Опрацьовано: {item['title'][:70]}...")
    return "ok"
