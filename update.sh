#!/usr/bin/env bash

# Scrape GitHub stars, update README, commit & push.
#
# Usage:
#   ./update.sh [username]
#
# Exit status:
#   0 - scrape completed and changes were pushed, or nothing changed
#   1 - push failed after retries

set -euo pipefail

SCRIPT_DIR="$(dirname -- "$(readlink -f -- "$0")")"
cd "$SCRIPT_DIR"

USERNAME="${1:-budi-imam-prasetyo}"

echo "Scraping GitHub stars for: $USERNAME"
python3 scrape.py "$USERNAME"

# Check whether the scrape produced any changes.
if [[ -z "$(git status --porcelain)" ]]; then
    echo "Nothing to push."
    exit 0
fi

echo "Changes detected. Committing..."

git add -A
git commit -m "Update stars: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Push with retry: 3 attempts, 5-second backoff.
for attempt in 1 2 3; do
    if git push origin main; then
        echo "Pushed to origin/main."
        exit 0
    fi

    if (( attempt < 3 )); then
        echo "Push attempt $attempt failed, retrying in 5s..."
        sleep 5
    fi
done

echo "Push failed after 3 attempts — commit left local, will retry next run."
exit 1