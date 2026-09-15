from __future__ import annotations

from typing import Any

from .models import FeedItem, ScoredItem


def _haystack(item: FeedItem) -> str:
    return item.blob.lower()


def _hits(text: str, keywords: list[str]) -> list[str]:
    found = []
    for raw in keywords:
        kw = (raw or "").strip().lower()
        if kw and kw in text:
            found.append(raw)
    return found


def score_item(item: FeedItem, profile: dict[str, Any]) -> ScoredItem:
    text = _haystack(item)
    include = list(profile.get("include_keywords") or []) + list(profile.get("topics") or [])
    exclude = list(profile.get("exclude_keywords") or [])
    require = list(profile.get("require_any_keywords") or [])
    journals = list(profile.get("journal_whitelist") or [])
    allow = list(profile.get("feed_allowlist") or [])
    block = list(profile.get("feed_blocklist") or [])
    min_rule = float(profile.get("min_rule_score", 2))

    reasons: list[str] = []

    if allow and item.feed_name not in allow:
        return ScoredItem(
            item=item,
            rule_score=0,
            reasons=["feed not in allowlist"],
            skipped=True,
            skip_reason="feed_allowlist",
        )
    if block and item.feed_name in block:
        return ScoredItem(
            item=item,
            rule_score=0,
            reasons=[f"blocked feed: {item.feed_name}"],
            skipped=True,
            skip_reason="feed_blocklist",
        )

    excluded = _hits(text, exclude)
    if excluded:
        return ScoredItem(
            item=item,
            rule_score=0,
            reasons=[f"exclude: {', '.join(excluded)}"],
            skipped=True,
            skip_reason="exclude_keywords",
        )

    if require and not _hits(text, require):
        return ScoredItem(
            item=item,
            rule_score=0,
            reasons=["missing required keyword"],
            skipped=True,
            skip_reason="require_any_keywords",
        )

    include_hits = _hits(text, include)
    journal_hit = False
    pub = f"{item.publication_title} {item.feed_name}".lower()
    for j in journals:
        if j.lower() in pub:
            journal_hit = True
            reasons.append(f"journal: {j}")
            break

    # No include keywords configured → keep everything at a neutral score.
    configured_include = [k for k in include if (k or "").strip()]
    unique_hits = sorted({h.lower() for h in include_hits})
    if not configured_include:
        score = 3.0
        reasons.append("no include_keywords; keeping item")
    elif not unique_hits:
        score = 2.0 if journal_hit else 0.0
    else:
        # 1 hit → 3, 2 → 4, 3+ → 5 so a single keyword clears min_rule_score.
        score = float(min(5, 2 + len(unique_hits)))
        reasons.append("keywords: " + ", ".join(sorted(set(include_hits), key=str.lower)))
        if journal_hit:
            score = min(5.0, score + 1.0)

    skipped = score < min_rule and bool(configured_include)
    return ScoredItem(
        item=item,
        rule_score=score,
        reasons=reasons,
        skipped=skipped,
        skip_reason="below_min_rule_score" if skipped else "",
    )


def filter_items(items: list[FeedItem], profile: dict[str, Any]) -> tuple[list[ScoredItem], list[ScoredItem]]:
    kept: list[ScoredItem] = []
    skipped: list[ScoredItem] = []
    for item in items:
        scored = score_item(item, profile)
        if scored.skipped:
            skipped.append(scored)
        else:
            kept.append(scored)
    kept.sort(key=lambda s: (s.rule_score, s.item.date or ""), reverse=True)
    return kept, skipped
