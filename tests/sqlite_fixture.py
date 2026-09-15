from __future__ import annotations

import sqlite3
from pathlib import Path


def build_fixture_db(path: Path) -> Path:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE feeds (
          libraryID INTEGER PRIMARY KEY,
          name TEXT NOT NULL,
          url TEXT NOT NULL,
          lastUpdate TIMESTAMP,
          lastCheck TIMESTAMP,
          lastCheckError TEXT,
          cleanupReadAfter INT,
          cleanupUnreadAfter INT,
          refreshInterval INT
        );
        CREATE TABLE items (
          itemID INTEGER PRIMARY KEY,
          itemTypeID INTEGER NOT NULL,
          dateAdded TIMESTAMP,
          dateModified TIMESTAMP,
          clientDateModified TIMESTAMP,
          libraryID INTEGER NOT NULL,
          key TEXT NOT NULL,
          version INTEGER DEFAULT 0,
          clientVersion INTEGER DEFAULT 0,
          synced INTEGER DEFAULT 0
        );
        CREATE TABLE feedItems (
          itemID INTEGER PRIMARY KEY,
          guid TEXT NOT NULL UNIQUE,
          readTime TIMESTAMP,
          translatedTime TIMESTAMP
        );
        CREATE TABLE fieldsCombined (
          fieldID INTEGER PRIMARY KEY,
          fieldName TEXT,
          label TEXT,
          fieldFormatID INT,
          custom INT
        );
        CREATE TABLE itemDataValues (
          valueID INTEGER PRIMARY KEY,
          value TEXT
        );
        CREATE TABLE itemData (
          itemID INTEGER,
          fieldID INTEGER,
          valueID INTEGER,
          PRIMARY KEY (itemID, fieldID)
        );
        CREATE TABLE creators (
          creatorID INTEGER PRIMARY KEY,
          firstName TEXT,
          lastName TEXT,
          fieldMode INTEGER
        );
        CREATE TABLE itemCreators (
          itemID INTEGER,
          creatorID INTEGER,
          creatorTypeID INTEGER DEFAULT 1,
          orderIndex INTEGER DEFAULT 0
        );
        """
    )
    con.execute(
        "INSERT INTO feeds(libraryID,name,url,lastCheck,refreshInterval) "
        "VALUES (2,'Cell','http://cell.example/rss','2026-09-10 08:00:00',60)"
    )
    fields = [
        (1, "title"),
        (2, "abstractNote"),
        (3, "url"),
        (4, "DOI"),
        (5, "publicationTitle"),
        (6, "date"),
    ]
    con.executemany("INSERT INTO fieldsCombined(fieldID,fieldName) VALUES (?,?)", fields)

    def add_item(item_id, guid, date_added, values, authors, read_time=None):
        con.execute(
            "INSERT INTO items(itemID,itemTypeID,dateAdded,dateModified,clientDateModified,libraryID,key) "
            "VALUES (?,?,?,?,?,2,?)",
            (item_id, 1, date_added, date_added, date_added, f"KEY{item_id}"),
        )
        con.execute(
            "INSERT INTO feedItems(itemID,guid,readTime) VALUES (?,?,?)",
            (item_id, guid, read_time),
        )
        for field_id, value in values.items():
            vid = item_id * 100 + field_id
            con.execute(
                "INSERT INTO itemDataValues(valueID,value) VALUES (?,?)", (vid, value)
            )
            con.execute(
                "INSERT INTO itemData(itemID,fieldID,valueID) VALUES (?,?,?)",
                (item_id, field_id, vid),
            )
        for i, (first, last) in enumerate(authors):
            cid = item_id * 10 + i
            con.execute(
                "INSERT INTO creators(creatorID,firstName,lastName,fieldMode) VALUES (?,?,?,0)",
                (cid, first, last),
            )
            con.execute(
                "INSERT INTO itemCreators(itemID,creatorID,orderIndex) VALUES (?,?,?)",
                (item_id, cid, i),
            )

    add_item(
        1,
        "guid-spatial",
        "2026-09-09 10:00:00",
        {
            1: "Whole-transcriptome spatial imaging",
            2: "RT&amp;T-AMP-MERFISH enables whole-transcriptome-scale spatial imaging of single cells in intact tissues.",
            3: "https://example.org/paper1",
            4: "10.1016/j.cell.2026.06.027",
            5: "Cell",
            6: "2026-09-08 2026-09-08 00:00:00",
        },
        [("Limor", "Cohen")],
    )
    add_item(
        2,
        "guid-unrelated",
        "2026-09-09 11:00:00",
        {
            1: "An unrelated economics commentary",
            2: "Markets rose on Tuesday.",
            3: "https://example.org/paper2",
            5: "News",
            6: "2026-09-09",
        },
        [("Ada", "Smith")],
        read_time="2026-09-09 12:00:00",
    )
    add_item(
        3,
        "guid-old",
        "2020-01-01 00:00:00",
        {
            1: "Ancient spatial atlas",
            2: "A long historical spatial transcriptomics methods paper used only for lookback tests.",
            3: "https://example.org/old",
            5: "Cell",
            6: "2020-01-01",
        },
        [("Old", "Author")],
    )
    con.commit()
    con.close()
    return path
