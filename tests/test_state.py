from pathlib import Path

from zotero_rss_analyzer.state import load_state, mark_seen, save_state, seen_set


def test_state_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    state = load_state(path)
    assert seen_set(state) == set()
    mark_seen(state, ["a", "b"], report_path="/tmp/r.md")
    save_state(path, state)
    again = load_state(path)
    assert seen_set(again) == {"a", "b"}
    assert again["last_report"] == "/tmp/r.md"
    assert again["runs"]
