from pathlib import Path

from zotero_rss_analyzer.feed_reader import clean_text, parse_zotero_json_items, read_from_sqlite

from sqlite_fixture import build_fixture_db


def test_read_feed_items(tmp_path: Path) -> None:
    db = build_fixture_db(tmp_path / "zotero.sqlite")
    feeds, items, _ = read_from_sqlite(tmp_path, db_path=db)
    assert len(feeds) == 1
    assert feeds[0].name == "Cell"
    assert feeds[0].item_count == 3
    assert feeds[0].unread_count == 2
    by_guid = {it.guid: it for it in items}
    spatial = by_guid["guid-spatial"]
    assert spatial.title == "Whole-transcriptome spatial imaging"
    assert "RT&T-AMP-MERFISH" in spatial.abstract
    assert spatial.doi == "10.1016/j.cell.2026.06.027"
    assert spatial.date == "2026-09-08"
    assert spatial.authors == ["Limor Cohen"]
    assert spatial.metadata_thin is False


def test_clean_text_strips_rss_html() -> None:
    raw = (
        '<p xmlns="http://www.w3.org/1999/xhtml">Nature Genetics, '
        '<a href="https://example.org">doi:1</a></p>The authors present a resource.'
    )
    assert "<p" not in clean_text(raw)
    assert "The authors present a resource." in clean_text(raw)
    assert clean_text("RT&amp;T-AMP") == "RT&T-AMP"


def test_clean_text_decodes_entities_and_encoded_tags() -> None:
    encoded = "&lt;p&gt;Hello &amp;amp; world&lt;/p&gt;"
    assert clean_text(encoded) == "Hello & world"
    assert clean_text("P &lt; 0.05 and n &gt; 10") == "P < 0.05 and n > 10"
    assert clean_text("P < 0.05 and n > 10") == "P < 0.05 and n > 10"
    assert clean_text("H<sub>2</sub>O &nbsp; in&nbsp;situ") == "H 2 O in situ"
    assert "<i>" not in clean_text("&lt;i&gt;E. coli&lt;/i&gt;")
    decoded = clean_text("&#181;m")
    assert "&#" not in decoded
    assert decoded.endswith("m")


def test_parse_zotero_json_items_skips_feed_metadata() -> None:
    payload = [
        {"data": {"name": "Cell", "url": "http://cell.example/rss"}},
        {
            "key": "ABC123",
            "library": {"id": 2, "name": "Cell"},
            "data": {
                "key": "ABC123",
                "itemType": "journalArticle",
                "title": "Spatial atlas of the cortex",
                "abstractNote": "A long enough abstract about spatial transcriptomics in tissue.",
                "url": "https://example.org/paper",
                "DOI": "10.1038/s41586-001",
                "date": "2026-09-08",
                "publicationTitle": "Cell",
                "creators": [{"firstName": "Ada", "lastName": "Lovelace"}],
            },
        },
    ]
    items = parse_zotero_json_items(payload)
    assert len(items) == 1
    assert items[0].title == "Spatial atlas of the cortex"
    assert items[0].authors == ["Ada Lovelace"]
    assert items[0].doi == "10.1038/s41586-001"
    assert items[0].feed_name == "Cell"

