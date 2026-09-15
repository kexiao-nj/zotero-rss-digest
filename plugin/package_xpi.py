#!/usr/bin/env python3
"""Pack plugin/ into an installable Zotero 10 XPI."""
from __future__ import annotations

import struct
import zlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "build" / "rss-digest.xpi"
INCLUDE = ("manifest.json", "bootstrap.js", "prefs.js", "content", "locale")


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


def main() -> None:
    write_icon(ROOT / "content" / "icon.png", 48)
    write_icon(ROOT / "content" / "icon@2x.png", 96)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for name in INCLUDE:
            add(z, ROOT / name, name)
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
