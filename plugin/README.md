# Plugin pack

User-facing docs:

- [中文 README](../README.md)
- [English README](../README.en.md)

Build:

```bash
python3 plugin/package_xpi.py
```

Output:

- `../build/rss-digest.xpi`
- `../dist/rss-digest.xpi` and `../dist/rss-digest-<version>.xpi`
- `updates.json` with `update_link` + `update_hash` (Zotero auto-update)

Version comes from `manifest.json`. After packing, commit those files and push `main` so installed copies can update.
