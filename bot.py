"""
Обробники команд Telegram-бота + функція публікації дайджесту в канал.
"""

import os
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import db
from config.topics import TOPICS, get_topic_hashtag, get_topic_label, list_topics_text

LEVEL_DOT = {"High": "🟢", "Medium": "🟡", "Low": "🔴"}


def format_article(article: dict) -> str:
    """Новий формат: спочатку висновок (виділено), потім опис, доказовість — лише кольором."""
    dot = LEVEL_DOT.get(article["evidence_level"], "⚪")
    hashtag = get_topic_hashtag(article.get("topic_key", ""))
    return (
        f"{dot} *{article['title']}*\n\n"
        f"💡 *{article['conclusion']}*\n\n"
        f"{article['description']}\n\n"
        f"{hashtag}\n"
        f"🔗 [Джерело]({article['url']}) · {article['journal']}, {article['pub_date']}"
    )


def save_button(pmid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔖 Зберегти", callback_data=f"save:{pmid}")]]
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Вітаю! Я бот-дайджест новин УЗД-діагностики.\n\n"
        "Команди:\n"
        "/topics — список тем\n"
        "/topic <ключ> — останні статті за темою (напр. /topic thyroid)\n"
        "/search <слово> — пошук за ключовим словом\n"
        "/recent — останні опрацьовані статті за всіма темами\n"
        "/saved — ваші збережені статті (натискайте 🔖 під постами в каналі)\n"
    )
    await update.message.reply_text(text)


async def cmd_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(list_topics_text(), parse_mode=ParseMode.MARKDOWN)


async def cmd_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Вкажіть ключ теми, напр.: `/topic thyroid`\nПовний список — /topics",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    topic_key = context.args[0].strip().lower()
    if topic_key not in TOPICS:
        await update.message.reply_text("Такої теми немає. Перевірте /topics.")
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
            format_article(art),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
            reply_markup=save_button(art["pmid"]),
        )


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Вкажіть слово для пошуку, напр.: `/search РЧА`", parse_mode=ParseMode.MARKDOWN)
        return

    keyword = " ".join(context.args)
    results = db.search_articles(keyword, limit=10)
    if not results:
        await update.message.reply_text("Нічого не знайдено.")
        return

    await update.message.reply_text(f"🔎 Результати за запитом «{keyword}»:")
    for art in results:
        await update.message.reply_text(
            format_article(art),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
            reply_markup=save_button(art["pmid"]),
        )


async def cmd_recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    articles = db.get_recent_articles(limit=10)
    if not articles:
        await update.message.reply_text("Ще немає опрацьованих статей.")
        return
    for art in articles:
        await update.message.reply_text(
            format_article(art),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
            reply_markup=save_button(art["pmid"]),
        )


async def cmd_saved(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bookmarks = db.get_bookmarks(user_id, limit=30)
    if not bookmarks:
        await update.message.reply_text(
            "У вас поки немає збережених статей. Натискайте 🔖 «Зберегти» під постами в каналі."
        )
        return

    lines = ["🔖 Ваші збережені статті:\n"]
    for b in bookmarks:
        lines.append(f"• [{b['title']}]({b['url']})")
    await update.message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True
    )


async def handle_save_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробляє натискання кнопки 🔖 Зберегти під постом у каналі (працює для будь-кого,
    навіть якщо людина ще не писала боту в особисті — answer_callback_query не потребує цього)."""
    query = update.callback_query
    pmid = query.data.split(":", 1)[1]

    article = db.get_article_by_pmid(pmid)
    if not article:
        await query.answer("Статтю не знайдено в базі.", show_alert=True)
        return

    db.add_bookmark(query.from_user.id, pmid, article["title"], article["url"])
    await query.answer(
        "🔖 Збережено! Перегляньте список командою /saved у приватному чаті з ботом.",
        show_alert=True,
    )


async def post_digest_to_channel(context: ContextTypes.DEFAULT_TYPE):
    """Публікує в канал усі ще не опубліковані статті одним блоком під заголовком дня.
    Викликається планувальником (main.py) — типово раз на день."""
    channel_id = os.environ["TELEGRAM_CHANNEL_ID"]
    pending = db.get_unposted_articles(limit=100)

    if not pending:
        return

    today_label = datetime.now().strftime("%d.%m.%Y")
    try:
        await context.bot.send_message(
            chat_id=channel_id,
            text=f"📅 *{today_label}*",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:  # noqa: BLE001
        print(f"Не вдалося опублікувати заголовок дня: {e}")

    for art in pending:
        try:
            await context.bot.send_message(
                chat_id=channel_id,
                text=format_article(art),
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True,
                reply_markup=save_button(art["pmid"]),
            )
            db.mark_posted(art["pmid"])
        except Exception as e:  # noqa: BLE001
            print(f"Не вдалося опублікувати статтю {art['pmid']}: {e}")
