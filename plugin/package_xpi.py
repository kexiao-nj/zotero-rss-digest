#!/usr/bin/env python3
"""Pack plugin/ into an installable Zotero 10 XPI and refresh updates.json."""
from __future__ import annotations

import hashlib
import json
import shutil
import struct
import zlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
OUT = REPO / "build" / "rss-digest.xpi"
DIST = REPO / "dist"
INCLUDE = ("manifest.json", "bootstrap.js", "prefs.js", "content", "locale")
RAW_BASE = "https://raw.githubusercontent.com/kexiao-nj/zotero-rss-digest/main"


def png_chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def write_icon(path: Path, size: int) -> None:
    """Simple branded PNG so about:addons can render the plugin card."""
    margin = max(2, size // 16)
    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            if margin <= x < size - margin and margin <= y < size - margin:
                raw.extend((0x1F, 0x4E, 0x79, 255))
            else:
                raw.extend((0, 0, 0, 0))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + png_chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def add(z: zipfile.ZipFile, path: Path, arc: str) -> None:
    if path.is_dir():
        for child in sorted(path.iterdir()):
            add(z, child, f"{arc}/{child.name}")
    else:
        z.write(path, arc)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_updates(manifest: dict, versioned_name: str, digest: str) -> None:
    addon_id = manifest["applications"]["zotero"]["id"]
    apps = manifest["applications"]["zotero"]
    payload = {
        "addons": {
            addon_id: {
                "updates": [
                    {
                        "version": manifest["version"],
                        "update_link": f"{RAW_BASE}/dist/{versioned_name}",
                        "update_hash": f"sha256:{digest}",
                        "applications": {
                            "zotero": {
                                "strict_min_version": apps["strict_min_version"],
                                "strict_max_version": apps["strict_max_version"],
                            }
                        },
                    }
                ]
            }
        }
    }
    path = ROOT / "updates.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {path.relative_to(REPO)}")


def main() -> None:
    write_icon(ROOT / "content" / "icon.png", 48)
    write_icon(ROOT / "content" / "icon@2x.png", 96)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for name in INCLUDE:
            add(z, ROOT / name, name)

    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    version = manifest["version"]
    versioned_name = f"rss-digest-{version}.xpi"
    DIST.mkdir(parents=True, exist_ok=True)
    versioned = DIST / versioned_name
    latest = DIST / "rss-digest.xpi"
    shutil.copyfile(OUT, versioned)
    shutil.copyfile(OUT, latest)
    digest = sha256_file(OUT)
    write_updates(manifest, versioned_name, digest)
    print(f"Wrote {OUT.relative_to(REPO)} ({OUT.stat().st_size} bytes)")
    print(f"Wrote {versioned.relative_to(REPO)}")
    print(f"Wrote {latest.relative_to(REPO)}")
    print(f"sha256:{digest}")


if __name__ == "__main__":
    main()
