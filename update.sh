#!/usr/bin/env bash
# Scrape GitHub stars, detect changes, update README.md
# Usage: ./update.sh [username]
set -euo pipefail
cd "$(dirname "$0")"
python3 scrape.py "${1:-budi-imam-prasetyo}"
