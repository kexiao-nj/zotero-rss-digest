from zotero_rss_analyzer.models import FeedItem
from zotero_rss_analyzer.relevance import filter_items, score_item


def _item(**kwargs) -> FeedItem:
    base = dict(
        guid="g1",
        item_id=1,
        key="ABC",
        library_id=2,
        feed_name="Cell",
        feed_url="http://example",
        title="Spatial transcriptomics of single cells",
        abstract="We image the genome in tissues.",
        publication_title="Cell",
    )
    base.update(kwargs)
    return FeedItem(**base)


PROFILE = {
    "topics": ["spatial omics"],
    "include_keywords": ["spatial", "CRISPR"],
    "exclude_keywords": ["economics"],
    "require_any_keywords": [],
    "journal_whitelist": [],
    "feed_allowlist": [],
    "feed_blocklist": [],
    "min_rule_score": 2,
}


def test_include_keyword_scores() -> None:
    scored = score_item(_item(), PROFILE)
    assert not scored.skipped
    assert scored.rule_score >= 2


def test_exclude_drops() -> None:
    scored = score_item(_item(title="economics of hospitals", abstract=""), PROFILE)
    assert scored.skipped
    assert scored.skip_reason == "exclude_keywords"


def test_filter_splits() -> None:
    kept, skipped = filter_items(
        [
            _item(),
            _item(guid="g2", title="An economics essay", abstract="markets"),
        ],
        PROFILE,
    )
    assert len(kept) == 1
    assert len(skipped) == 1


def test_empty_keywords_keep_all() -> None:
    profile = {**PROFILE, "include_keywords": [], "topics": [], "min_rule_score": 2}
    scored = score_item(_item(title="Anything", abstract="zzz"), profile)
    assert not scored.skipped
    assert scored.rule_score == 3
