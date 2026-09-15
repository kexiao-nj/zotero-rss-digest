from pathlib import Path

from zotero_rss_analyzer.config import AppConfig
from zotero_rss_analyzer.pipeline import run_pipeline

from sqlite_fixture import build_fixture_db


def _cfg(tmp_path: Path) -> AppConfig:
    profile = {
        "topics": ["spatial"],
        "include_keywords": ["spatial"],
        "exclude_keywords": ["economics"],
        "require_any_keywords": [],
        "journal_whitelist": [],
        "feed_allowlist": [],
        "feed_blocklist": [],
        "min_rule_score": 2,
        "min_llm_score": 3,
        "priority_thresholds": {"close_read": 4, "skim": 3},
    }
    data = {
        "zotero": {
            "data_dir": str(tmp_path),
            "copy_retries": 1,
            "copy_retry_seconds": 0.1,
        },
        "run": {
            "first_run_lookback_days": 30,
            "llm_batch_cap": 30,
            "enrich": False,
            "language": "zh",
        },
        "llm": {},
        "output": {
            "reports_dir": "reports",
            "findings_file": "findings.md",
            "skipped_file": "reports/skipped.jsonl",
            "state_file": "data/state.json",
        },
    }
    return AppConfig(data, tmp_path, profile)


def test_pipeline_rule_only(tmp_path: Path) -> None:
    db = build_fixture_db(tmp_path / "zotero.sqlite")
    cfg = _cfg(tmp_path)
    stats = run_pipeline(cfg, use_llm=False, enrich=False, process_all=True, db_path=db)
    assert stats.new_items == 3
    assert stats.related == 2
    assert stats.skipped == 1
    assert stats.report_path
    md = Path(stats.report_path).read_text(encoding="utf-8")
    assert "Whole-transcriptome spatial imaging" in md
    skipped = (tmp_path / "reports" / "skipped.jsonl").read_text(encoding="utf-8")
    assert "guid-unrelated" in skipped
    findings = (tmp_path / "findings.md").read_text(encoding="utf-8")
    assert "spatial imaging" in findings
    stats2 = run_pipeline(cfg, use_llm=False, enrich=False, db_path=db)
    assert stats2.empty
    assert stats2.new_items == 0


def test_lookback_does_not_redigest_history(tmp_path: Path) -> None:
    db = build_fixture_db(tmp_path / "zotero.sqlite")
    cfg = _cfg(tmp_path)
    stats = run_pipeline(
        cfg, use_llm=False, enrich=False, lookback_days=14, db_path=db
    )
    assert stats.new_items == 2
    md = Path(stats.report_path).read_text(encoding="utf-8")
    assert "Ancient spatial atlas" not in md
    stats2 = run_pipeline(cfg, use_llm=False, enrich=False, db_path=db)
    assert stats2.empty
