from zotero_rss_analyzer.models import FeedItem, ScoredItem
from zotero_rss_analyzer.report import render_digest


def test_digest_contains_import_hint() -> None:
    item = FeedItem(
        guid="g",
        item_id=1,
        key="K",
        library_id=2,
        feed_name="Cell",
        feed_url="http://x",
        title="A paper",
        abstract="Hello",
        url="http://paper",
        doi="10.1/xyz",
        date="2026-09-09",
        authors=["A Author"],
    )
    scored = ScoredItem(
        item=item,
        rule_score=4,
        llm_score=4,
        card={
            "one_liner": "空间成像",
            "problem": "",
            "method": "",
            "conclusion": "要点",
            "why_relevant": "spatial",
            "suggestion": "精读",
        },
    )
    md = render_digest(
        related=[scored],
        skipped=[],
        themes=["空间组学"],
        profile={"priority_thresholds": {"close_read": 4, "skim": 3}},
        new_count=1,
    )
    assert "RSS Digest" in md
    assert "优先阅读" in md
    assert "添加到我的文库" in md
    assert "不自动写库" in md
    assert "空间组学" in md
