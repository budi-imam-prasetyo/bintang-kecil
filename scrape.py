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
import urllib.error
import urllib.request

from engine import UNCATEGORIZED, classify

USERNAME = sys.argv[1] if len(sys.argv) > 1 else "budi-imam-prasetyo"
API = f"https://api.github.com/users/{USERNAME}/starred"
DIR = os.path.dirname(os.path.abspath(__file__))

# Network reliability: bounded retries with linear backoff.
HTTP_TIMEOUT = 30        # seconds per request
MAX_ATTEMPTS = 3         # 1 try + 2 retries — never unbounded
RETRY_BACKOFF = 2        # seconds before attempt n: (n-1) * RETRY_BACKOFF


def _fetch_page(url, token):
    """Fetch one API page with timeout + bounded retries.

    Retries transient failures (network errors, 5xx, rate-limit 403) with
    backoff.  Other HTTP errors (401/404/...) fail fast with a clear
    message.  Raises RuntimeError after MAX_ATTEMPTS.
    """
    last_err = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if attempt > 1:
            delay = (attempt - 1) * RETRY_BACKOFF
            print(f"  retry {attempt - 1}/{MAX_ATTEMPTS - 1} in {delay}s "
                  f"after: {last_err}")
            time.sleep(delay)
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "github-stars-scraper/1.0")
        if token:
            # Authenticated: 5000 req/h instead of 60 — avoids CI rate limits.
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code >= 500 or e.code == 403:
                last_err = f"HTTP {e.code} {e.reason}"
                continue
            raise RuntimeError(
                f"GitHub API request failed permanently: HTTP {e.code} "
                f"{e.reason} for {url}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = f"{type(e).__name__}: {e}"
            continue
    raise RuntimeError(
        f"GitHub API request failed after {MAX_ATTEMPTS} attempts: {url} "
        f"(last error: {last_err})")


def fetch_stars():
    token = os.environ.get("GITHUB_TOKEN")
    page, all_repos = 1, []
    while True:
        data = _fetch_page(f"{API}?per_page=100&page={page}", token)
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
        if not rows:
            # Empty dataset: write a header-only CSV (stable fieldnames)
            # instead of crashing on rows[0].
            w = csv.DictWriter(f, fieldnames=[
                "repo", "url", "stars", "language", "description",
                "topics", "created", "forks", "license"])
            w.writeheader()
            return
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
        # Resolve the data file path relative to the repo root (not cwd),
        # so the script keeps working when moved into a subdirectory.
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True, cwd=DIR,
        ).stdout.strip()
        data_rel = os.path.relpath(os.path.join(DIR, "budi-stars.json"), root)
        head = subprocess.run(
            ["git", "show", f"HEAD:{data_rel}"],
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




def generate_readme(rows, cat_map=None):
    from engine import CATEGORIES
    cats = {c: [] for c in CATEGORIES}
    cats[UNCATEGORIZED] = []

    for r in rows:
        # classify() is deterministic and this is a single pass over rows
        # (no repeated classification of the same row) — README, stats and
        # grouping all come from this one loop.
        if cat_map and (r["repo"] or "").strip() in cat_map:
            cat = cat_map[r["repo"].strip()]["final"]
        else:
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
    # --laya (or USE_LAYA=1): run the laya_classify re-sorting pass over all
    # repos before generating the README.  Without it, behaviour is
    # byte-identical to the rules-only pipeline.
    args = [a for a in sys.argv[1:]]
    use_laya = "--laya" in args or os.environ.get("USE_LAYA") == "1"
    username = next((a for a in args if not a.startswith("-")), "budi-imam-prasetyo")
    global USERNAME
    USERNAME = username

    print(f"Fetching stars for @{USERNAME}...")
    raw = fetch_stars()
    print(f"Fetched {len(raw)} repos")

    rows = build_rows(raw)
    save_json(rows)
    save_csv(rows)

    cat_map = None
    if use_laya:
        from laya_classify import audit_lines, classify_all, summarize
        print("Running Laya re-classification pass...")
        cat_map = classify_all(rows)
        if cat_map:
            changed, counts = summarize(cat_map)
            print(f"  laya decided {len(cat_map)} repos; "
                  f"{changed} re-categorized vs rules; sources={counts}")
            for line in audit_lines(cat_map):
                print(line)
        else:
            print("  laya unavailable — README keeps rules-only categories")

    changed_data = detect_changes(rows)
    # With a Laya pass the rows themselves may equal HEAD while the
    # category assignment changed — regenerate whenever Laya decided.
    # Deterministic Laya output keeps an unchanged README byte-identical.
    if changed_data or (use_laya and cat_map):
        generate_readme(rows, cat_map=cat_map)
        print(f"README.md updated — {len(rows)} repos, changes detected")
    else:
        print("No changes detected — README.md unchanged")


if __name__ == "__main__":
    main()
