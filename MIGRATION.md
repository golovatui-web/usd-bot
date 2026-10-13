# Покрокова заміна Anthropic → Gemini

Робити на сервері, де вже крутиться бот (Oracle Cloud / systemd `usd-bot`).
Базу `usd_bot.db` **не видаляти**.

Нижче шлях `/home/ubuntu/ВАШ_РЕПОЗИТОРІЙ` замініть на реальну папку
(ту, що в `WorkingDirectory` юніта `usd-bot.service`).

---

## 0. Ключ Gemini (з комп'ютера, у браузері)

1. Відкрийте https://aistudio.google.com/apikey
2. Увійдіть Google-акаунтом → **Create API key**
3. Скопіюйте ключ. Картка не потрібна.

---

## 1. Зайти на сервер і зупинити бота

```bash
ssh -i ваш-ключ.key ubuntu@ВАШ_PUBLIC_IP
cd ~/ВАШ_РЕПОЗИТОРІЙ
sudo systemctl stop usd-bot
```

## 2. Резервна копія бази (обов'язково)

```bash
cp usd_bot.db ~/backups/usd_bot_before_gemini_$(date +%F).db
ls -lh usd_bot.db ~/backups/
```

Якщо папки `~/backups` немає: `mkdir -p ~/backups` і повторіть `cp`.

## 3. Покласти нові файли

Розпакуйте `usd-digest-bot.zip` **у папку бота** (файли мають лягти поруч
із `main.py` і `usd_bot.db`, а `topics.py` — у `config/`).

Приклад, якщо zip лежить у домашній папці:

```bash
cd ~/ВАШ_РЕПОЗИТОРІЙ
unzip -o ~/usd-digest-bot.zip
# якщо unzip створив підпапку:
cp -r usd-digest-bot/. .
```

Або скопіюйте файли вручну. Має з'явитись / оновитись:

| Файл | Дія |
|---|---|
| `gemini_service.py` | новий (замість Claude) |
| `worker.py` | новий (черга 24/7) |
| `config/topics.py` | замінити (25 MeSH-тем) |
| `config/__init__.py` | новий, якщо немає |
| `db.py` | замінити |
| `fetcher.py` | замінити |
| `bot.py` | замінити |
| `scheduler.py` | замінити |
| `main.py` | замінити |
| `seed_new_topics.py` | замінити |
| `requirements.txt` | замінити |
| `.env.example` | замінити |

**Видалити старий модуль Claude:**

```bash
rm -f summarizer.py
```

`usd_bot.db` і `.env` не чіпати на цьому кроці.

## 4. Оновити Python-залежності

```bash
source venv/bin/activate
pip install -r requirements.txt
```

Мають з'явитись пакети `google-genai`, `pydantic`, `tenacity`.
Пакет `anthropic` більше не потрібен.

## 5. Відредагувати `.env`

```bash
nano .env
```

**Прибрати** рядок:

```
ANTHROPIC_API_KEY=...
```

**Додати** (вставте свій ключ):

```
GEMINI_API_KEY=ваш_ключ_з_aistudio
```

**Додати в кінець файлу**, якщо цих рядків ще немає (можна скопіювати з `.env.example`):

```
SUMMARIZER_FAST_MODEL=gemini-2.5-flash
SUMMARIZER_PREMIUM_MODEL=gemini-2.5-pro
ENABLE_PREMIUM_UPGRADE=true
UPGRADE_PRACTICAL_LEVELS=High,Medium
UPGRADE_EVIDENCE_LEVELS=
MAX_PREMIUM_PER_DAY=40
GEMINI_CALL_GAP_SECONDS=6
FEED_TOPICS_PER_TICK=3
FEED_INTERVAL_MINUTES=15
WORKER_INTERVAL_SECONDS=15
MAX_QUEUE_ATTEMPTS=3
```

`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`, `ADMIN_CHAT_ID`, `NCBI_API_KEY`,
`DIGEST_HOUR_KYIV`, `LOOKBACK_DAYS` — лишити як були.

Зберегти: `Ctrl+O`, `Enter`, вийти: `Ctrl+X`.

## 6. Тестовий запуск (30 секунд)

```bash
source venv/bin/activate
python3 main.py
```

Має з'явитись рядок на кшталт:

`Бот запущено. Фідер кожні 15 хв, воркер кожні 15 с, дайджест о 8:00 за Києвом.`

У Telegram напишіть боту `/start` і `/topics` — має відповісти, у списку
вже 25 тем. Зупиніть тест: `Ctrl+C`.

Якщо падає з `GEMINI_API_KEY` — крок 5 не збережено або ключ порожній.

## 7. Засіяти нові теми (один раз)

Інакше перший прохід по `lung_pocus` / `ceus` / `elastography` / `ai_tech`
знайде старі статті і спробує всі прогнати через Gemini.

```bash
source venv/bin/activate
python3 seed_new_topics.py
```

Дочекайтесь `Готово. Всього позначено: N`. Потім файл можна не чіпати.

## 8. Увімкнути службу знову

```bash
sudo systemctl start usd-bot
sudo systemctl status usd-bot
journalctl -u usd-bot -n 40 --no-pager
```

У статусі має бути `active (running)`. У логах — без `ANTHROPIC` / `summarizer.py`.

---

## Перевірка наступного ранку

- У каналі дайджест як раніше (заголовок дня + пости без пушів).
- Вам у приват (якщо є `ADMIN_CHAT_ID`): `Живий. Оброблено сьогодні: N. Черга pending: X, failed: Y.`
- Логи: `journalctl -u usd-bot -f`

## Якщо щось пішло не так

| Симптом | Що зробити |
|---|---|
| Бот не стартує, `GEMINI_API_KEY` | Перевірити `.env`, без лапок-пробілів навколо ключа |
| `ModuleNotFoundError: google` | `source venv/bin/activate && pip install -r requirements.txt` |
| Дублікати в каналі | Відновити `usd_bot.db` з `~/backups/` |
| Квота Pro / 429 у логах | У `.env`: `ENABLE_PREMIUM_UPGRADE=false`, потім `sudo systemctl restart usd-bot` |
| Команди `/topics` зависають | Переконайтесь, що стоїть **новий** `scheduler.py` (робота через `asyncio.to_thread`) |

Відкат: зупинити службу, повернути старі файли + `usd_bot.db` з бекапу, `pip install anthropic`, повернути `ANTHROPIC_API_KEY`, старт.
