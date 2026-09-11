# Шаблон-промпт для Sonnet 5 (для нової розмови, без історії цього чату)

Ідея: замість того, щоб тягнути весь контекст цього довгого чату в кожен новий запит,
вставляйте цей короткий "бриф" у СВІЖУ розмову — там уже є весь мінімум, потрібний
моделі, щоб згенерувати сумісний код без здогадок і без зайвих токенів на пояснення.

---

## Бриф проєкту (вставляти як є)

Проєкт: Telegram-бот на `python-telegram-bot` (async), публікує дайджест наукових
статей з ультразвукової діагностики (УЗД) з PubMed у Telegram-канал.

Файли й контракти між ними:

- **`summarizer.py`** — `summarize_article(title, abstract, journal) -> dict`.
  Викликає Anthropic API (гібридна схема: Haiku 4.5 для всіх статей, Sonnet 5 —
  додатково, якщо `practical_relevance` статті у списку `UPGRADE_PRACTICAL_LEVELS`,
  типово `High,Medium`). Повертає:
  `{"conclusion": str, "description": str, "evidence_level": "High"|"Medium"|"Low",
  "practical_relevance": "High"|"Medium"|"Low"}`.
  `evidence_level` = формальний дизайн дослідження (РКД/огляд/case report).
  `practical_relevance` = чи змінює стаття дії лікаря БЕЗПОСЕРЕДНЬО на прийомі
  (диф.-діагностичний критерій, порогове значення, пастка/артефакт, нова техніка) —
  це НЕ те саме, що evidence_level.

- **`db.py`** — SQLite (`usd_bot.db`), таблиця `articles` (pmid, topic_key, title,
  journal, pub_date, url, conclusion, description, evidence_level,
  practical_relevance, posted_to_channel, created_at) і `bookmarks`.
  `save_article(pmid, topic_key, title, journal, pub_date, url, conclusion,
  description, evidence_level, practical_relevance="Low")` — `INSERT OR IGNORE`.
  Усі getter'и роблять `SELECT *` → нові колонки підхоплюються автоматично.
  **База вже в проді** — будь-яка зміна схеми йде ЛИШЕ через `ALTER TABLE` з
  попередньою перевіркою `PRAGMA table_info(articles)`, ніколи `DROP`/`CREATE` наново.

- **`bot.py`** — `format_article(article: dict) -> str`, формує текст поста
  (**HTML**, `ParseMode.HTML` — НЕ Markdown, див. вимоги надійності нижче) для
  каналу й для команд `/topic`, `/search`, `/recent`, `/saved`.
  `LEVEL_DOT = {"High": "🟢", "Medium": "🟡", "Low": "🔴"}` — гурток доказовості.
  `PRACTICAL_BADGE = "🩺"`, показується поряд із гуртком, коли
  `practical_relevance` у `PRACTICAL_BADGE_LEVELS` (типово лише `("High",)`).

- **`scheduler.py`** — щоденна задача (`run_daily` у `main.py`, фіксований час за
  Europe/Kyiv): PubMed → `summarize_article` → `db.save_article` →
  `bot.post_digest_to_channel` → `bot.send_heartbeat`.

- **`fetcher.py`** — PubMed E-utilities (esearch/efetch), повертає лише
  title/abstract/journal/pub_date/url. Повний текст статей не використовується.

- **`config/topics.py`** — реєстр тем: `label`, `hashtag`, `query` (PubMed-запит).
  Зараз 24 теми. **Порядок словника має значення** — при перетині тем виграє та,
  що йде РАНІШЕ (глобальна унікальність pmid у БД).

## ⚠️ ОБОВ'ЯЗКОВІ вимоги надійності (не випливають із контрактів вище!)

Ці вимоги НЕ видно із самих сигнатур функцій, тому вже кілька разів губились при
ітераціях в окремих розмовах. Зберігайте їх при БУДЬ-ЯКІЙ зміні відповідних файлів:

- **bot.py**: `format_article()` і БУДЬ-ЯКИЙ текст, що містить дані з PubMed/Claude
  (title, conclusion, description, journal, pub_date, заголовки закладок у
  `cmd_saved`) — ЗАВЖДИ `ParseMode.HTML` + `html.escape()` на кожне динамічне поле.
  НІКОЛИ не Markdown: символи `_ * [ ] \`` у назвах статей з PubMed ламають legacy
  Markdown-парсер Telegram (`BadRequest: Can't parse entities`).
- **scheduler.py**: важка синхронна частина (PubMed `requests`, синхронний Anthropic
  SDK) — ЗАВЖДИ винесена в окрему `def` (не `async def`) і викликається через
  `await asyncio.to_thread(...)` з `check_and_process_new_articles`. Інакше event
  loop бота блокується на весь цикл перевірки, і команди `/topics`, `/search` не
  відповідають.
- **bot.py → post_digest_to_channel**: `disable_notification=True` для ВСІХ постів,
  крім заголовка дня; `await asyncio.sleep(1)` між постами (захист від Telegram
  flood-limit для каналів).
- **bot.py → send_heartbeat**: викликається в кінці `check_and_process_new_articles`
  (якщо `ADMIN_CHAT_ID` заданий у `.env`) — шле адміну "✅ Живий, оброблено N статей".
- **summarizer.py**: сирий текст винятку (`str(e)`, стектрейс) НІКОЛИ не потрапляє в
  текст, який публікується в канал — лише `print()` у консольний лог. Публічний
  текст при помилці — нейтральний ("⚠️ Не вдалося автоматично опрацювати цю
  статтю"). 1 повторна спроба (retry) для fast-моделі при тимчасовому збої мережі/API.
- **fetcher.py**: `sort=pub_date` (НЕ `most+recent` — невалідне значення для PubMed
  ESearch), `itertext()` (НЕ `.text` — губить текст після вкладених `<i>`/`<sub>`
  тегів у назвах/анотаціях), дедуп PMID через `list(dict.fromkeys(idlist))`.
- **main.py**: `load_dotenv()` — перший рядок виконуваного коду, до будь-яких
  локальних імпортів (`db`, `bot`, `scheduler`, `summarizer`). Якщо `summarizer.py`
  створює Anthropic-клієнт на рівні модуля — переконайтесь, що це lazy
  (`_get_client()` із перевіркою `if _client is None`), а не eager читання
  `os.environ["ANTHROPIC_API_KEY"]` прямо при імпорті.
- **db.py**: `add_bookmark()` повертає `bool` (`True` = новий запис, `False` = вже
  збережено раніше) — використовується в `handle_save_callback` для точнішого
  тексту відповіді користувачу.

## ЗАДАЧА

<!-- Опишіть тут одним-двома реченнями, що саме треба змінити або додати -->

## Вимоги до відповіді (для економії токенів)

- Виведи **лише змінені функції/фрагменти**, НЕ цілі файли, якщо зміна точкова.
- Без розлогих пояснень "чому" — одне коротке речення-коментар над кожною зміною.
- Якщо зачіпається SQLite-схема — обов'язково безпечна міграція
  (`PRAGMA table_info` перед `ALTER TABLE`), база вже містить реальні дані.
- Українські докстрінги/коментарі — залишай українською, у тому ж стилі, що і зараз.
- Якщо додаєш нову змінну середовища — допиши рядок і коментар до неї в стилі
  наявного `.env.example`.
- Перед тим як віддати відповідь — звір її з розділом "⚠️ ОБОВ'ЯЗКОВІ вимоги
  надійності" вище: чи не порушує зміна щось із переліченого.
