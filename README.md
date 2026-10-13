# УЗД-Дайджест — Telegram-бот (Gemini, безкоштовний тариф)

Бот стежить за новими статтями в PubMed за 25 темами ультразвукової діагностики,
генерує коротку анотацію українською через **Gemini API (безкоштовний тариф
Google AI Studio)**, оцінює рівень доказовості та практичну цінність і публікує
дайджест у Telegram-канал.

**Що змінилось порівняно з версією на Anthropic**

- Claude → Gemini 2.5 Flash + Pro. Витрати на AI: **$0**.
- Запити PubMed переписані на **MeSH + [tiab] + [pt]**, з автоматичним фільтром
  `("Ultrasonography"[Mesh] OR "ultrasound"[tiab] OR "sonography"[tiab])`.
- Навантаження розмазане на добу: фідер кожні 15 хв бере 3 теми, воркер
  обробляє **1 статтю за раз** з паузою 6 с між викликами API (≈10 RPM,
  нижче ліміту free-tier). 429 → паузи 15 / 30 / 60 с.
- Щоденна публікація в канал лишилась: статті накопичуються в черзі й
  виходять о `DIGEST_HOUR_KYIV` одним блоком.

**Джерело даних:** офіційні анотації PubMed. Повні тексти не завантажуються.

---

## Міграція з Anthropic (якщо бот уже працює)

1. Зробіть копію `usd_bot.db` (інакше втратите історію PMID і почнете
   дублювати пости).
2. Замініть файли проєкту на цю версію. Схему БД **не дропайте** —
   `db.init_db()` сам додасть колонки `title_ua`, `summary_ua`,
   `evidence_justification`, `clinical_takeaway` і таблицю `article_queue`.
3. У `.env` замініть `ANTHROPIC_API_KEY` на `GEMINI_API_KEY`
   (ключ з https://aistudio.google.com/apikey). Решту змінних можна
   скопіювати з `.env.example`.
4. `source venv/bin/activate && pip install -r requirements.txt`
5. `sudo systemctl restart usd-bot`
6. Один раз запустіть `python seed_new_topics.py` — щоб нові теми
   (lung_pocus, ceus, elastography, ai_tech) не вилили історичний беклог
   у канал і не спалили денну квоту Gemini.

---

## Крок 1. Telegram-бот і канал

Як раніше: @BotFather → токен; канал → бот як адміністратор; ID каналу
в `TELEGRAM_CHANNEL_ID`.

## Крок 2. Безкоштовний ключ Gemini

1. https://aistudio.google.com/apikey → Create API key.
2. Картка не обов'язкова. Ліміти (RPM/RPD) дивіться в AI Studio для
   свого проєкту — вони не публікуються як гарантія, тому бот навмисно
   ходить повільно (6 с між викликами, 3 теми / 15 хв, max 40 статей/день).
3. Типові орієнтири free-tier: Flash ≈ 10 RPM / ~250 RPD, Pro ≈ 5 RPM /
   ~50–100 RPD. Pro викликається лише для статей з `practical_relevance`
   High або Medium.

Якщо Pro-квота кінчається — поставте `ENABLE_PREMIUM_UPGRADE=false`
(усі статті лишаються на Flash) або зменшіть `MAX_PREMIUM_PER_DAY`.

## Крок 3. NCBI-ключ (бажано)

https://www.ncbi.nlm.nih.gov/account/settings/ → API Key Management.

## Крок 4. Хостинг (Oracle Cloud Always Free) — без змін

Код як і раніше крутиться на VM. Коротко:

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env          # TELEGRAM_*, GEMINI_API_KEY, канал
python3 main.py    # тест, Ctrl+C
```

systemd-юніт той самий (`ExecStart=.../python3 .../main.py`).
Логи: `journalctl -u usd-bot -f`.

---

## Як це працює (24/7 pacing)

```
PubMed feeder (кожні 15 хв, 3 теми round-robin)
        ↓ нові PMID
article_queue (status=pending)
        ↓ воркер, 1 стаття, sleep 6 с
Gemini Flash  →  (якщо варто)  Gemini Pro
        ↓
articles (ще не posted)
        ↓ о DIGEST_HOUR_KYIV
канал + heartbeat адміну
```

Команди бота в приваті: `/topics`, `/topic thyroid`, `/search`, `/recent`, `/saved`.

Шкала доказовості — кольоровий гурток. Бейдж стетоскопа — `practical_relevance=High`.

---

## Теми (25)

Органо-специфічні йдуть першими, щоб при перетині pmid «вигравала» вужча тема:
щитоподібна, молочна/лімфовузли, живіт, печінка, нирки, підшлункова/ШКТ,
гінекологія, акушерство, репродуктологія, урологія, судини шиї, периферичні
судини, ОРС, м'які тканини, периферичні нерви, слинні, голова/шия, легені/POCUS,
CEUS, еластографія, педіатрія, онкологія, невідкладна, ШІ, рекомендації.

Щоб додати тему — рядок у `config/topics.py` (`label`, `hashtag`, `query` без
ультразвукового фільтра: його додає `fetcher.compose_pubmed_query`).

---

## Вартість

- Хостинг Oracle Always Free: $0
- PubMed: $0
- Gemini free tier: $0 (ліміт — RPM/RPD, не гроші)

Разом: **$0/міс**, якщо тримати `MAX_ARTICLES_PER_DAY` і паузи як у `.env.example`.
