"""
Обробники команд Telegram-бота + публікація дайджесту в канал.
"""

import asyncio
import html
import os
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import db
from config.topics import TOPICS, get_topic_hashtag, get_topic_label, list_topics_text

LEVEL_DOT = {"High": "🟢", "Medium": "🟡", "Low": "🔴"}
PRACTICAL_BADGE_LEVELS = ("High",)
PRACTICAL_BADGE = "🩺"

POST_THROTTLE_SECONDS = 1


def format_article(article: dict) -> str:
    """HTML-пост. Усі динамічні поля — html.escape(). НІКОЛИ Markdown:
    символи _ * [ ] у назвах з PubMed ламають legacy-парсер Telegram.
    """
    dot = LEVEL_DOT.get(article.get("evidence_level") or "Low", "⚪")
    if article.get("practical_relevance") in PRACTICAL_BADGE_LEVELS:
        prefix = f"{dot} {PRACTICAL_BADGE}"
    else:
        prefix = dot
    hashtag = get_topic_hashtag(article.get("topic_key", ""))

    display_title = article.get("title_ua") or article.get("title") or ""
    original_title = article.get("title") or ""
    takeaway = (
        article.get("clinical_takeaway")
        or article.get("conclusion")
        or ""
    )
    summary = article.get("summary_ua") or article.get("description") or ""
    justification = article.get("evidence_justification") or ""
    journal = article.get("journal") or ""
    pub_date = str(article.get("pub_date") or "")
    url = article.get("url") or ""

    title_html = html.escape(display_title)
    takeaway_html = html.escape(takeaway)
    summary_html = html.escape(summary)
    journal_html = html.escape(journal)
    pub_date_html = html.escape(pub_date)
    url_html = html.escape(url, quote=True)

    extra_title = ""
    if original_title and display_title and original_title.strip() != display_title.strip():
        extra_title = f"<i>{html.escape(original_title)}</i>\n\n"

    justification_block = ""
    if justification:
        justification_block = f"{html.escape(justification)}\n\n"

    return (
        f"{prefix} <b>{title_html}</b>\n\n"
        f"{extra_title}"
        f"💡 <b>{takeaway_html}</b>\n\n"
        f"{summary_html}\n\n"
        f"{justification_block}"
        f"{hashtag}\n"
        f'🔗 <a href="{url_html}">Джерело</a> · {journal_html}, {pub_date_html}'
    )


def save_button(pmid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔖 Зберегти", callback_data=f"save:{pmid}")]]
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"cmd_start: user_id={update.effective_user.id} (@{update.effective_user.username})")

    text = (
        "Вітаю. Я бот-дайджест новин УЗД-діагностики.\n\n"
        "Гурток біля заголовка — рівень доказовості (High / Medium / Low).\n"
        "Символ стетоскопа поряд — стаття практично застосовна на прийомі.\n\n"
        "Команди:\n"
        "/topics — список тем\n"
        "/topic <ключ> — останні статті за темою (напр. /topic thyroid)\n"
        "/search <слово> — пошук за ключовим словом\n"
        "/recent — останні опрацьовані статті\n"
        "/saved — ваші збережені статті (кнопка під постами в каналі)\n\n"
        f"Ваш Telegram ID: {update.effective_user.id} (для ADMIN_CHAT_ID)"
    )
    await update.message.reply_text(text)


async def cmd_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(list_topics_text(), parse_mode=ParseMode.HTML)


async def cmd_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Вкажіть ключ теми, напр.: <code>/topic thyroid</code>\nПовний список — /topics",
            parse_mode=ParseMode.HTML,
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

    await update.message.reply_text(f"{get_topic_label(topic_key)}:")
    for art in articles:
        await update.message.reply_text(
            format_article(art),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=save_button(art["pmid"]),
        )


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Вкажіть слово для пошуку, напр.: <code>/search РЧА</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    keyword = " ".join(context.args)
    results = db.search_articles(keyword, limit=10)
    if not results:
        await update.message.reply_text("Нічого не знайдено.")
        return

    safe_kw = html.escape(keyword)
    await update.message.reply_text(
        f"Результати за запитом «{safe_kw}»:", parse_mode=ParseMode.HTML
    )
    for art in results:
        await update.message.reply_text(
            format_article(art),
            parse_mode=ParseMode.HTML,
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
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=save_button(art["pmid"]),
        )


async def cmd_saved(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bookmarks = db.get_bookmarks(user_id, limit=30)
    if not bookmarks:
        await update.message.reply_text(
            "У вас поки немає збережених статей. Натискайте «Зберегти» під постами в каналі."
        )
        return

    lines = ["Ваші збережені статті:\n"]
    for b in bookmarks:
        title = html.escape(b["title"])
        url = html.escape(b["url"], quote=True)
        lines.append(f'• <a href="{url}">{title}</a>')
    await update.message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True
    )


async def handle_save_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    pmid = query.data.split(":", 1)[1]

    article = db.get_article_by_pmid(pmid)
    if not article:
        await query.answer("Статтю не знайдено в базі.", show_alert=True)
        return

    bookmark_title = article.get("title_ua") or article["title"]
    is_new = db.add_bookmark(query.from_user.id, pmid, bookmark_title, article["url"])
    if is_new:
        await query.answer(
            "Збережено. Перегляньте список командою /saved у приватному чаті з ботом.",
            show_alert=True,
        )
    else:
        await query.answer("Ця стаття вже у ваших збережених.", show_alert=True)


async def post_digest_to_channel(context: ContextTypes.DEFAULT_TYPE):
    """Публікує неопубліковані статті блоком під заголовком дня.

    - Заголовок дня — зі сповіщенням.
    - Самі статті — disable_notification=True.
    - Пауза POST_THROTTLE_SECONDS між постами — захист від flood-limit.
    """
    channel_id = os.environ["TELEGRAM_CHANNEL_ID"]
    pending = db.get_unposted_articles(limit=100)

    if not pending:
        return

    today_label = datetime.now().strftime("%d.%m.%Y")
    try:
        await context.bot.send_message(
            chat_id=channel_id,
            text=f"📅 <b>{today_label}</b>",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:  # noqa: BLE001
        print(f"Не вдалося опублікувати заголовок дня: {e}")

    for art in pending:
        try:
            await context.bot.send_message(
                chat_id=channel_id,
                text=format_article(art),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=save_button(art["pmid"]),
                disable_notification=True,
            )
            db.mark_posted(art["pmid"])
        except Exception as e:  # noqa: BLE001
            print(f"Не вдалося опублікувати статтю {art['pmid']}: {e}")
        await asyncio.sleep(POST_THROTTLE_SECONDS)


async def send_heartbeat(
    context: ContextTypes.DEFAULT_TYPE,
    total_new: int,
    pending: int = 0,
    failed: int = 0,
):
    admin_id = os.environ.get("ADMIN_CHAT_ID", "").strip()
    if not admin_id:
        return
    try:
        await context.bot.send_message(
            chat_id=admin_id,
            text=(
                f"Живий. Оброблено сьогодні: {total_new}. "
                f"Черга pending: {pending}, failed: {failed}."
            ),
            disable_notification=True,
        )
    except Exception as e:  # noqa: BLE001
        print(f"Не вдалося надіслати heartbeat адміну (ADMIN_CHAT_ID={admin_id}): {e}")
