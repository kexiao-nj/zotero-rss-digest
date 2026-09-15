from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests

from .models import FeedItem, ScoredItem

log = logging.getLogger(__name__)

JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)


def _extract_json(text: str) -> Any:
    text = text.strip()
    fenced = JSON_FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def chat_completion(settings: dict[str, Any], messages: list[dict[str, str]]) -> str:
    url = settings["base_url"].rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings["model"],
        "temperature": settings["temperature"],
        "max_tokens": settings["max_tokens"],
        "messages": messages,
    }
    resp = requests.post(
        url, headers=headers, json=payload, timeout=settings["timeout_seconds"]
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def fallback_card(item: FeedItem, score: float, reasons: list[str]) -> dict[str, Any]:
    snippet = (item.abstract or item.title or "")[:280]
    suggestion = "忽略"
    if score >= 4:
        suggestion = "精读"
    elif score >= 3:
        suggestion = "扫摘要"
    return {
        "one_liner": snippet.split(". ")[0][:160] if snippet else item.title,
        "problem": "",
        "method": "",
        "conclusion": snippet,
        "why_relevant": "; ".join(reasons) or "规则筛选命中",
        "suggestion": suggestion,
    }


def distill_item(
    scored: ScoredItem,
    profile: dict[str, Any],
    settings: dict[str, Any],
    language: str = "zh",
) -> ScoredItem:
    item = scored.item
    topics = ", ".join(profile.get("topics") or []) or "(unspecified)"
    prompt = f"""You are screening RSS papers against a research profile.
Return ONLY JSON with this shape:
{{
  "score": 0,
  "reason": "short",
  "one_liner": "short",
  "problem": "short",
  "method": "short",
  "conclusion": "short",
  "why_relevant": "short",
  "suggestion": "精读|扫摘要|忽略"
}}
score is 0-5 integer. Write text fields in {"Chinese" if language.startswith("zh") else "English"}.
Research topics: {topics}
Title: {item.title}
Feed/Journal: {item.feed_name} / {item.publication_title}
Authors: {item.author_line()}
Date: {item.date}
DOI: {item.doi}
Abstract: {item.abstract[:2500]}
Rule hits: {"; ".join(scored.reasons)}
"""
    try:
        raw = chat_completion(
            settings,
            [
                {
                    "role": "system",
                    "content": "You extract structured paper cards. JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        data = _extract_json(raw)
        score = float(data.get("score", scored.rule_score))
        scored.llm_score = max(0.0, min(5.0, score))
        scored.card = {
            "one_liner": data.get("one_liner") or "",
            "problem": data.get("problem") or "",
            "method": data.get("method") or "",
            "conclusion": data.get("conclusion") or "",
            "why_relevant": data.get("why_relevant") or data.get("reason") or "",
            "suggestion": data.get("suggestion") or fallback_card(item, score, scored.reasons)["suggestion"],
        }
        if data.get("reason"):
            scored.reasons.append(str(data["reason"]))
    except (requests.RequestException, KeyError, ValueError, json.JSONDecodeError) as exc:
        log.warning("LLM distill failed for %s: %s", item.guid, exc)
        scored.card = fallback_card(item, scored.rule_score, scored.reasons)
    return scored


def cluster_items(
    related: list[ScoredItem],
    settings: dict[str, Any],
    language: str = "zh",
) -> list[str]:
    if len(related) < 3 or not settings.get("enabled"):
        return []
    lines = []
    for i, s in enumerate(related[:30], 1):
        lines.append(f"{i}. {s.item.title} [{s.item.feed_name}] score={s.score}")
    prompt = f"""Cluster these papers into 3-7 themes.
Return JSON: {{"themes": ["theme — one sentence", ...]}}
Language: {"Chinese" if language.startswith("zh") else "English"}.
Papers:
{chr(10).join(lines)}
"""
    try:
        raw = chat_completion(
            settings,
            [
                {"role": "system", "content": "JSON only."},
                {"role": "user", "content": prompt},
            ],
        )
        data = _extract_json(raw)
        themes = data.get("themes") or []
        return [str(t) for t in themes if t]
    except (requests.RequestException, KeyError, ValueError, json.JSONDecodeError) as exc:
        log.warning("Clustering failed: %s", exc)
        return []
