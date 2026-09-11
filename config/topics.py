"""
Реєстр тем бота.

Кожна тема має:
- label: назва українською, яку бачить користувач
- query: пошуковий запит PubMed (мова PubMed — англійська)
- hashtag: хештег, що додається до кожного поста в каналі (для навігації історією/пошуку
  прямо всередині Telegram-каналу — клік на хештег відкриває пошук по каналу)

Щоб додати/змінити тему — просто відредагуйте цей словник.
Ключ теми (наприклад "thyroid") використовується як ідентифікатор у командах бота
та в базі даних, тому після першого запуску краще не перейменовувати ключі.

Порядок словника МАЄ значення: при перетині тем (одна стаття підходить під кілька
запитів) виграє та, що йде РАНІШЕ в цьому переліку (глобальна унікальність pmid —
див. коментар у scheduler.py). Тому органо-специфічні теми йдуть перед "наскрізними"
(pediatric, oncology, acute_emergency) — щоб, наприклад, стаття про пухлину печінки
отримала хештег #печінка, а не #онкологія.

21 тема (скорочено з 24: прибрано ceus/elastography/lung_pocus — надто вузькі за
обсягом публікацій для щоденного дайджесту; можна повернути пізніше, якщо захочете).
"""

TOPICS = {
    # ==================== Основні ====================
    "thyroid": {
        "label": "Щитоподібна залоза",
        "hashtag": "#щитоподібна",
        "query": (
            '"thyroid"[Title/Abstract] AND '
            '(ultrasound[Title/Abstract] OR "fine needle"[Title/Abstract] OR biopsy[Title/Abstract] '
            'OR "radiofrequency ablation"[Title/Abstract] OR TIRADS[Title/Abstract])'
        ),
    },
    "breast_lymph": {
        "label": "Молочні залози та лімфовузли",
        "hashtag": "#молочна_залоза",
        "query": (
            '(breast[Title/Abstract] OR "lymph node"[Title/Abstract] OR axillary[Title/Abstract]) '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract] OR biopsy[Title/Abstract] '
            'OR "core needle"[Title/Abstract])'
        ),
    },
    "abdomen": {
        "label": "Черевна порожнина (загальне)",
        "hashtag": "#черевна_порожнина",
        # NOT liver/kidney/pancreas — щоб не дублювати їхні окремі теми нижче
        # (без цього виключення "abdominal ultrasound" ловило б майже все підряд).
        "query": (
            '(abdomen[Title/Abstract] OR abdominal[Title/Abstract] OR "acute abdomen"[Title/Abstract] '
            'OR spleen[Title/Abstract] OR splenic[Title/Abstract]) '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract]) '
            'NOT (liver[Title/Abstract] OR hepatic[Title/Abstract] OR kidney[Title/Abstract] '
            'OR renal[Title/Abstract] OR pancreas[Title/Abstract] OR pancreatic[Title/Abstract])'
        ),
    },
    "liver": {
        "label": "Печінка",
        "hashtag": "#печінка",
        "query": (
            '(liver[Title/Abstract] OR hepatic[Title/Abstract] OR "fatty liver"[Title/Abstract] '
            'OR cirrhosis[Title/Abstract] OR steatosis[Title/Abstract] '
            'OR "hepatocellular carcinoma"[Title/Abstract]) '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract] OR elastography[Title/Abstract])'
        ),
    },
    "kidney": {
        "label": "Нирки",
        "hashtag": "#нирки",
        "query": (
            '(kidney[Title/Abstract] OR renal[Title/Abstract] OR "renal artery"[Title/Abstract] '
            'OR nephrolithiasis[Title/Abstract] OR hydronephrosis[Title/Abstract]) '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract] OR doppler[Title/Abstract])'
        ),
    },
    "gynecology": {
        "label": "Гінекологія",
        "hashtag": "#гінекологія",
        "query": (
            '(gynecologic[Title/Abstract] OR gynecological[Title/Abstract] OR pelvic[Title/Abstract] '
            'OR ovarian[Title/Abstract] OR uterine[Title/Abstract] OR endometrial[Title/Abstract]) '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract])'
        ),
    },
    "obstetrics": {
        "label": "Акушерство",
        "hashtag": "#акушерство",
        "query": (
            '(obstetric[Title/Abstract] OR fetal[Title/Abstract] OR prenatal[Title/Abstract] '
            'OR "fetal biometry"[Title/Abstract] OR "nuchal translucency"[Title/Abstract] '
            'OR pregnancy[Title/Abstract]) '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract])'
        ),
    },
    "urology": {
        "label": "Урологія",
        "hashtag": "#урологія",
        "query": (
            '(urologic[Title/Abstract] OR urological[Title/Abstract] OR prostate[Title/Abstract] '
            'OR bladder[Title/Abstract] OR scrotal[Title/Abstract] OR testicular[Title/Abstract]) '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract])'
        ),
    },
    "vessels": {
        "label": "Судини шиї і голови",
        "hashtag": "#судини_шиї",
        "query": (
            '("carotid artery"[Title/Abstract] OR "vertebral artery"[Title/Abstract] '
            'OR "neck vessels"[Title/Abstract] OR "transcranial doppler"[Title/Abstract] '
            'OR "carotid stenosis"[Title/Abstract]) '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract] OR doppler[Title/Abstract])'
        ),
    },
    "guidelines": {
        "label": "Рекомендації асоціацій (EFSUMB/AIUM/ESR/ACR)",
        "hashtag": "#рекомендації",
        "query": (
            '(guideline[Title/Abstract] OR guidelines[Title/Abstract] OR recommendation*[Title/Abstract] '
            'OR consensus[Title/Abstract] OR "practice parameter"[Title/Abstract]) '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract])'
        ),
    },

    # ==================== Цінні доповнення ====================
    "vascular": {
        "label": "Периферичні судини",
        "hashtag": "#периферичні_судини",
        "query": (
            '("deep vein thrombosis"[Title/Abstract] OR "venous insufficiency"[Title/Abstract] '
            'OR "peripheral artery disease"[Title/Abstract] OR "peripheral vascular"[Title/Abstract] '
            'OR "lower limb ischemia"[Title/Abstract] OR varicose[Title/Abstract]) '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract] OR duplex[Title/Abstract])'
        ),
    },
    "msk": {
        "label": "Опорно-рухова система",
        "hashtag": "#опорно_руховий",
        "query": (
            '(musculoskeletal[Title/Abstract] OR tendon[Title/Abstract] OR ligament[Title/Abstract] '
            'OR "rotator cuff"[Title/Abstract] OR joint[Title/Abstract] OR muscle[Title/Abstract]) '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract] OR sonography[Title/Abstract])'
        ),
    },
    "soft_tissue": {
        "label": "М'які тканини",
        "hashtag": "#мякі_тканини",
        "query": (
            '"soft tissue"[Title/Abstract] '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract])'
        ),
    },
    "reproduction": {
        "label": "Репродуктологія",
        "hashtag": "#репродуктологія",
        "query": (
            '(reproductive[Title/Abstract] OR infertility[Title/Abstract] OR fertility[Title/Abstract] '
            'OR "in vitro fertilization"[Title/Abstract] OR follicular[Title/Abstract] '
            'OR "ovarian reserve"[Title/Abstract]) '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract])'
        ),
    },
    "pancreas_gi": {
        "label": "Підшлункова залоза та ШКТ",
        "hashtag": "#підшлункова_шкт",
        "query": (
            '(pancreas[Title/Abstract] OR pancreatic[Title/Abstract] OR "gastrointestinal tract"[Title/Abstract] '
            'OR bowel[Title/Abstract] OR intestinal[Title/Abstract] OR appendicitis[Title/Abstract]) '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract])'
        ),
    },
    "oncology": {
        "label": "Онкологічне УЗД",
        "hashtag": "#онкологія",
        "query": (
            '(oncology[Title/Abstract] OR oncologic[Title/Abstract] OR tumor[Title/Abstract] '
            'OR malignancy[Title/Abstract] OR metastasis[Title/Abstract] OR "cancer screening"[Title/Abstract]) '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract] '
            'OR "contrast-enhanced ultrasound"[Title/Abstract])'
        ),
    },
    "acute_emergency": {
        "label": "Невідкладне УЗД",
        "hashtag": "#невідкладна_допомога",
        "query": (
            '(emergency[Title/Abstract] OR "point-of-care"[Title/Abstract] OR POCUS[Title/Abstract] '
            'OR trauma[Title/Abstract] OR FAST[Title/Abstract]) '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract] OR sonography[Title/Abstract])'
        ),
    },

    # ==================== Нішеві ====================
    "peripheral_nerves": {
        "label": "Периферичні нерви",
        "hashtag": "#периферичні_нерви",
        "query": (
            '("peripheral nerve"[Title/Abstract] OR "nerve entrapment"[Title/Abstract] '
            'OR "carpal tunnel"[Title/Abstract] OR neuropathy[Title/Abstract]) '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract] OR sonography[Title/Abstract])'
        ),
    },
    "pediatric": {
        "label": "Педіатричне УЗД",
        "hashtag": "#педіатрія",
        "query": (
            '(pediatric[Title/Abstract] OR paediatric[Title/Abstract] OR infant[Title/Abstract] '
            'OR neonatal[Title/Abstract]) '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract] OR sonography[Title/Abstract])'
        ),
    },
    "salivary": {
        "label": "Слинні залози",
        "hashtag": "#слинні_залози",
        "query": (
            '"salivary gland"[Title/Abstract] '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract])'
        ),
    },
    "head_neck": {
        "label": "Голова та шия (інше)",
        "hashtag": "#голова_шия",
        "query": (
            '(parathyroid[Title/Abstract] OR larynx[Title/Abstract] OR laryngeal[Title/Abstract] '
            'OR "cervical lymph node"[Title/Abstract] OR "neck mass"[Title/Abstract]) '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract])'
        ),
    },
}


def get_topic_label(topic_key: str) -> str:
    topic = TOPICS.get(topic_key)
    return topic["label"] if topic else topic_key


def get_topic_hashtag(topic_key: str) -> str:
    topic = TOPICS.get(topic_key)
    return topic["hashtag"] if topic else "#узд"


def list_topics_text() -> str:
    """Форматований список тем для команди /topics у боті (HTML — узгоджено з форматом
    format_article у bot.py, щоб не змішувати різні parse_mode в одному боті)."""
    lines = ["📋 Доступні теми:\n"]
    for key, data in TOPICS.items():
        lines.append(f"• <code>{key}</code> — {data['label']}")
    lines.append("\nПриклад: <code>/topic thyroid</code>")
    return "\n".join(lines)
