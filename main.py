"""
Точка входу. Запускає:
  1. Telegram-бота (обробка команд у приватних чатах)
  2. Фонову періодичну задачу (перевірка PubMed + анотування + публікація в канал)
     раз на день, у фіксований час за київським часом.

Запуск: python main.py
"""

# load_dotenv() МАЄ бути першим — до будь-яких локальних імпортів (db, bot, scheduler).
# Причина: summarizer.py створює Anthropic-клієнт ОДИН РАЗ на рівні модуля і читає
# ANTHROPIC_API_KEY з os.environ вже під час імпорту. Якби load_dotenv() викликався
# після імпортів (як раніше), ключа ще не було б у середовищі — і імпорт впав би
# з KeyError ще до старту програми.
from dotenv import load_dotenv

load_dotenv()

import datetime as dt
import os
from zoneinfo import ZoneInfo

from telegram.ext import Application, CallbackQueryHandler, CommandHandler

import db
from bot import (
    cmd_start,
    cmd_topics,
    cmd_topic,
    cmd_search,
    cmd_recent,
    cmd_saved,
    handle_save_callback,
)
from scheduler import check_and_process_new_articles

REQUIRED_ENV_VARS = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHANNEL_ID", "ANTHROPIC_API_KEY"]


def check_env():
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        raise SystemExit(
            f"Не заповнені обов'язкові змінні середовища: {', '.join(missing)}.\n"
            f"Перевірте файл .env (див. .env.example)."
        )


def main():
    check_env()
    db.init_db()

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    digest_hour = int(os.environ.get("DIGEST_HOUR_KYIV", 8))

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("topics", cmd_topics))
    application.add_handler(CommandHandler("topic", cmd_topic))
    application.add_handler(CommandHandler("search", cmd_search))
    application.add_handler(CommandHandler("recent", cmd_recent))
    application.add_handler(CommandHandler("saved", cmd_saved))
    application.add_handler(CallbackQueryHandler(handle_save_callback, pattern=r"^save:"))

    # Фіксований час щодня за київським часом (а не "кожні 24 год від старту сервісу") —
    # так дата в заголовку дня в каналі й сам час публікації не "пливуть" після кожного
    # рестарту/деплою/збою, і не залежать від того, в якому часовому поясі працює сервер
    # (Oracle Cloud VM зазвичай у UTC).
    application.job_queue.run_daily(
        check_and_process_new_articles,
        time=dt.time(hour=digest_hour, minute=0, tzinfo=ZoneInfo("Europe/Kyiv")),
    )

    print(f"Бот запущено. Щоденна перевірка о {digest_hour}:00 за Києвом. Очікую на команди...")
    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
