#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$HOME/Library/LaunchAgents/com.zotero.rss.analyzer.plist"
launchctl unload "$DEST" 2>/dev/null || true
rm -f "$DEST"
echo "Removed launchd agent (if it was installed)."
