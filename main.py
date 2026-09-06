"""
Точка входу. Запускає:
  1. Telegram-бота (обробка команд у приватних чатах)
  2. Фонову періодичну задачу (перевірка PubMed + анотування + публікація в канал)

Запуск: python main.py
"""

import os
from datetime import timedelta

from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler

import db
from bot import cmd_start, cmd_topics, cmd_topic, cmd_search, cmd_recent
from scheduler import check_and_process_new_articles

load_dotenv()

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
    interval_hours = float(os.environ.get("CHECK_INTERVAL_HOURS", 12))

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("теми", cmd_topics))
    application.add_handler(CommandHandler("тема", cmd_topic))
    application.add_handler(CommandHandler("пошук", cmd_search))
    application.add_handler(CommandHandler("останні", cmd_recent))

    # перша перевірка через 15 секунд після старту, далі — кожні CHECK_INTERVAL_HOURS годин
    application.job_queue.run_repeating(
        check_and_process_new_articles,
        interval=timedelta(hours=interval_hours),
        first=15,
    )

    print("Бот запущено. Очікую на команди та виконую періодичні перевірки...")
    application.run_polling(allowed_updates=[])


if __name__ == "__main__":
    main()
