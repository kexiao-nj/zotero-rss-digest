from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def empty_state() -> dict[str, Any]:
    return {
        "seen_guids": [],
        "last_run": None,
        "last_report": None,
        "runs": [],
    }


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_state()
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    data.setdefault("seen_guids", [])
    data.setdefault("runs", [])
    return data


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    tmp.replace(path)


def seen_set(state: dict[str, Any]) -> set[str]:
    return set(state.get("seen_guids") or [])


def mark_seen(state: dict[str, Any], guids: list[str], report_path: str | None) -> None:
    existing = seen_set(state)
    existing.update(guids)
    state["seen_guids"] = sorted(existing)
    state["last_run"] = _now()
    if report_path:
        state["last_report"] = report_path
    runs = state.setdefault("runs", [])
    runs.append(
        {
            "at": state["last_run"],
            "new_guids": len(guids),
            "report": report_path,
        }
    )
    state["runs"] = runs[-50:]
