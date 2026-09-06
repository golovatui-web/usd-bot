"""
Реєстр тем бота.

Кожна тема має:
- label: назва українською, яку бачить користувач
- query: пошуковий запит PubMed (мова PubMed — англійська, тому запити англійською,
         навіть якщо весь інтерфейс бота українською)

Щоб додати/змінити тему — просто відредагуйте цей словник.
Ключ теми (наприклад "thyroid") використовується як ідентифікатор у командах бота
та в базі даних, тому після першого запуску краще не перейменовувати ключі.
"""

TOPICS = {
    "vessels": {
        "label": "Судини шиї і голови",
        "query": (
            '("carotid artery"[Title/Abstract] OR "vertebral artery"[Title/Abstract] '
            'OR "neck vessels"[Title/Abstract] OR "transcranial doppler"[Title/Abstract] '
            'OR "carotid stenosis"[Title/Abstract]) '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract] OR doppler[Title/Abstract])'
        ),
    },
    "soft_tissue": {
        "label": "М'які тканини",
        "query": (
            '"soft tissue"[Title/Abstract] '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract])'
        ),
    },
    "salivary": {
        "label": "Слинні залози",
        "query": (
            '"salivary gland"[Title/Abstract] '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract])'
        ),
    },
    "thyroid": {
        "label": "Щитоподібна залоза (вузли, біопсія, РЧА)",
        "query": (
            '"thyroid"[Title/Abstract] AND '
            '(ultrasound[Title/Abstract] OR "fine needle"[Title/Abstract] OR biopsy[Title/Abstract] '
            'OR "radiofrequency ablation"[Title/Abstract] OR TIRADS[Title/Abstract])'
        ),
    },
    "breast_lymph": {
        "label": "Молочні залози, лімфатичні вузли, біопсії",
        "query": (
            '(breast[Title/Abstract] OR "lymph node"[Title/Abstract] OR axillary[Title/Abstract]) '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract] OR biopsy[Title/Abstract] '
            'OR "core needle"[Title/Abstract])'
        ),
    },
    "abdomen_kidney": {
        "label": "Черевна порожнина, нирки",
        "query": (
            '(abdomen[Title/Abstract] OR abdominal[Title/Abstract] OR kidney[Title/Abstract] '
            'OR renal[Title/Abstract] OR hepatic[Title/Abstract] OR liver[Title/Abstract]) '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract])'
        ),
    },
    "acute_onco": {
        "label": "Гострі та онкологічні захворювання",
        "query": (
            '(acute[Title/Abstract] OR oncology[Title/Abstract] OR oncologic[Title/Abstract] '
            'OR tumor[Title/Abstract] OR malignancy[Title/Abstract] OR metastasis[Title/Abstract]) '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract] OR "point-of-care"[Title/Abstract])'
        ),
    },
    "urology": {
        "label": "Урологія",
        "query": (
            '(urologic[Title/Abstract] OR urological[Title/Abstract] OR prostate[Title/Abstract] '
            'OR bladder[Title/Abstract] OR scrotal[Title/Abstract] OR testicular[Title/Abstract]) '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract])'
        ),
    },
    "gynecology": {
        "label": "Гінекологія",
        "query": (
            '(gynecologic[Title/Abstract] OR gynecological[Title/Abstract] OR pelvic[Title/Abstract] '
            'OR ovarian[Title/Abstract] OR uterine[Title/Abstract] OR endometrial[Title/Abstract]) '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract])'
        ),
    },
    "reproduction": {
        "label": "Репродуктологія",
        "query": (
            '(reproductive[Title/Abstract] OR infertility[Title/Abstract] OR fertility[Title/Abstract] '
            'OR "in vitro fertilization"[Title/Abstract] OR follicular[Title/Abstract] '
            'OR "ovarian reserve"[Title/Abstract]) '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract])'
        ),
    },
    "guidelines": {
        "label": "Нові рекомендації та протоколи асоціацій (EFSUMB/AIUM/ESR/ACR)",
        "query": (
            '(guideline[Title/Abstract] OR guidelines[Title/Abstract] OR recommendation*[Title/Abstract] '
            'OR consensus[Title/Abstract] OR "practice parameter"[Title/Abstract]) '
            'AND (ultrasound[Title/Abstract] OR ultrasonography[Title/Abstract])'
        ),
    },
}


def get_topic_label(topic_key: str) -> str:
    topic = TOPICS.get(topic_key)
    return topic["label"] if topic else topic_key


def list_topics_text() -> str:
    """Форматований список тем для команди /теми у боті."""
    lines = ["📋 Доступні теми:\n"]
    for key, data in TOPICS.items():
        lines.append(f"• `{key}` — {data['label']}")
    lines.append("\nПриклад: `/тема thyroid`")
    return "\n".join(lines)
