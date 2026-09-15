from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class FeedInfo:
    library_id: int
    name: str
    url: str
    last_update: str | None = None
    last_check: str | None = None
    last_check_error: str | None = None
    refresh_interval: int | None = None
    item_count: int = 0
    unread_count: int = 0


@dataclass
class FeedItem:
    guid: str
    item_id: int
    key: str
    library_id: int
    feed_name: str
    feed_url: str
    date_added: str | None = None
    date_modified: str | None = None
    read_time: str | None = None
    title: str = ""
    abstract: str = ""
    url: str = ""
    doi: str = ""
    publication_title: str = ""
    date: str = ""
    language: str = ""
    authors: list[str] = field(default_factory=list)
    extra_fields: dict[str, str] = field(default_factory=dict)
    metadata_thin: bool = False

    @property
    def blob(self) -> str:
        parts = [
            self.title,
            self.abstract,
            self.publication_title,
            self.feed_name,
            " ".join(self.authors),
            self.doi,
        ]
        return "\n".join(p for p in parts if p)

    def author_line(self) -> str:
        if not self.authors:
            return ""
        if len(self.authors) <= 3:
            return ", ".join(self.authors)
        return ", ".join(self.authors[:3]) + " et al."


@dataclass
class ScoredItem:
    item: FeedItem
    rule_score: float
    llm_score: float | None = None
    reasons: list[str] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""
    card: dict[str, Any] | None = None

    @property
    def score(self) -> float:
        if self.llm_score is not None:
            return self.llm_score
        return self.rule_score


@dataclass
class ProbeResult:
    local_api_ok: bool
    local_api_detail: str
    feeds_http_ok: bool
    data_dir: str
    sqlite_ok: bool
    sqlite_detail: str
    feeds: list[FeedInfo] = field(default_factory=list)
    total_items: int = 0
    unread_items: int = 0


@dataclass
class RunStats:
    started_at: datetime
    finished_at: datetime | None = None
    ingested: int = 0
    new_items: int = 0
    related: int = 0
    skipped: int = 0
    llm_used: int = 0
    report_path: str | None = None
    empty: bool = False
    message: str = ""
