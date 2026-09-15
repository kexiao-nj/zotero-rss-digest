from __future__ import annotations

import html
import logging
import re
import shutil
import sqlite3
import tempfile
import time
from collections import defaultdict
from pathlib import Path

from .models import FeedInfo, FeedItem
from .zotero_client import try_feeds_http

log = logging.getLogger(__name__)

FIELD_MAP = {
    "title": "title",
    "abstractNote": "abstract",
    "url": "url",
    "DOI": "doi",
    "publicationTitle": "publication_title",
    "date": "date",
    "language": "language",
}

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
TAG_RE = re.compile(r"<[^>]+>")


def parse_item_date(raw: str | None) -> str:
    if not raw:
        return ""
    match = DATE_RE.search(raw)
    return match.group(1) if match else raw.strip()


def clean_text(value: str | None) -> str:
    text = html.unescape((value or "").strip())
    text = TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _copy_with_wal(data_dir: Path, dest_dir: Path) -> Path:
    src = data_dir / "zotero.sqlite"
    if not src.exists():
        raise FileNotFoundError(f"zotero.sqlite not found in {data_dir}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        piece = data_dir / f"zotero.sqlite{suffix}"
        if piece.exists():
            shutil.copy2(piece, dest_dir / f"zotero.sqlite{suffix}")
    return dest_dir / "zotero.sqlite"


def copy_zotero_db(data_dir: Path, retries: int = 3, retry_seconds: float = 1.5) -> Path:
    last_err: Exception | None = None
    tmp = Path(tempfile.mkdtemp(prefix="zotero-rss-"))
    for attempt in range(1, retries + 1):
        try:
            dest = _copy_with_wal(data_dir, tmp)
            log.debug("Copied Zotero DB to %s (attempt %s)", dest, attempt)
            return dest
        except OSError as exc:
            last_err = exc
            log.warning("SQLite copy failed (attempt %s/%s): %s", attempt, retries, exc)
            time.sleep(retry_seconds)
    raise RuntimeError(f"Could not copy zotero.sqlite after {retries} tries: {last_err}")


def _connect(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def _fields_table(con: sqlite3.Connection) -> str:
    names = {
        r[0]
        for r in con.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")
    }
    if "fieldsCombined" in names:
        return "fieldsCombined"
    if "fields" in names:
        return "fields"
    raise RuntimeError("Neither fieldsCombined nor fields exists in zotero.sqlite")


def _format_author(first: str | None, last: str | None, field_mode: int | None) -> str:
    first = (first or "").strip()
    last = (last or "").strip()
    if field_mode == 1:
        return last or first
    return " ".join(p for p in (first, last) if p)


def list_feeds(con: sqlite3.Connection) -> list[FeedInfo]:
    rows = con.execute(
        """
        SELECT
          f.libraryID,
          f.name,
          f.url,
          f.lastUpdate,
          f.lastCheck,
          f.lastCheckError,
          f.refreshInterval,
          COUNT(fi.itemID) AS item_count,
          SUM(CASE WHEN fi.readTime IS NULL THEN 1 ELSE 0 END) AS unread_count
        FROM feeds f
        LEFT JOIN items i ON i.libraryID = f.libraryID
        LEFT JOIN feedItems fi ON fi.itemID = i.itemID
        GROUP BY f.libraryID
        ORDER BY f.name COLLATE NOCASE
        """
    ).fetchall()
    return [
        FeedInfo(
            library_id=int(r["libraryID"]),
            name=r["name"] or "",
            url=r["url"] or "",
            last_update=r["lastUpdate"],
            last_check=r["lastCheck"],
            last_check_error=r["lastCheckError"],
            refresh_interval=r["refreshInterval"],
            item_count=int(r["item_count"] or 0),
            unread_count=int(r["unread_count"] or 0),
        )
        for r in rows
    ]


def load_feed_items(con: sqlite3.Connection) -> list[FeedItem]:
    fields_table = _fields_table(con)
    base_rows = con.execute(
        """
        SELECT
          fi.guid,
          fi.readTime,
          i.itemID,
          i.key,
          i.libraryID,
          i.dateAdded,
          i.dateModified,
          f.name AS feed_name,
          f.url AS feed_url
        FROM feedItems fi
        JOIN items i ON i.itemID = fi.itemID
        JOIN feeds f ON f.libraryID = i.libraryID
        """
    ).fetchall()
    if not base_rows:
        return []

    items: dict[int, FeedItem] = {}
    for r in base_rows:
        items[int(r["itemID"])] = FeedItem(
            guid=r["guid"],
            item_id=int(r["itemID"]),
            key=r["key"],
            library_id=int(r["libraryID"]),
            feed_name=r["feed_name"] or "",
            feed_url=r["feed_url"] or "",
            date_added=r["dateAdded"],
            date_modified=r["dateModified"],
            read_time=r["readTime"],
        )

    id_list = list(items)
    placeholders = ",".join("?" * len(id_list))
    field_sql = f"""
        SELECT id.itemID, fc.fieldName, idv.value
        FROM itemData id
        JOIN itemDataValues idv ON idv.valueID = id.valueID
        JOIN {fields_table} fc ON fc.fieldID = id.fieldID
        WHERE id.itemID IN ({placeholders})
    """
    for r in con.execute(field_sql, id_list):
        item = items[int(r["itemID"])]
        name = r["fieldName"]
        value = clean_text(r["value"])
        attr = FIELD_MAP.get(name)
        if attr:
            setattr(item, attr, value)
        else:
            item.extra_fields[name] = value

    creator_sql = f"""
        SELECT ic.itemID, c.firstName, c.lastName, c.fieldMode, ic.orderIndex
        FROM itemCreators ic
        JOIN creators c ON c.creatorID = ic.creatorID
        WHERE ic.itemID IN ({placeholders})
        ORDER BY ic.itemID, ic.orderIndex
    """
    grouped: dict[int, list[str]] = defaultdict(list)
    for r in con.execute(creator_sql, id_list):
        grouped[int(r["itemID"])].append(
            _format_author(r["firstName"], r["lastName"], r["fieldMode"])
        )
    for item_id, authors in grouped.items():
        items[item_id].authors = [a for a in authors if a]

    result = []
    for item in items.values():
        item.date = parse_item_date(item.date) or parse_item_date(item.date_added)
        item.metadata_thin = len(item.abstract) < 80
        if item.doi:
            item.doi = item.doi.replace("https://doi.org/", "").strip()
        result.append(item)
    result.sort(key=lambda it: (it.date or "", it.date_added or ""), reverse=True)
    return result


def _author_from_api(raw: dict) -> str:
    if raw.get("name"):
        return str(raw["name"]).strip()
    return " ".join(
        p for p in ((raw.get("firstName") or "").strip(), (raw.get("lastName") or "").strip()) if p
    )


def parse_zotero_json_items(payload: list[dict]) -> list[FeedItem]:
    """Map Zotero Local/Web API item JSON into FeedItem. Returns [] if unusable."""
    items: list[FeedItem] = []
    for idx, raw in enumerate(payload):
        if not isinstance(raw, dict):
            continue
        data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
        if not isinstance(data, dict):
            continue
        title = clean_text(str(data.get("title") or ""))
        # Feed metadata objects have name+url but no title.
        if not title and data.get("name") and data.get("url") and not data.get("itemType"):
            continue
        key = str(raw.get("key") or data.get("key") or "")
        url = str(data.get("url") or "")
        guid = str(data.get("guid") or url or key)
        if not guid and not title:
            continue
        library = raw.get("library") if isinstance(raw.get("library"), dict) else {}
        feed_name = str(
            library.get("name")
            or data.get("publicationTitle")
            or data.get("feedName")
            or ""
        )
        authors = [
            _author_from_api(c)
            for c in (data.get("creators") or [])
            if isinstance(c, dict)
        ]
        doi = str(data.get("DOI") or data.get("doi") or "").replace(
            "https://doi.org/", ""
        ).strip()
        abstract = clean_text(str(data.get("abstractNote") or data.get("abstract") or ""))
        date_added = str(data.get("dateAdded") or raw.get("dateAdded") or "") or None
        item = FeedItem(
            guid=guid or f"http-item-{idx}",
            item_id=idx + 1,
            key=key,
            library_id=int(library.get("id") or 0),
            feed_name=feed_name,
            feed_url="",
            date_added=date_added,
            date_modified=str(data.get("dateModified") or "") or None,
            title=title,
            abstract=abstract,
            url=url,
            doi=doi,
            publication_title=clean_text(str(data.get("publicationTitle") or "")),
            date=parse_item_date(str(data.get("date") or "")) or parse_item_date(date_added),
            language=str(data.get("language") or ""),
            authors=[a for a in authors if a],
            metadata_thin=len(abstract) < 80,
        )
        items.append(item)
    items.sort(key=lambda it: (it.date or "", it.date_added or ""), reverse=True)
    return items


def _feeds_from_items(items: list[FeedItem]) -> list[FeedInfo]:
    grouped: dict[str, FeedInfo] = {}
    for item in items:
        name = item.feed_name or "(unknown feed)"
        info = grouped.get(name)
        if info is None:
            info = FeedInfo(library_id=item.library_id, name=name, url=item.feed_url)
            grouped[name] = info
        info.item_count += 1
        if not item.read_time:
            info.unread_count += 1
    return list(grouped.values())


def ingest_feeds(
    data_dir: Path,
    api_base: str | None = None,
    retries: int = 3,
    retry_seconds: float = 1.5,
    db_path: Path | None = None,
) -> tuple[list[FeedInfo], list[FeedItem], Path | None]:
    """Prefer undocumented Local API feeds if they return items; else SQLite copy."""
    if db_path is None and api_base:
        ok, payload = try_feeds_http(api_base)
        if ok and payload:
            parsed = parse_zotero_json_items(payload)
            if parsed:
                log.info("Ingesting %s items from Local API feeds endpoint", len(parsed))
                return _feeds_from_items(parsed), parsed, None
            log.debug("Local API feeds payload had no items; using SQLite")
    return read_from_sqlite(
        data_dir, retries=retries, retry_seconds=retry_seconds, db_path=db_path
    )


def read_from_sqlite(
    data_dir: Path,
    retries: int = 3,
    retry_seconds: float = 1.5,
    db_path: Path | None = None,
) -> tuple[list[FeedInfo], list[FeedItem], Path]:
    copied = db_path
    cleanup = None
    if copied is None:
        copied = copy_zotero_db(data_dir, retries=retries, retry_seconds=retry_seconds)
        cleanup = copied.parent
    try:
        con = _connect(copied)
        try:
            feeds = list_feeds(con)
            items = load_feed_items(con)
            return feeds, items, copied
        finally:
            con.close()
    finally:
        if cleanup is not None:
            shutil.rmtree(cleanup, ignore_errors=True)
