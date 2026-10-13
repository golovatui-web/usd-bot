"""
SQLite: опрацьовані статті, черга 24/7, закладки, курсор round-robin.

База вже в проді — будь-яка зміна схеми ЛИШЕ через ALTER TABLE з попередньою
перевіркою PRAGMA table_info, ніколи DROP/CREATE наново.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

DB_PATH = "usd_bot.db"

QUEUE_PENDING = "pending"
QUEUE_PROCESSING = "processing"
QUEUE_PROCESSED = "processed"
QUEUE_FAILED = "failed"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _add_column_if_missing(conn, table: str, column: str, ddl: str, log: str):
    if not _column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
        print(f"db: {log}")


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pmid TEXT UNIQUE NOT NULL,
                topic_key TEXT NOT NULL,
                title TEXT NOT NULL,
                journal TEXT,
                pub_date TEXT,
                url TEXT,
                conclusion TEXT,
                description TEXT,
                evidence_level TEXT,
                practical_relevance TEXT DEFAULT 'Low',
                posted_to_channel INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )

        cols = {row["name"] for row in conn.execute("PRAGMA table_info(articles)")}
        if "summary" in cols and "conclusion" not in cols:
            conn.execute("ALTER TABLE articles RENAME COLUMN summary TO conclusion")
            conn.execute("ALTER TABLE articles ADD COLUMN description TEXT")
            print("db: міграція схеми articles (summary → conclusion + description)")

        _add_column_if_missing(
            conn, "articles", "practical_relevance",
            "practical_relevance TEXT DEFAULT 'Low'",
            "міграція articles (додано practical_relevance)",
        )
        _add_column_if_missing(
            conn, "articles", "title_ua",
            "title_ua TEXT",
            "міграція articles (додано title_ua)",
        )
        _add_column_if_missing(
            conn, "articles", "summary_ua",
            "summary_ua TEXT",
            "міграція articles (додано summary_ua)",
        )
        _add_column_if_missing(
            conn, "articles", "evidence_justification",
            "evidence_justification TEXT",
            "міграція articles (додано evidence_justification)",
        )
        _add_column_if_missing(
            conn, "articles", "clinical_takeaway",
            "clinical_takeaway TEXT",
            "міграція articles (додано clinical_takeaway)",
        )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_topic ON articles(topic_key)")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS article_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pmid TEXT UNIQUE NOT NULL,
                topic_key TEXT NOT NULL,
                title TEXT NOT NULL,
                journal TEXT,
                pub_date TEXT,
                url TEXT,
                abstract TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER DEFAULT 0,
                last_error TEXT,
                added_at TEXT NOT NULL,
                processed_at TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_queue_status ON article_queue(status, added_at)"
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                pmid TEXT NOT NULL,
                title TEXT,
                url TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, pmid)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bookmark_user ON bookmarks(user_id)")


def get_state(key: str, default: str = "") -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM bot_state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_state(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO bot_state(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def article_exists(pmid: str) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM articles WHERE pmid = ?", (pmid,)).fetchone()
        return row is not None


def queue_has_pmid(pmid: str) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM article_queue WHERE pmid = ?", (pmid,)).fetchone()
        return row is not None


def enqueue_article(
    pmid: str,
    topic_key: str,
    title: str,
    journal: str,
    pub_date: str,
    url: str,
    abstract: str,
) -> bool:
    """True, якщо рядок додано. Дублікати (pmid) ігноруються."""
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO article_queue
            (pmid, topic_key, title, journal, pub_date, url, abstract, status, added_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                pmid, topic_key, title, journal, pub_date, url, abstract,
                datetime.utcnow().isoformat(),
            ),
        )
        return cursor.rowcount > 0


def reclaim_stale_processing(minutes: int = 30):
    """Якщо воркер впав під час processing — повертаємо в pending."""
    cutoff = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE article_queue
            SET status = 'pending'
            WHERE status = 'processing' AND added_at < ?
            """,
            (cutoff,),
        )


def claim_next_pending():
    """Атомарно бере одну pending-статтю і ставить processing."""
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM article_queue
            WHERE status = 'pending'
            ORDER BY added_at ASC
            LIMIT 1
            """
        ).fetchone()
        if not row:
            return None
        cursor = conn.execute(
            """
            UPDATE article_queue
            SET status = 'processing', attempts = attempts + 1
            WHERE pmid = ? AND status = 'pending'
            """,
            (row["pmid"],),
        )
        if cursor.rowcount == 0:
            return None
        return dict(row)


def mark_queue_processed(pmid: str):
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE article_queue
            SET status = 'processed', processed_at = ?, last_error = NULL
            WHERE pmid = ?
            """,
            (datetime.utcnow().isoformat(), pmid),
        )


def mark_queue_failed(pmid: str, error: str, max_attempts: int = 3):
    """Після max_attempts — failed (стаття НЕ публікується). Інакше знову pending."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT attempts FROM article_queue WHERE pmid = ?", (pmid,)
        ).fetchone()
        attempts = row["attempts"] if row else 99
        status = QUEUE_FAILED if attempts >= max_attempts else QUEUE_PENDING
        conn.execute(
            """
            UPDATE article_queue
            SET status = ?, last_error = ?
            WHERE pmid = ?
            """,
            (status, error[:500], pmid),
        )
        return status


def count_queue(status: str | None = None) -> int:
    with get_conn() as conn:
        if status:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM article_queue WHERE status = ?", (status,)
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) AS n FROM article_queue").fetchone()
        return int(row["n"])


def count_processed_today() -> int:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n FROM articles
            WHERE created_at >= ?
            """,
            (today,),
        ).fetchone()
        return int(row["n"])


def count_premium_today() -> int:
    """Скільки Pro-апгрейдів сьогодні — зберігаємо лічильник у bot_state."""
    key = f"premium_{datetime.utcnow().strftime('%Y-%m-%d')}"
    raw = get_state(key, "0")
    try:
        return int(raw)
    except ValueError:
        return 0


def bump_premium_today() -> int:
    key = f"premium_{datetime.utcnow().strftime('%Y-%m-%d')}"
    n = count_premium_today() + 1
    set_state(key, str(n))
    return n


def save_article(
    pmid: str,
    topic_key: str,
    title: str,
    journal: str,
    pub_date: str,
    url: str,
    conclusion: str,
    description: str,
    evidence_level: str,
    practical_relevance: str = "Low",
    title_ua: str = "",
    summary_ua: str = "",
    evidence_justification: str = "",
    clinical_takeaway: str = "",
):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO articles
            (pmid, topic_key, title, journal, pub_date, url, conclusion,
             description, evidence_level, practical_relevance,
             title_ua, summary_ua, evidence_justification, clinical_takeaway,
             created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pmid, topic_key, title, journal, pub_date, url, conclusion,
                description, evidence_level, practical_relevance,
                title_ua or None, summary_ua or None,
                evidence_justification or None,
                clinical_takeaway or conclusion,
                datetime.utcnow().isoformat(),
            ),
        )


def get_article_by_pmid(pmid: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM articles WHERE pmid = ?", (pmid,)).fetchone()
        return dict(row) if row else None


def mark_posted(pmid: str):
    with get_conn() as conn:
        conn.execute("UPDATE articles SET posted_to_channel = 1 WHERE pmid = ?", (pmid,))


def get_unposted_articles(limit: int = 100):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM articles WHERE posted_to_channel = 0 ORDER BY created_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_articles_by_topic(topic_key: str, limit: int = 5):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM articles WHERE topic_key = ? ORDER BY created_at DESC LIMIT ?",
            (topic_key, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def search_articles(keyword: str, limit: int = 10):
    with get_conn() as conn:
        like = f"%{keyword}%"
        rows = conn.execute(
            """
            SELECT * FROM articles
            WHERE title LIKE ? OR title_ua LIKE ? OR description LIKE ?
               OR conclusion LIKE ? OR summary_ua LIKE ? OR clinical_takeaway LIKE ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (like, like, like, like, like, like, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def get_recent_articles(limit: int = 10):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM articles ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def add_bookmark(user_id: int, pmid: str, title: str, url: str) -> bool:
    """True = новий запис, False = уже було збережено."""
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO bookmarks (user_id, pmid, title, url, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, pmid, title, url, datetime.utcnow().isoformat()),
        )
        return cursor.rowcount > 0


def get_bookmarks(user_id: int, limit: int = 30):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM bookmarks WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
