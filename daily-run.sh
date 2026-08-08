#!/usr/bin/env bash

# Run scrape if not already run today.
# Used by systemd timer (06:00) and boot service (catch-up).

set -euo pipefail

SCRIPT_DIR="$(dirname -- "$(readlink -f -- "$0")")"

MARKER_DIR="$HOME/.cache/bintang-kecil"
MARKER="$MARKER_DIR/last-run"
LOCK="/tmp/github-stars-scrape.lock"
TODAY="$(date +%Y-%m-%d)"

# Prevent concurrent runs.
exec 200>"$LOCK"
flock -n 200 || {
    echo "Another run is in progress, exiting."
    exit 0
}

# Already ran today? Skip.
if [[ -f "$MARKER" ]] && [[ "$(cat "$MARKER")" == "$TODAY" ]]; then
    echo "Already ran today ($TODAY), skipping."
    exit 0
fi

echo "Running daily star scrape..."

cd "$SCRIPT_DIR"
bash "$SCRIPT_DIR/update.sh"

# Only mark as done if update.sh succeeded.
mkdir -p "$MARKER_DIR"
printf '%s\n' "$TODAY" > "$MARKER"

echo "Daily star scrape completed successfully."