#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-$REPO/.venv/bin/python}"
LABEL="com.zotero.rss.analyzer"
DEST="$HOME/Library/LaunchAgents/${LABEL}.plist"
TEMPLATE="$REPO/deploy/launchd/${LABEL}.plist.template"

if [[ ! -x "$PYTHON" ]]; then
  echo "Python not found at $PYTHON"
  echo "Create a venv first: python3 -m venv .venv && .venv/bin/pip install -e ."
  exit 1
fi

mkdir -p "$REPO/logs" "$HOME/Library/LaunchAgents"
sed -e "s|__REPO_ROOT__|${REPO}|g" -e "s|__PYTHON__|${PYTHON}|g" "$TEMPLATE" > "$DEST"
launchctl unload "$DEST" 2>/dev/null || true
launchctl load "$DEST"
echo "Installed $DEST"
echo "Interval: 6 hours. Test with: launchctl start $LABEL"
echo "Logs: $REPO/logs/launchd.out.log"
