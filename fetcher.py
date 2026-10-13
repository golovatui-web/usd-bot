"""
Отримання нових статей із PubMed (E-utilities). Повний текст НЕ завантажується —
лише публічна анотація, яку далі перефразовує Gemini.

Базовий ультразвуковий фільтр додається до КОЖНОГО тематичного запиту
(див. compose_pubmed_query), щоб MeSH-запити в config/topics.py лишались
чистими й не дублювали "ultrasound" у кожному рядку.
"""

import time
import xml.etree.ElementTree as ET
from typing import Dict, List

import requests

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

ULTRASOUND_FILTER = (
    '("Ultrasonography"[Mesh] OR "ultrasound"[tiab] OR "sonography"[tiab])'
)


def compose_pubmed_query(topic_query: str) -> str:
    """Обгортає тематичний MeSH/tiab-запит обов'язковим ультразвуковим фільтром."""
    return f"({topic_query}) AND {ULTRASOUND_FILTER}"


def search_pubmed(query: str, days_back: int, retmax: int, api_key: str = "") -> List[str]:
    """Повертає список PMID за останні `days_back` днів.

    sort=pub_date — за фактичною датою публікації (а не "most recent", яке
    для ESearch невалідне і сортує за датою індексації).
    """
    params = {
        "db": "pubmed",
        "term": compose_pubmed_query(query),
        "retmax": retmax,
        "retmode": "json",
        "sort": "pub_date",
        "datetype": "pdat",
        "reldate": days_back,
    }
    if api_key:
        params["api_key"] = api_key

    resp = requests.get(ESEARCH_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    idlist = data.get("esearchresult", {}).get("idlist", [])
    return list(dict.fromkeys(idlist))


def _text_or_none(el):
    """Весь текст елемента, включно з фрагментами після вкладених <i>/<sub>/<sup>.
    Звичайний el.text віддав би лише текст ДО першого вкладеного тега."""
    if el is None:
        return None
    text = "".join(el.itertext()).strip()
    return text or None


def _extract_abstract(article_el) -> str:
    parts = []
    for ab in article_el.findall(".//Abstract/AbstractText"):
        label = ab.get("Label")
        text = "".join(ab.itertext()).strip()
        parts.append(f"{label}: {text}" if label else text)
    return " ".join(parts).strip()


def fetch_details(pmids: List[str], api_key: str = "") -> List[Dict]:
    if not pmids:
        return []

    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "rettype": "abstract",
        "retmode": "xml",
    }
    if api_key:
        params["api_key"] = api_key

    resp = requests.get(EFETCH_URL, params=params, timeout=30)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)

    results = []
    for article_el in root.findall(".//PubmedArticle"):
        pmid = _text_or_none(article_el.find(".//PMID"))
        title = _text_or_none(article_el.find(".//ArticleTitle")) or "(без назви)"
        journal = _text_or_none(article_el.find(".//Journal/Title"))
        abstract = _extract_abstract(article_el)

        year = _text_or_none(article_el.find(".//PubDate/Year"))
        medline_date = _text_or_none(article_el.find(".//PubDate/MedlineDate"))
        pub_date = year or medline_date or "н/д"

        if not abstract:
            continue

        results.append(
            {
                "pmid": pmid,
                "title": title,
                "journal": journal or "н/д",
                "pub_date": pub_date,
                "abstract": abstract,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            }
        )

    return results


def fetch_new_articles_for_topic(query: str, days_back: int, retmax: int, api_key: str = "") -> List[Dict]:
    """Пошук + деталі для однієї теми, з паузою під NCBI rate limit (~3 req/s без ключа)."""
    pmids = search_pubmed(query, days_back, retmax, api_key)
    time.sleep(0.4)
    details = fetch_details(pmids, api_key)
    time.sleep(0.4)
    return details
