# Zotero RSS Digest

[中文](README.md)

A **Zotero 10 plugin** that reads **RSS Feeds** in the left pane, filters them against your research profile, optionally distills cards with an OpenAI-compatible LLM (Chinese or English), and lets you save selected items into My Library.

**Current version: 0.3.1** · Compatible with **Zotero 10.0–10.0.\*** (including 10.0.2)

[**Download rss-digest.xpi (v0.3.1)**](https://github.com/kexiao-nj/zotero-rss-digest/raw/main/dist/rss-digest.xpi)

## Install

1. Download [rss-digest.xpi](https://github.com/kexiao-nj/zotero-rss-digest/raw/main/dist/rss-digest.xpi).
2. In Zotero: **Tools → Plugins → gear → Install Plugin From File…** and choose the downloaded `.xpi`.
3. **Fully quit and restart Zotero**.

The packaged plugin is also in [`dist/rss-digest.xpi`](https://github.com/kexiao-nj/zotero-rss-digest/blob/main/dist/rss-digest.xpi). This plugin does not register a Zotero Preference pane. Settings live in the plugin overlay.

Pack from source:

```bash
python3 plugin/package_xpi.py
```

Output: `build/rss-digest.xpi`.

## Use

Open **Tools → RSS Digest**. An overlay appears on the main window (Scan now / Rescan / Export Markdown / Results / Settings / Close).

| Action | What it does |
|---|---|
| **Scan now** | Incremental: unseen items inside the scan window. |
| **Rescan** | Scan again within the configured date range (default last 7 days), including GUIDs already seen. |
| **Export Markdown** | Save the current results as a `.md` file. Requires a completed scan. |
| **Results** | Show cards. |
| **Settings** | API, language, scan window, collection, topics / keywords. Click **Save settings** after edits. |
| **Add to My Library** | Uses Zotero’s own feed translation into the named collection, and attaches a digest note. |

High-scoring items are **not** saved automatically. You choose what enters the library.

Scan progress is shown on the results pane (feeds / LLM / translation / percent). Closing the overlay does not drop the latest results; they are also stored in `rss-digest-state.json` in the Zotero data directory.

## Settings

| Field | Meaning |
|---|---|
| Base URL / API Key / Model | OpenAI-compatible endpoint (DeepSeek, OpenRouter, local vLLM). **Leave the key empty for keyword-only scans (no translation, no LLM).** |
| Interval (hours) | Background scan timer. Default 6. |
| Lookback days / From–To | Only items in this window are scanned. Leave dates empty to use lookback days from today (**default 7**). Fill from/to for a fixed range (empty To means today). “Fill last N days” writes the lookback as dates. |
| Digest language | **中文**: title, abstract, and digest cards are translated into Simplified Chinese; original title/abstract are kept. **English**: cards stay in English. |
| Save-to collection | Target collection; created if missing. Default `RSS Digest`. |
| **Topics** | Research directions, one per line. Count toward the rule score with include keywords, and are sent to the LLM as your profile. |
| **Include keywords** | Keep terms, one per line. Case-insensitive substring match in title, abstract, journal, authors, and DOI. |
| **Exclude keywords** | Blocklist. Any hit skips the item; it is never sent to the LLM. |

You must click **Save settings**. **Test LLM** saves first, then calls the API.

## Scoring (Score on each card)

Score is **0–5 relevance**, not citation count. The card shows the LLM score when present, otherwise the rule score.

**Rule score (first filter)**

- Exclude hit → 0, dropped.
- Topics and Include **both empty** → every item starts at 3.
- No Include/Topic hits → 0, dropped.
- Hits → `min(5, 2 + number of distinct keywords)` (1 hit → 3, 2 → 4, 3+ → 5).
- Rule score **below 2** does not continue.

**LLM score (second pass)**

With an API key, the first **30** items that passed the rule filter are sent to the model for a 0–5 integer against your Topics. Overflow or LLM failure falls back to the rule score. LLM scores **below 3** are hidden.

**Suggestion**

| Score | Suggestion |
|---|---|
| ≥ 4 | Read closely / 精读 |
| ≥ 3 | Skim abstract / 扫摘要 |
| lower | Skip / 忽略 |

Results are sorted by final score, high to low.

## Language

When Chinese is selected and an API key is set, title, abstract, one-liner, and takeaway are translated into Simplified Chinese. Missed or failed translations get a second pass. Without an API key, cards stay in the source language.

## Data location

Seen GUIDs and the last scan live in `rss-digest-state.json` in the Zotero data directory (often `~/Zotero/rss-digest-state.json`).

## Developer notes

The packaged `manifest.json` must include `applications.zotero.id`, `update_url`, `strict_min_version`, and `strict_max_version` (`10.0.*`). Zotero 10 rejects the XPI without them.

Do not call `Zotero.ftl.addResourceIds` or `PreferencePanes.register`; both break Zotero’s built-in Settings sidebar.

The UI is an HTML overlay on the main window, not a standalone chrome window. Controls use `textarea` and clickable `div`s because HTML `input`/`button` often do not receive events inside the XUL main window.

## Automatic updates

Zotero’s add-on manager does the checking. The plugin does not ship a custom updater.

1. The installed XPI’s `manifest.json` has `applications.zotero.update_url`, which points at [`plugin/updates.json`](plugin/updates.json).
2. Zotero fetches that JSON on a timer, or when you choose **Tools → Plugins → gear → Check for Updates**.
3. If `version` is newer than the installed copy and `update_hash` (SHA-256 of the XPI) matches, Zotero downloads `update_link` and installs it.

To publish a new version:

1. Bump `version` in `plugin/manifest.json` (and the README).
2. From the repo root run `python3 plugin/package_xpi.py`. That writes `dist/rss-digest.xpi`, `dist/rss-digest-<version>.xpi`, and `plugin/updates.json` with `update_hash`.
3. Commit `plugin/manifest.json`, `plugin/updates.json`, and `dist/*.xpi`, then **push to `main`**. The live `update_url` is the file on GitHub.

Builds **0.2.17 and later** pick up later versions automatically. Older sideloaded XPIs that still point at a previous `update_url` need a one-time reinstall.

## Optional Python CLI

The repo still includes an offline CLI (`zotero-rss`) for Markdown digests without installing the plugin. It copies `zotero.sqlite` to read Feeds (the local API does not expose RSS).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
zotero-rss probe
zotero-rss run --no-llm --no-enrich
```

See `config/config.yaml` and `config/research_profile.yaml`.
