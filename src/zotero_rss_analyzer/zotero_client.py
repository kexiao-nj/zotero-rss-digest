from __future__ import annotations

import logging
from typing import Any

import requests

from .models import ProbeResult

log = logging.getLogger(__name__)

LOCAL_API_HINT = (
    "Enable Zotero Local API: Settings → Advanced → "
    '"Allow other applications on this computer to communicate with Zotero". '
    "Zotero must stay running."
)


def _get(url: str, timeout: float = 3.0) -> requests.Response | None:
    try:
        return requests.get(url, timeout=timeout)
    except requests.RequestException as exc:
        log.debug("GET %s failed: %s", url, exc)
        return None


def check_local_api(base: str) -> tuple[bool, str]:
    resp = _get(f"{base.rstrip('/')}/")
    if resp is None:
        return False, f"Cannot reach {base}. Is Zotero running? {LOCAL_API_HINT}"
    if resp.status_code == 403:
        return False, f"Local API returned 403. {LOCAL_API_HINT}"
    if resp.status_code >= 400:
        return False, f"Local API returned HTTP {resp.status_code} from {base}/"
    return True, f"Local API OK ({resp.status_code}) at {base}/"


def try_feeds_http(base: str) -> tuple[bool, list[dict[str, Any]] | None]:
    """Probe undocumented feed endpoints. Returns (ok, payload_or_None)."""
    candidates = [
        f"{base.rstrip('/')}/feeds",
        f"{base.rstrip('/')}/users/0/feeds",
        f"{base.rstrip('/')}/users/0/items?itemType=feedItem&limit=1",
    ]
    for url in candidates:
        resp = _get(url)
        if resp is None:
            continue
        if resp.status_code != 200:
            log.debug("Feeds HTTP probe %s -> %s", url, resp.status_code)
            continue
        try:
            payload = resp.json()
        except ValueError:
            continue
        if isinstance(payload, list) and payload:
            return True, payload
        if isinstance(payload, dict) and payload:
            return True, [payload]
    return False, None


def ping_user_library(base: str) -> tuple[bool, str]:
    url = f"{base.rstrip('/')}/users/0/items?limit=1"
    resp = _get(url)
    if resp is None:
        return False, "user library unreachable"
    if resp.status_code == 200:
        total = resp.headers.get("Total-Results", "?")
        return True, f"user library reachable (Total-Results={total})"
    return False, f"user library HTTP {resp.status_code}"


def apply_api_probe(result: ProbeResult, base: str) -> ProbeResult:
    ok, detail = check_local_api(base)
    result.local_api_ok = ok
    lib_ok, lib_detail = ping_user_library(base) if ok else (False, "skipped")
    feeds_ok, _ = try_feeds_http(base) if ok else (False, None)
    result.feeds_http_ok = feeds_ok
    extra = f"{detail}; {lib_detail}"
    if not feeds_ok:
        extra += "; /api/feeds not available (expected — using SQLite)"
    else:
        extra += "; undocumented /api/feeds responded"
    result.local_api_detail = extra
    return result
