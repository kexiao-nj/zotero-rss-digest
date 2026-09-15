from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .models import ScoredItem


def _suggestion(scored: ScoredItem, profile: dict[str, Any]) -> str:
    if scored.card and scored.card.get("suggestion"):
        return scored.card["suggestion"]
    thresholds = profile.get("priority_thresholds") or {}
    close_read = float(thresholds.get("close_read", 4))
    skim = float(thresholds.get("skim", 3))
    if scored.score >= close_read:
        return "精读"
    if scored.score >= skim:
        return "扫摘要"
    return "忽略"


def _card_block(scored: ScoredItem, profile: dict[str, Any], index: int) -> list[str]:
    item = scored.item
    card = scored.card or {}
    lines = [
        f"### {index}. {item.title or '(untitled)'}",
        f"- Feed: {item.feed_name}"
        + (f" / {item.publication_title}" if item.publication_title else ""),
        f"- Authors: {item.author_line() or '—'}",
        f"- Date: {item.date or item.date_added or '—'}",
    ]
    if item.url:
        lines.append(f"- Link: {item.url}")
    if item.doi:
        lines.append(f"- DOI: {item.doi}")
    lines.append(f"- Score: {scored.score:g} (rule {scored.rule_score:g}"
                 + (f", llm {scored.llm_score:g}" if scored.llm_score is not None else "")
                 + ")")
    if item.metadata_thin:
        lines.append("- metadata: thin")
    if card.get("one_liner"):
        lines.append(f"- 一句话: {card['one_liner']}")
    if card.get("problem"):
        lines.append(f"- 问题: {card['problem']}")
    if card.get("method"):
        lines.append(f"- 方法: {card['method']}")
    if card.get("conclusion"):
        lines.append(f"- 要点: {card['conclusion']}")
    why = card.get("why_relevant") or "; ".join(scored.reasons)
    if why:
        lines.append(f"- 为何相关: {why}")
    lines.append(f"- 建议: {_suggestion(scored, profile)}")
    lines.append(
        "- 入库: 在 Zotero 订阅列表中打开该条目，右侧选择目标文件夹后点「添加到我的文库」。本 agent 不自动写库。"
    )
    lines.append("")
    return lines


def render_digest(
    *,
    related: list[ScoredItem],
    skipped: list[ScoredItem],
    themes: list[str],
    profile: dict[str, Any],
    new_count: int,
    when: date | None = None,
) -> str:
    day = when or date.today()
    thresholds = profile.get("priority_thresholds") or {}
    close_read = float(thresholds.get("close_read", 4))
    priority = [s for s in related if s.score >= close_read]
    rest = [s for s in related if s.score < close_read]
    lines = [
        f"# RSS Digest · {day.isoformat()}",
        "",
        f"- 新条目: {new_count} | 相关: {len(related)} | 跳过: {len(skipped)}",
        "",
    ]
    if themes:
        lines.append("## 本轮主题")
        for theme in themes:
            lines.append(f"- {theme}")
        lines.append("")
    lines.append("## 优先阅读")
    if not priority:
        lines.append("（本轮无达到精读阈值的条目）")
        lines.append("")
    else:
        for i, scored in enumerate(priority, 1):
            lines.extend(_card_block(scored, profile, i))
    if rest:
        lines.append("## 其余相关")
        lines.append("")
        start = len(priority) + 1
        for i, scored in enumerate(rest, start):
            lines.extend(_card_block(scored, profile, i))
    return "\n".join(lines).rstrip() + "\n"


def write_digest(path: Path, markdown: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return path


def append_skipped(path: Path, skipped: list[ScoredItem], run_id: str) -> None:
    if not skipped:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for s in skipped:
            rec = {
                "run": run_id,
                "guid": s.item.guid,
                "title": s.item.title,
                "feed": s.item.feed_name,
                "reason": s.skip_reason,
                "rule_score": s.rule_score,
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def update_findings(
    path: Path,
    *,
    related: list[ScoredItem],
    themes: list[str],
    when: date | None = None,
) -> None:
    if not related:
        return
    day = when or date.today()
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    block = [f"## {day.isoformat()}", "", f"_Updated {stamp}_", ""]
    if themes:
        block.append("Themes:")
        for theme in themes:
            block.append(f"- {theme}")
        block.append("")
    block.append("Papers:")
    for s in related:
        title = s.item.title or s.item.guid
        block.append(f"- ({s.score:g}) {title} — {s.item.feed_name}")
    block.append("")
    addition = "\n".join(block)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if not existing.startswith("# RSS Findings"):
            existing = "# RSS Findings\n\n" + existing
        path.write_text(existing.rstrip() + "\n\n" + addition, encoding="utf-8")
    else:
        path.write_text("# RSS Findings\n\n" + addition, encoding="utf-8")
