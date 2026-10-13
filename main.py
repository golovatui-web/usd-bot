"""
Точка входу. Запускає Telegram-бота і три фонові задачі:
  - фідер PubMed (round-robin кожні 15 хв)
  - AI-воркер черги (1 стаття / ~15 с, з паузою 6 с між викликами Gemini)
  - щоденна публікація дайджесту о DIGEST_HOUR_KYIV за Києвом

Запуск: python main.py
"""

from dotenv import load_dotenv

load_dotenv()

import datetime as dt
import os
from zoneinfo import ZoneInfo

from telegram.ext import Application, CallbackQueryHandler, CommandHandler

import db
from bot import (
    cmd_recent,
    cmd_saved,
    cmd_search,
    cmd_start,
    cmd_topic,
    cmd_topics,
    handle_save_callback,
)
from scheduler import feed_pubmed_round_robin, process_queue_tick, publish_digest_and_heartbeat

REQUIRED_ENV_VARS = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHANNEL_ID", "GEMINI_API_KEY"]


def check_env():
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        raise SystemExit(
            f"Не заповнені обов'язкові змінні середовища: {', '.join(missing)}.\n"
            f"Перевірте файл .env (див. .env.example).\n"
            f"Ключ Gemini: https://aistudio.google.com/apikey"
        )


def main():
    check_env()
    db.init_db()

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    digest_hour = int(os.environ.get("DIGEST_HOUR_KYIV", "8"))
    feed_minutes = int(os.environ.get("FEED_INTERVAL_MINUTES", "15"))
    worker_seconds = int(os.environ.get("WORKER_INTERVAL_SECONDS", "15"))

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("topics", cmd_topics))
    application.add_handler(CommandHandler("topic", cmd_topic))
    application.add_handler(CommandHandler("search", cmd_search))
    application.add_handler(CommandHandler("recent", cmd_recent))
    application.add_handler(CommandHandler("saved", cmd_saved))
    application.add_handler(CallbackQueryHandler(handle_save_callback, pattern=r"^save:"))

    jq = application.job_queue
    jq.run_repeating(
        feed_pubmed_round_robin,
        interval=dt.timedelta(minutes=feed_minutes),
        first=20,
        name="pubmed_feeder",
    )
    jq.run_repeating(
        process_queue_tick,
        interval=dt.timedelta(seconds=worker_seconds),
        first=40,
        name="gemini_worker",
    )
    jq.run_daily(
        publish_digest_and_heartbeat,
        time=dt.time(hour=digest_hour, minute=0, tzinfo=ZoneInfo("Europe/Kyiv")),
        name="daily_digest",
    )

    print(
        f"Бот запущено. Фідер кожні {feed_minutes} хв, воркер кожні {worker_seconds} с, "
        f"дайджест о {digest_hour}:00 за Києвом."
    )
    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
