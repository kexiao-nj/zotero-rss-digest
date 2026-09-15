from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .config import AppConfig
from .distill import cluster_items, distill_item, fallback_card
from .enrich import enrich_items
from .feed_reader import ingest_feeds
from .models import FeedItem, ProbeResult, RunStats, ScoredItem
from .relevance import filter_items
from .report import append_skipped, render_digest, update_findings, write_digest
from .state import load_state, mark_seen, save_state, seen_set
from .zotero_client import apply_api_probe

log = logging.getLogger(__name__)


def parse_iso_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def item_on_or_after(item: FeedItem, start: date) -> bool:
    for raw in (item.date, item.date_added):
        if not raw:
            continue
        try:
            return date.fromisoformat(str(raw)[:10]) >= start
        except ValueError:
            continue
    return True


def probe(cfg: AppConfig, db_path: Path | None = None) -> ProbeResult:
    result = ProbeResult(
        local_api_ok=False,
        local_api_detail="",
        feeds_http_ok=False,
        data_dir=str(cfg.data_dir),
        sqlite_ok=False,
        sqlite_detail="",
    )
    apply_api_probe(result, cfg.local_api_base)
    try:
        feeds, items, _ = ingest_feeds(
            cfg.data_dir,
            api_base=cfg.local_api_base,
            retries=int(cfg.zotero.get("copy_retries", 3)),
            retry_seconds=float(cfg.zotero.get("copy_retry_seconds", 1.5)),
            db_path=db_path,
        )
        result.sqlite_ok = True
        result.feeds = feeds
        result.total_items = len(items)
        result.unread_items = sum(1 for it in items if not it.read_time)
        result.sqlite_detail = (
            f"Read {len(feeds)} feeds / {len(items)} items from {cfg.data_dir}"
        )
    except Exception as exc:
        result.sqlite_ok = False
        result.sqlite_detail = f"SQLite read failed: {exc}"
        log.exception("probe sqlite failed")
    return result


def select_new_items(
    items: list[FeedItem],
    state: dict,
    *,
    lookback_days: int | None,
    since: date | None,
    process_all: bool,
) -> list[FeedItem]:
    if since is not None:
        return [it for it in items if item_on_or_after(it, since)]
    if process_all:
        return list(items)
    seen = seen_set(state)
    if not seen:
        days = lookback_days if lookback_days is not None else 7
        start = date.today() - timedelta(days=days)
        return [it for it in items if item_on_or_after(it, start)]
    return [it for it in items if it.guid not in seen]


def run_pipeline(
    cfg: AppConfig,
    *,
    use_llm: bool = True,
    enrich: bool | None = None,
    lookback_days: int | None = None,
    since: str | None = None,
    process_all: bool = False,
    db_path: Path | None = None,
) -> RunStats:
    started = datetime.now(timezone.utc)
    stats = RunStats(started_at=started)
    feeds, items, _ = ingest_feeds(
        cfg.data_dir,
        api_base=None if db_path else cfg.local_api_base,
        retries=int(cfg.zotero.get("copy_retries", 3)),
        retry_seconds=float(cfg.zotero.get("copy_retry_seconds", 1.5)),
        db_path=db_path,
    )
    stats.ingested = len(items)
    log.info("Loaded %s feeds / %s RSS items", len(feeds), len(items))

    state = load_state(cfg.state_path)
    since_date = parse_iso_date(since) if since else None
    if lookback_days is None:
        lookback_days = int(cfg.run.get("first_run_lookback_days", 7))
    new_items = select_new_items(
        items,
        state,
        lookback_days=lookback_days,
        since=since_date,
        process_all=process_all,
    )
    stats.new_items = len(new_items)

    def snapshot_guids(report_path: str | None) -> None:
        mark_seen(state, [it.guid for it in items], report_path)
        save_state(cfg.state_path, state)

    if not new_items:
        snapshot_guids(None)
        stats.empty = True
        stats.message = "No new RSS items."
        stats.finished_at = datetime.now(timezone.utc)
        log.info(stats.message)
        return stats

    do_enrich = cfg.run.get("enrich", True) if enrich is None else enrich
    enrich_items(new_items, enabled=bool(do_enrich))

    kept, skipped = filter_items(new_items, cfg.profile)
    llm_cfg = cfg.llm_settings()
    language = str(cfg.run.get("language", "zh"))
    cap = int(cfg.run.get("llm_batch_cap", 30))
    min_llm = float(cfg.profile.get("min_llm_score", 3))

    related: list[ScoredItem] = []
    if use_llm and llm_cfg["enabled"] and kept:
        batch = kept[:cap]
        overflow = kept[cap:]
        for scored in overflow:
            scored.card = fallback_card(scored.item, scored.rule_score, scored.reasons)
            if scored.score >= min_llm:
                related.append(scored)
            else:
                scored.skipped = True
                scored.skip_reason = "below_min_llm_score"
                skipped.append(scored)
        for scored in batch:
            distill_item(scored, cfg.profile, llm_cfg, language=language)
            stats.llm_used += 1
            if scored.score >= min_llm:
                related.append(scored)
            else:
                scored.skipped = True
                scored.skip_reason = "below_min_llm_score"
                skipped.append(scored)
        related.sort(key=lambda s: s.score, reverse=True)
        themes = cluster_items(related, llm_cfg, language=language)
    else:
        if use_llm and not llm_cfg["enabled"]:
            log.info("LLM disabled (no API key); writing rule-only digest")
        related = kept
        for scored in related:
            if not scored.card:
                scored.card = fallback_card(scored.item, scored.rule_score, scored.reasons)
        themes = []

    stats.related = len(related)
    stats.skipped = len(skipped)
    day = date.today()
    markdown = render_digest(
        related=related,
        skipped=skipped,
        themes=themes,
        profile=cfg.profile,
        new_count=len(new_items),
        when=day,
    )
    report_path = cfg.reports_dir / f"{day.isoformat()}.md"
    write_digest(report_path, markdown)
    append_skipped(cfg.skipped_path, skipped, run_id=started.isoformat())
    update_findings(cfg.findings_path, related=related, themes=themes, when=day)
    snapshot_guids(str(report_path))
    stats.report_path = str(report_path)
    stats.finished_at = datetime.now(timezone.utc)
    stats.message = f"Wrote {report_path}"
    log.info(stats.message)
    return stats
