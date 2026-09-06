"""
Проста SQLite-база для зберігання оброблених статей.
Файл бази (usd_bot.db) створюється автоматично поруч зі скриптом.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime

DB_PATH = "usd_bot.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


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
                summary TEXT,
                evidence_level TEXT,
                evidence_reason TEXT,
                posted_to_channel INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_topic ON articles(topic_key)"
        )


def article_exists(pmid: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM articles WHERE pmid = ?", (pmid,)
        ).fetchone()
        return row is not None


def save_article(
    pmid: str,
    topic_key: str,
    title: str,
    journal: str,
    pub_date: str,
    url: str,
    summary: str,
    evidence_level: str,
    evidence_reason: str,
):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO articles
            (pmid, topic_key, title, journal, pub_date, url, summary,
             evidence_level, evidence_reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pmid, topic_key, title, journal, pub_date, url, summary,
                evidence_level, evidence_reason, datetime.utcnow().isoformat(),
            ),
        )


def mark_posted(pmid: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE articles SET posted_to_channel = 1 WHERE pmid = ?", (pmid,)
        )


def get_unposted_articles(limit: int = 20):
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
            WHERE title LIKE ? OR summary LIKE ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (like, like, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def get_recent_articles(limit: int = 10):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM articles ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
