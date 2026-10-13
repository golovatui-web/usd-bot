"""
Реєстр тем бота (MeSH + Title/Abstract).

Кожна тема має:
- label: назва українською, яку бачить користувач
- query: пошуковий запит PubMed БЕЗ ультразвукового фільтра.
  Базовий фільтр додається програмно в fetcher.compose_pubmed_query():
    AND ("Ultrasonography"[Mesh] OR "ultrasound"[tiab] OR "sonography"[tiab])
- hashtag: хештег поста в каналі (клік відкриває пошук по історії каналу)

Ключ теми (наприклад "thyroid") — ідентифікатор у командах бота та в БД,
після першого запуску краще не перейменовувати.

Порядок словника МАЄ значення: при перетині тем виграє та, що йде РАНІШЕ
(глобальна унікальність pmid — див. scheduler.py / worker.py). Тому
органо-специфічні теми йдуть перед техніками (ceus, elastography) і
наскрізними (pediatric, oncology, acute_emergency, ai_tech, guidelines).

25 тем. Теги PubMed: [Mesh] — Medical Subject Headings, [tiab] — Title/Abstract,
[pt] — Publication Type.
"""

TOPICS = {
    # ==================== Органо-специфічні ====================
    "thyroid": {
        "label": "Щитоподібна залоза",
        "hashtag": "#щитоподібна",
        "query": (
            '("Thyroid Gland"[Mesh] OR "Thyroid Nodule"[Mesh] OR "Thyroid Neoplasms"[Mesh] '
            'OR thyroid[tiab] OR "thyroid nodule"[tiab] OR "FNA"[tiab] '
            'OR "fine needle aspiration"[tiab] OR TIRADS[tiab] '
            'OR "radiofrequency ablation"[tiab] OR RFA[tiab])'
        ),
    },
    "breast_lymph": {
        "label": "Молочні залози та лімфовузли",
        "hashtag": "#молочна_залоза",
        "query": (
            '("Breast Neoplasms"[Mesh] OR "Lymph Nodes"[Mesh] OR "Breast"[Mesh] '
            'OR breast[tiab] OR "lymph nodes"[tiab] OR axillary[tiab] '
            'OR "core needle biopsy"[tiab] OR "fine needle"[tiab] OR BIRADS[tiab])'
        ),
    },
    "abdomen": {
        "label": "Черевна порожнина (загальне)",
        "hashtag": "#черевна_порожнина",
        "query": (
            '("Abdomen"[Mesh] OR "Spleen"[Mesh] OR abdomen[tiab] OR abdominal[tiab] '
            'OR "acute abdomen"[tiab] OR spleen[tiab] OR splenic[tiab]) '
            'NOT (liver[tiab] OR hepatic[tiab] OR kidney[tiab] OR renal[tiab] '
            'OR pancreas[tiab] OR pancreatic[tiab])'
        ),
    },
    "liver": {
        "label": "Печінка",
        "hashtag": "#печінка",
        "query": (
            '("Liver"[Mesh] OR "Liver Diseases"[Mesh] OR "Fatty Liver"[Mesh] '
            'OR "Liver Cirrhosis"[Mesh] OR liver[tiab] OR hepatic[tiab] '
            'OR "fatty liver"[tiab] OR cirrhosis[tiab] OR steatosis[tiab] '
            'OR "hepatocellular carcinoma"[tiab] OR NAFLD[tiab] OR MASLD[tiab])'
        ),
    },
    "kidney": {
        "label": "Нирки",
        "hashtag": "#нирки",
        "query": (
            '("Kidney"[Mesh] OR "Kidney Diseases"[Mesh] OR "Hydronephrosis"[Mesh] '
            'OR kidney[tiab] OR renal[tiab] OR "renal artery"[tiab] '
            'OR nephrolithiasis[tiab] OR hydronephrosis[tiab] OR "renal cyst"[tiab])'
        ),
    },
    "pancreas_gi": {
        "label": "Підшлункова залоза та ШКТ",
        "hashtag": "#підшлункова_шкт",
        "query": (
            '("Pancreas"[Mesh] OR "Pancreatic Diseases"[Mesh] OR "Gastrointestinal Tract"[Mesh] '
            'OR "Appendicitis"[Mesh] OR pancreas[tiab] OR pancreatic[tiab] '
            'OR "gastrointestinal tract"[tiab] OR bowel[tiab] OR intestinal[tiab] '
            'OR appendicitis[tiab] OR Crohn[tiab])'
        ),
    },
    "gynecology": {
        "label": "Гінекологія",
        "hashtag": "#гінекологія",
        "query": (
            '("Genitalia, Female"[Mesh] OR "Ovarian Diseases"[Mesh] OR "Uterine Diseases"[Mesh] '
            'OR gynecologic[tiab] OR gynecological[tiab] OR pelvic[tiab] '
            'OR ovarian[tiab] OR uterine[tiab] OR endometrial[tiab] OR IOTA[tiab])'
        ),
    },
    "obstetrics": {
        "label": "Акушерство",
        "hashtag": "#акушерство",
        "query": (
            '("Ultrasonography, Prenatal"[Mesh] OR "Pregnancy"[Mesh] OR "Fetus"[Mesh] '
            'OR obstetric[tiab] OR fetal[tiab] OR prenatal[tiab] '
            'OR "fetal biometry"[tiab] OR "nuchal translucency"[tiab] OR pregnancy[tiab])'
        ),
    },
    "reproduction": {
        "label": "Репродуктологія",
        "hashtag": "#репродуктологія",
        "query": (
            '("Reproductive Techniques"[Mesh] OR "Infertility"[Mesh] OR "Ovarian Reserve"[Mesh] '
            'OR reproductive[tiab] OR infertility[tiab] OR fertility[tiab] '
            'OR "in vitro fertilization"[tiab] OR follicular[tiab] OR "ovarian reserve"[tiab])'
        ),
    },
    "urology": {
        "label": "Урологія",
        "hashtag": "#урологія",
        "query": (
            '("Prostate"[Mesh] OR "Urinary Bladder"[Mesh] OR "Testis"[Mesh] '
            'OR urologic[tiab] OR urological[tiab] OR prostate[tiab] '
            'OR bladder[tiab] OR scrotal[tiab] OR testicular[tiab] OR TRUS[tiab])'
        ),
    },
    "vessels": {
        "label": "Судини шиї і голови",
        "hashtag": "#судини_шиї",
        "query": (
            '("Carotid Arteries"[Mesh] OR "Carotid Stenosis"[Mesh] '
            'OR "Ultrasonography, Doppler, Transcranial"[Mesh] '
            'OR "carotid artery"[tiab] OR "carotid stenosis"[tiab] '
            'OR "vertebral artery"[tiab] OR "transcranial doppler"[tiab] '
            'OR "neck vessels"[tiab])'
        ),
    },
    "vascular": {
        "label": "Периферичні судини",
        "hashtag": "#периферичні_судини",
        "query": (
            '("Venous Thrombosis"[Mesh] OR "Peripheral Vascular Diseases"[Mesh] '
            'OR "Varicose Veins"[Mesh] OR "deep vein thrombosis"[tiab] '
            'OR "venous insufficiency"[tiab] OR "peripheral artery disease"[tiab] '
            'OR "peripheral vascular"[tiab] OR "lower limb ischemia"[tiab] OR varicose[tiab])'
        ),
    },
    "msk": {
        "label": "Опорно-рухова система",
        "hashtag": "#опорно_руховий",
        "query": (
            '("Musculoskeletal System"[Mesh] OR "Tendons"[Mesh] OR "Rotator Cuff"[Mesh] '
            'OR musculoskeletal[tiab] OR tendon[tiab] OR ligament[tiab] '
            'OR "rotator cuff"[tiab] OR "joint ultrasound"[tiab] OR muscle[tiab])'
        ),
    },
    "soft_tissue": {
        "label": "М'які тканини",
        "hashtag": "#мякі_тканини",
        "query": (
            '("Soft Tissue Neoplasms"[Mesh] OR "Soft Tissue Injuries"[Mesh] '
            'OR "soft tissue"[tiab] OR "soft-tissue"[tiab])'
        ),
    },
    "peripheral_nerves": {
        "label": "Периферичні нерви",
        "hashtag": "#периферичні_нерви",
        "query": (
            '("Peripheral Nerves"[Mesh] OR "Diabetic Neuropathies"[Mesh] '
            'OR "Carpal Tunnel Syndrome"[Mesh] OR "peripheral nerve"[tiab] '
            'OR "nerve entrapment"[tiab] OR "carpal tunnel"[tiab] '
            'OR "nerve morphometry"[tiab] OR neuropathy[tiab])'
        ),
    },
    "salivary": {
        "label": "Слинні залози",
        "hashtag": "#слинні_залози",
        "query": (
            '("Salivary Glands"[Mesh] OR "Parotid Gland"[Mesh] '
            'OR "salivary gland"[tiab] OR parotid[tiab] OR submandibular[tiab])'
        ),
    },
    "head_neck": {
        "label": "Голова та шия (інше)",
        "hashtag": "#голова_шия",
        "query": (
            '("Neck"[Mesh] OR "Parathyroid Glands"[Mesh] OR "Larynx"[Mesh] '
            'OR parathyroid[tiab] OR larynx[tiab] OR laryngeal[tiab] '
            'OR "cervical lymph node"[tiab] OR "neck mass"[tiab])'
        ),
    },
    "lung_pocus": {
        "label": "Легеневе УЗД / POCUS",
        "hashtag": "#легені",
        "query": (
            '("Lung"[Mesh] OR "Pleural Effusion"[Mesh] OR "Pneumothorax"[Mesh] '
            'OR "lung ultrasound"[tiab] OR "pulmonary ultrasound"[tiab] '
            'OR pleural[tiab] OR "B-lines"[tiab] OR pneumothorax[tiab])'
        ),
    },

    # ==================== Техніки ====================
    "ceus": {
        "label": "Контрастне УЗД (CEUS)",
        "hashtag": "#ceus",
        "query": (
            '("Contrast Media"[Mesh] OR "contrast-enhanced ultrasound"[tiab] '
            'OR CEUS[tiab] OR "contrast enhanced ultrasonography"[tiab] '
            'OR SonoVue[tiab] OR "ultrasound contrast"[tiab])'
        ),
    },
    "elastography": {
        "label": "Еластографія",
        "hashtag": "#еластографія",
        "query": (
            '("Elasticity Imaging Techniques"[Mesh] OR elastography[tiab] '
            'OR "shear wave"[tiab] OR "strain elastography"[tiab] '
            'OR SWE[tiab] OR ARFI[tiab] OR "liver stiffness"[tiab])'
        ),
    },

    # ==================== Наскрізні (пізніше в списку) ====================
    "pediatric": {
        "label": "Педіатричне УЗД",
        "hashtag": "#педіатрія",
        "query": (
            '("Pediatrics"[Mesh] OR "Infant"[Mesh] OR pediatric[tiab] '
            'OR paediatric[tiab] OR infant[tiab] OR neonatal[tiab] OR children[tiab])'
        ),
    },
    "oncology": {
        "label": "Онкологічне УЗД",
        "hashtag": "#онкологія",
        "query": (
            '("Neoplasms"[Mesh] OR oncology[tiab] OR oncologic[tiab] '
            'OR tumor[tiab] OR malignancy[tiab] OR metastasis[tiab] '
            'OR "cancer screening"[tiab])'
        ),
    },
    "acute_emergency": {
        "label": "Невідкладне УЗД",
        "hashtag": "#невідкладна_допомога",
        "query": (
            '("Emergencies"[Mesh] OR "Point-of-Care Systems"[Mesh] '
            'OR emergency[tiab] OR "point-of-care"[tiab] OR POCUS[tiab] '
            'OR trauma[tiab] OR FAST[tiab] OR eFAST[tiab])'
        ),
    },
    "ai_tech": {
        "label": "ШІ та технології УЗД",
        "hashtag": "#штучний_інтелект",
        "query": (
            '("Artificial Intelligence"[Mesh] OR "Deep Learning"[Mesh] '
            'OR "Machine Learning"[Mesh] OR "artificial intelligence"[tiab] '
            'OR "deep learning"[tiab] OR "machine learning"[tiab] OR automation[tiab])'
        ),
    },
    "guidelines": {
        "label": "Рекомендації асоціацій",
        "hashtag": "#рекомендації",
        "query": (
            '("Guideline"[pt] OR "Practice Guideline"[pt] OR "Consensus"[tiab] '
            'OR guideline[tiab] OR guidelines[tiab] OR "practice parameter"[tiab]) '
            'AND ("EFSUMB"[tiab] OR "AIUM"[tiab] OR "ESR"[tiab] OR "ACR"[tiab] '
            'OR "WFUMB"[tiab] OR "SRU"[tiab] OR "RSNA"[tiab])'
        ),
    },
}

TOPIC_KEYS = list(TOPICS.keys())


def get_topic_label(topic_key: str) -> str:
    topic = TOPICS.get(topic_key)
    return topic["label"] if topic else topic_key


def get_topic_hashtag(topic_key: str) -> str:
    topic = TOPICS.get(topic_key)
    return topic["hashtag"] if topic else "#узд"


def list_topics_text() -> str:
    """Форматований список тем для команди /topics (HTML, узгоджено з format_article)."""
    lines = ["Доступні теми:\n"]
    for key, data in TOPICS.items():
        lines.append(f"• <code>{key}</code> — {data['label']}")
    lines.append("\nПриклад: <code>/topic thyroid</code>")
    return "\n".join(lines)
