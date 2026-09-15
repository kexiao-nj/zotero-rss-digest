from __future__ import annotations

import logging
import os
import re
import time
from urllib.parse import quote

import requests

from .models import FeedItem

log = logging.getLogger(__name__)

DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
ARXIV_RE = re.compile(r"(?:arxiv:)?(\d{4}\.\d{4,5}(?:v\d+)?)", re.I)


def extract_doi(item: FeedItem) -> str:
    if item.doi:
        return item.doi.replace("https://doi.org/", "").strip()
    blob = " ".join([item.url, item.abstract, item.extra_fields.get("extra", "")])
    match = DOI_RE.search(blob)
    return match.group(0) if match else ""


def extract_arxiv(item: FeedItem) -> str:
    blob = " ".join([item.url, item.guid, item.doi, item.extra_fields.get("extra", "")])
    match = ARXIV_RE.search(blob)
    return match.group(1) if match else ""


def _headers() -> dict[str, str]:
    email = os.environ.get("CONTACT_EMAIL", "local-user@example.com")
    return {"User-Agent": f"zotero-rss-analyzer/0.1 (mailto:{email})"}


def _from_crossref(doi: str, timeout: float) -> str:
    url = f"https://api.crossref.org/works/{quote(doi)}"
    resp = requests.get(url, headers=_headers(), timeout=timeout)
    if resp.status_code != 200:
        return ""
    msg = resp.json().get("message") or {}
    abstract = msg.get("abstract") or ""
    # Crossref JATS wrapping
    abstract = re.sub(r"<[^>]+>", " ", abstract)
    return re.sub(r"\s+", " ", abstract).strip()


def _from_openalex(doi: str, timeout: float) -> str:
    url = f"https://api.openalex.org/works/https://doi.org/{doi}"
    resp = requests.get(url, headers=_headers(), timeout=timeout)
    if resp.status_code != 200:
        return ""
    inv = resp.json().get("abstract_inverted_index")
    if not isinstance(inv, dict):
        return ""
    positions: list[tuple[int, str]] = []
    for word, idxs in inv.items():
        for i in idxs:
            positions.append((int(i), word))
    positions.sort()
    return " ".join(w for _, w in positions).strip()


def _from_arxiv(arxiv_id: str, timeout: float) -> str:
    url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
    resp = requests.get(url, headers=_headers(), timeout=timeout)
    if resp.status_code != 200:
        return ""
    text = resp.text
    start = text.find("<summary>")
    end = text.find("</summary>")
    if start == -1 or end == -1:
        return ""
    return re.sub(r"\s+", " ", text[start + 9 : end]).strip()


def enrich_item(item: FeedItem, timeout: float = 12.0) -> FeedItem:
    if len(item.abstract) >= 80:
        item.metadata_thin = False
        return item
    doi = extract_doi(item)
    arxiv_id = extract_arxiv(item)
    abstract = ""
    try:
        if doi:
            abstract = _from_crossref(doi, timeout) or _from_openalex(doi, timeout)
        if not abstract and arxiv_id:
            abstract = _from_arxiv(arxiv_id, timeout)
    except requests.RequestException as exc:
        log.info("Enrich failed for %s: %s", item.guid, exc)
    if abstract and len(abstract) > len(item.abstract):
        item.abstract = abstract
        if doi and not item.doi:
            item.doi = doi
    item.metadata_thin = len(item.abstract) < 80
    return item


def enrich_items(items: list[FeedItem], enabled: bool = True, pause: float = 0.15) -> list[FeedItem]:
    if not enabled:
        return items
    for item in items:
        if item.metadata_thin:
            enrich_item(item)
            if pause:
                time.sleep(pause)
    return items
