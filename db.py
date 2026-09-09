"""
Проста SQLite-база для зберігання оброблених статей і закладок користувачів.
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


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


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

        # Захисні міграції — БД уже в проді, тому ЛИШЕ ALTER TABLE з попередньою
        # перевіркою PRAGMA table_info, ніколи DROP/CREATE наново.

        # 1) Дуже стара схема (summary/evidence_reason, до появи conclusion/description).
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(articles)")}
        if "summary" in cols and "conclusion" not in cols:
            conn.execute("ALTER TABLE articles RENAME COLUMN summary TO conclusion")
            conn.execute("ALTER TABLE articles ADD COLUMN description TEXT")
            print("db: міграція схеми articles (summary → conclusion + description)")

        # 2) practical_relevance (новіша колонка, могла бути відсутня в БД, створеній
        #    попередньою версією без гібридної fast/premium-схеми). Старі статті
        #    отримають DEFAULT 'Low' — просто не матимуть бейджа 🩺 в каналі, жодні
        #    наявні дані не губляться.
        if not _column_exists(conn, "articles", "practical_relevance"):
            conn.execute(
                "ALTER TABLE articles ADD COLUMN practical_relevance TEXT DEFAULT 'Low'"
            )
            print("db: міграція схеми articles (додано practical_relevance)")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_topic ON articles(topic_key)")

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


def article_exists(pmid: str) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM articles WHERE pmid = ?", (pmid,)).fetchone()
        return row is not None


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
):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO articles
            (pmid, topic_key, title, journal, pub_date, url, conclusion,
             description, evidence_level, practical_relevance, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pmid, topic_key, title, journal, pub_date, url, conclusion,
                description, evidence_level, practical_relevance,
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
            WHERE title LIKE ? OR description LIKE ? OR conclusion LIKE ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (like, like, like, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def get_recent_articles(limit: int = 10):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM articles ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def add_bookmark(user_id: int, pmid: str, title: str, url: str) -> bool:
    """Повертає True, якщо це новий запис, False — якщо користувач вже зберігав цю статтю раніше."""
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
