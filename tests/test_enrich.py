from zotero_rss_analyzer.enrich import extract_arxiv, extract_doi
from zotero_rss_analyzer.models import FeedItem


def _item(**kwargs) -> FeedItem:
    data = dict(
        guid="g",
        item_id=1,
        key="K",
        library_id=2,
        feed_name="arXiv",
        feed_url="http://x",
    )
    data.update(kwargs)
    return FeedItem(**data)


def test_extract_doi_from_field() -> None:
    assert extract_doi(_item(doi="https://doi.org/10.1038/s41586-021-03819-2")) == (
        "10.1038/s41586-021-03819-2"
    )


def test_extract_arxiv_from_url() -> None:
    item = _item(url="https://arxiv.org/abs/2401.12345")
    assert extract_arxiv(item) == "2401.12345"
