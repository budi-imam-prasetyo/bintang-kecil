#!/usr/bin/env bash
# Run scrape if not already run today
# Used by systemd timer (6AM) and boot service (catch-up)
set -euo pipefail

SCRIPT_DIR="/home/ryoukaii/Projects/github-stars"
MARKER_DIR="$HOME/.cache/bintang-kecil"
MARKER="$MARKER_DIR/last-run"
TODAY=$(date +%Y-%m-%d)

# Already ran today? Skip.
if [ -f "$MARKER" ] && [ "$(cat "$MARKER")" = "$TODAY" ]; then
    echo "Already ran today ($TODAY), skipping"
    exit 0
fi

echo "Running daily star scrape..."
cd "$SCRIPT_DIR"
bash update.sh

# Mark as done
mkdir -p "$MARKER_DIR"
echo "$TODAY" > "$MARKER"
