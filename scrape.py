#!/usr/bin/env python3
"""Scrape GitHub starred repos, detect changes, update README.md + CSV + JSON.

Usage: python3 scrape.py [username]
"""

import csv
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request

from engine import UNCATEGORIZED, classify

USERNAME = sys.argv[1] if len(sys.argv) > 1 else "budi-imam-prasetyo"
API = f"https://api.github.com/users/{USERNAME}/starred"
DIR = os.path.dirname(os.path.abspath(__file__))


def fetch_stars():
    token = os.environ.get("GITHUB_TOKEN")
    page, all_repos = 1, []
    while True:
        req = urllib.request.Request(f"{API}?per_page=100&page={page}")
        req.add_header("User-Agent", "github-stars-scraper/1.0")
        if token:
            # Authenticated: 5000 req/h instead of 60 — avoids CI rate limits.
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        if not data:
            break
        all_repos.extend(data)
        if len(data) < 100:
            break
        page += 1
        time.sleep(0.5)
    return all_repos


def build_rows(raw):
    rows = []
    for r in raw:
        rows.append({
            "repo": r["full_name"],
            "url": r["html_url"],
            "stars": r["stargazers_count"],
            "language": r.get("language") or "",
            "description": (r.get("description") or "").replace("\n", " ")[:120],
            "topics": ", ".join(r.get("topics", [])),
            "created": r["created_at"][:10],
            "forks": r["forks_count"],
            "license": (r.get("license") or {}).get("spdx_id", ""),
        })
    rows.sort(key=lambda x: x["stars"], reverse=True)
    return rows


def save_json(rows):
    path = os.path.join(DIR, "budi-stars.json")
    with open(path, "w") as f:
        json.dump(rows, f, indent=2)


def save_csv(rows):
    path = os.path.join(DIR, "budi-stars.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)


def detect_changes(rows):
    """True if star data differs from the last committed state.

    Preferred source: the previously committed budi-stars.json at git HEAD
    (works both locally and in CI, where the .bak file doesn't persist).
    Fallback: the local .bak file, for non-git usage.
    """
    new_rows = json.dumps(rows)
    try:
        head = subprocess.run(
            ["git", "show", "HEAD:budi-stars.json"],
            capture_output=True, text=True, check=True, cwd=DIR,
        ).stdout
        # Compare parsed JSON, not raw bytes: saves to disk are indented,
        # so byte/hash comparison against json.dumps(rows) never matches.
        if json.loads(head) == rows:
            return False
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        pass

    bak = os.path.join(DIR, "budi-stars.json.bak")
    if os.path.exists(bak):
        with open(bak) as f:
            old_hash = hashlib.md5(f.read().encode()).hexdigest()
        if old_hash == hashlib.md5(new_rows.encode()).hexdigest():
            return False
    with open(bak, "w") as f:
        json.dump(rows, f)
    return True




def generate_readme(rows):
    from engine import CATEGORIES
    cats = {c: [] for c in CATEGORIES}
    cats[UNCATEGORIZED] = []

    for r in rows:
        cat = classify(r)[0]
        if cat not in cats:
            cats[cat] = []
        cats[cat].append(r)

    # Lang stats
    langs = {}
    for r in rows:
        l = r["language"] or "Unknown"
        langs[l] = langs.get(l, 0) + 1
    langs_sorted = sorted(langs.items(), key=lambda x: -x[1])

    def rr(r):
        desc = (r["description"] or "—")[:80]
        return f'| [{r["repo"]}]({r["url"]}) | {r["stars"]:,} | {r["language"]} | {desc} |'

    L = []
    L.append("# ⭐ My Starred Repositories\n")
    L.append(f"> {len(rows)} repositories starred on GitHub. Categorized by domain.\n")

    # TOC
    def cat_anchor(name):
        # GitHub github-slugger: lowercase, strip non-alphanum except space/hyphen, space→hyphen
        import re
        a = name.lower()
        a = re.sub(r'[^\w\s-]', '', a)
        a = a.replace(' ', '-')
        return a

    L.append("| # | Category | Repos |")
    L.append("|---|----------|-------|")
    toc_idx = 0
    for cat_name, items in cats.items():
        if not items:
            continue
        toc_idx += 1
        anchor = cat_anchor(cat_name)
        L.append(f"| {toc_idx} | [{cat_name}](#{anchor}) | {len(items)} |")
    L.append("")

    L.append("---\n")

    for cat_name, items in cats.items():
        if not items:
            continue
        L.append(f"## {cat_name}\n")
        L.append("| Repository | ⭐ | Language | Description |")
        L.append("|---|---:|---|---|")
        for r in items:
            L.append(rr(r))
        L.append("")

    L.append("---\n")
    L.append("## 📊 Stats\n")
    L.append("| Metric | Value |")
    L.append("|---|---|")
    L.append(f"| Total starred | {len(rows)} |")
    if langs_sorted:
        L.append(f"| Top language | {langs_sorted[0][0]} ({langs_sorted[0][1]} repos) |")
    if len(langs_sorted) >= 3:
        L.append(f"| Runner-up | {langs_sorted[1][0]} ({langs_sorted[1][1]}), {langs_sorted[2][0]} ({langs_sorted[2][1]}) |")
    if rows:
        L.append(f"| Most starred | {rows[0]['repo']} ({rows[0]['stars']:,} ⭐) |")
    L.append(f"| Own repos starred | {len(cats.get('🔧 Own Projects', []))} |")

    with open(os.path.join(DIR, "README.md"), "w") as f:
        f.write("\n".join(L) + "\n")


# --- main ---
def main():
    print(f"Fetching stars for @{USERNAME}...")
    raw = fetch_stars()
    print(f"Fetched {len(raw)} repos")

    rows = build_rows(raw)
    save_json(rows)
    save_csv(rows)

    if detect_changes(rows):
        generate_readme(rows)
        print(f"README.md updated — {len(rows)} repos, changes detected")
    else:
        print("No changes detected — README.md unchanged")


if __name__ == "__main__":
    main()
