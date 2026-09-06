"""
Обробники команд Telegram-бота + функція публікації дайджесту в канал.
"""

import os

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import db
from config.topics import TOPICS, get_topic_label, list_topics_text

LEVEL_EMOJI = {"High": "🟢 High", "Medium": "🟡 Medium", "Low": "🔴 Low"}


def format_article(article: dict) -> str:
    level = LEVEL_EMOJI.get(article["evidence_level"], article["evidence_level"])
    return (
        f"*{article['title']}*\n"
        f"_{article['journal']}, {article['pub_date']}_\n\n"
        f"{article['summary']}\n\n"
        f"Рівень доказовості: {level}"
        f"{' — ' + article['evidence_reason'] if article.get('evidence_reason') else ''}\n"
        f"🔗 [Джерело]({article['url']})"
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Вітаю! Я бот-дайджест новин УЗД-діагностики.\n\n"
        "Команди:\n"
        "/теми — список тем\n"
        "/тема <ключ> — останні статті за темою (напр. /тема thyroid)\n"
        "/пошук <слово> — пошук за ключовим словом\n"
        "/останні — останні опрацьовані статті за всіма темами\n"
    )
    await update.message.reply_text(text)


async def cmd_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(list_topics_text(), parse_mode=ParseMode.MARKDOWN)


async def cmd_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Вкажіть ключ теми, напр.: `/тема thyroid`\nПовний список — /теми",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    topic_key = context.args[0].strip().lower()
    if topic_key not in TOPICS:
        await update.message.reply_text("Такої теми немає. Перевірте /теми.")
        return

    articles = db.get_articles_by_topic(topic_key, limit=5)
    if not articles:
        await update.message.reply_text(
            f"Поки що немає збережених статей за темою «{get_topic_label(topic_key)}»."
        )
        return

    await update.message.reply_text(f"📚 {get_topic_label(topic_key)}:")
    for art in articles:
        await update.message.reply_text(
            format_article(art), parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True
        )


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Вкажіть слово для пошуку, напр.: `/пошук РЧА`", parse_mode=ParseMode.MARKDOWN)
        return

    keyword = " ".join(context.args)
    results = db.search_articles(keyword, limit=10)
    if not results:
        await update.message.reply_text("Нічого не знайдено.")
        return

    await update.message.reply_text(f"🔎 Результати за запитом «{keyword}»:")
    for art in results:
        await update.message.reply_text(
            format_article(art), parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True
        )


async def cmd_recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    articles = db.get_recent_articles(limit=10)
    if not articles:
        await update.message.reply_text("Ще немає опрацьованих статей.")
        return
    for art in articles:
        await update.message.reply_text(
            format_article(art), parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True
        )


async def post_digest_to_channel(context: ContextTypes.DEFAULT_TYPE):
    """Публікує в канал усі ще не опубліковані статті. Викликається планувальником (main.py)."""
    channel_id = os.environ["TELEGRAM_CHANNEL_ID"]
    pending = db.get_unposted_articles(limit=20)

    for art in pending:
        try:
            await context.bot.send_message(
                chat_id=channel_id,
                text=format_article(art),
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True,
            )
            db.mark_posted(art["pmid"])
        except Exception as e:  # noqa: BLE001
            print(f"Не вдалося опублікувати статтю {art['pmid']}: {e}")
