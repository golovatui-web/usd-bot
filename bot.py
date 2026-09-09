"""
Обробники команд Telegram-бота + функція публікації дайджесту в канал.
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
# Бейдж "практично важливо" — показуємо лише для practical_relevance == "High", щоб він
# лишався рідкісним і справді привертав увагу (не для "Medium", інакше знецінюється).
# Якщо захочете показувати і для Medium — розширте PRACTICAL_BADGE_LEVELS нижче.
PRACTICAL_BADGE_LEVELS = ("High",)
PRACTICAL_BADGE = "🩺"

POST_THROTTLE_SECONDS = 1  # пауза між постами в канал — захист від Telegram flood-limit


def format_article(article: dict) -> str:
    """Формат: [гурток доказовості + бейдж практичної цінності] заголовок, потім
    висновок (виділено), опис, доказовість — кольором, практична цінність — бейджем.

    ParseMode.HTML + html.escape() для всіх полів, що приходять із зовнішнього джерела
    (PubMed) або від Claude — без цього символи типу _ * [ ] у назві статті ламають
    legacy Markdown-парсер Telegram (BadRequest: Can't parse entities).
    """
    dot = LEVEL_DOT.get(article["evidence_level"], "⚪")
    if article.get("practical_relevance") in PRACTICAL_BADGE_LEVELS:
        prefix = f"{dot} {PRACTICAL_BADGE}"
    else:
        prefix = dot
    hashtag = get_topic_hashtag(article.get("topic_key", ""))

    title = html.escape(article["title"])
    conclusion = html.escape(article["conclusion"])
    description = html.escape(article["description"])
    journal = html.escape(article.get("journal") or "")
    pub_date = html.escape(str(article.get("pub_date") or ""))
    url = html.escape(article["url"], quote=True)

    return (
        f"{prefix} <b>{title}</b>\n\n"
        f"💡 <b>{conclusion}</b>\n\n"
        f"{description}\n\n"
        f"{hashtag}\n"
        f'🔗 <a href="{url}">Джерело</a> · {journal}, {pub_date}'
    )


def save_button(pmid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔖 Зберегти", callback_data=f"save:{pmid}")]]
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Друкуємо user_id в лог — щоб адміну було легко знайти свій ID для ADMIN_CHAT_ID
    # (heartbeat-налаштування), не встановлюючи окремих сторонніх ботів.
    print(f"cmd_start: user_id={update.effective_user.id} (@{update.effective_user.username})")

    text = (
        "👋 Вітаю! Я бот-дайджест новин УЗД-діагностики.\n\n"
        "🩺 поряд із гуртком = стаття практично застосовна на прийомі.\n\n"
        "Команди:\n"
        "/topics — список тем\n"
        "/topic <ключ> — останні статті за темою (напр. /topic thyroid)\n"
        "/search <слово> — пошук за ключовим словом\n"
        "/recent — останні опрацьовані статті за всіма темами\n"
        "/saved — ваші збережені статті (натискайте 🔖 під постами в каналі)\n\n"
        f"Ваш Telegram ID: {update.effective_user.id} (знадобиться для ADMIN_CHAT_ID, якщо це ви)"
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

    await update.message.reply_text(f"📚 {get_topic_label(topic_key)}:")
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
            "Вкажіть слово для пошуку, напр.: <code>/search РЧА</code>", parse_mode=ParseMode.HTML
        )
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
            "У вас поки немає збережених статей. Натискайте 🔖 «Зберегти» під постами в каналі."
        )
        return

    lines = ["🔖 Ваші збережені статті:\n"]
    for b in bookmarks:
        title = html.escape(b["title"])
        url = html.escape(b["url"], quote=True)
        lines.append(f'• <a href="{url}">{title}</a>')
    await update.message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True
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

    is_new = db.add_bookmark(query.from_user.id, pmid, article["title"], article["url"])
    if is_new:
        await query.answer(
            "🔖 Збережено! Перегляньте список командою /saved у приватному чаті з ботом.",
            show_alert=True,
        )
    else:
        await query.answer("Ця стаття вже у ваших збережених.", show_alert=True)


async def post_digest_to_channel(context: ContextTypes.DEFAULT_TYPE):
    """Публікує в канал усі ще не опубліковані статті одним блоком під заголовком дня.
    Викликається планувальником (main.py) раз на день.

    - Заголовок дня надсилається зі звуковим сповіщенням (це і є сигнал "дайджест готовий").
    - Самі статті — БЕЗ сповіщення (disable_notification=True), щоб 20-40 постів поспіль
      не завалили підписників пушами й не спричинили масові відписки.
    - Пауза між постами (POST_THROTTLE_SECONDS) — захист від Telegram flood-limit для
      каналів (орієнтовно безпечно до ~20 повідомлень/хв).
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


async def send_heartbeat(context: ContextTypes.DEFAULT_TYPE, total_new: int):
    """Раз на день шле адміну коротке підтвердження, що бот живий і скільки нового
    опрацьовано. Якщо ADMIN_CHAT_ID не задано — просто нічого не робить (не обов'язково).
    Якщо бот "зациклено падає" (наприклад, скінчився баланс Anthropic) — це помітно
    одразу з відсутності heartbeat, а не через тижні мовчазної тиші в каналі."""
    admin_id = os.environ.get("ADMIN_CHAT_ID", "").strip()
    if not admin_id:
        return
    try:
        await context.bot.send_message(
            chat_id=admin_id,
            text=f"✅ Живий. Оброблено нових статей сьогодні: {total_new}.",
            disable_notification=True,
        )
    except Exception as e:  # noqa: BLE001
        print(f"Не вдалося надіслати heartbeat адміну (ADMIN_CHAT_ID={admin_id}): {e}")
