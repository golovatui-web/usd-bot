"""
Отримання нових статей із PubMed (безкоштовне E-utilities API, ключ не обов'язковий,
але з ним вищі ліміти запитів: https://www.ncbi.nlm.nih.gov/books/NBK25497/).

Логіка навмисно проста: esearch -> список PMID -> efetch -> деталі (назва, анотація,
журнал, дата, DOI). Повний текст статей НЕ завантажується — лише публічно доступна
анотація (abstract), яку далі перефразовує Claude у summarizer.py.
"""

import time
import xml.etree.ElementTree as ET
from typing import Dict, List

import requests

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def search_pubmed(query: str, days_back: int, retmax: int, api_key: str = "") -> List[str]:
    """Повертає список PMID, опублікованих за останні `days_back` днів.

    sort=pub_date — сортування за фактичною датою публікації статті (а не датою її
    індексації в PubMed, яку позначає "most recent"): саме це нам потрібно, щоб при
    обмеженні retmax потрапляли дійсно найновіші публікації, а не довільна підмножина.
    """
    params = {
        "db": "pubmed",
        "term": query,
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
    # На випадок рідкісних дублікатів у відповіді PubMed — прибираємо, зберігаючи порядок.
    return list(dict.fromkeys(idlist))


def _text_or_none(el):
    """Бере ВЕСЬ текст елемента, включно з тим, що йде після вкладених inline-тегів
    (<i>, <sub>, <sup>, <b> — часто зустрічаються в назвах генів, хімічних формулах).
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
    """Повертає деталі статей (назва, анотація, журнал, дата, посилання) за списком PMID."""
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
            # Пропускаємо статті без анотації — без неї нема з чого робити коротке резюме
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
    """Зручна обгортка: пошук + деталі для однієї теми, з невеликою паузою (NCBI rate limit)."""
    pmids = search_pubmed(query, days_back, retmax, api_key)
    time.sleep(0.4)  # NCBI просить не більше ~3 запитів/сек без ключа
    details = fetch_details(pmids, api_key)
    time.sleep(0.4)
    return details
