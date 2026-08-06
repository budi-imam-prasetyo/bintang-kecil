#!/usr/bin/env bash
# Scrape GitHub stars, update README, commit & push
# Usage: ./update.sh [username]
set -euo pipefail
cd "$(dirname "$0")"

python3 scrape.py "${1:-budi-imam-prasetyo}"

# If scrape changed files, commit and push
if ! git diff --quiet HEAD 2>/dev/null || ! git diff --cached --quiet 2>/dev/null || [ -n "$(git ls-files --others --exclude-standard)" ]; then
    git add -A
    git commit -m "Update stars: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    git push origin main
    echo "Pushed to origin/main"
else
    echo "Nothing to push"
fi
