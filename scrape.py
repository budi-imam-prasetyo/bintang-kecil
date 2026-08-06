#!/usr/bin/env python3
"""Scrape GitHub starred repos, detect changes, update README.md + CSV + JSON.

Usage: python3 scrape.py [username]
"""

import csv
import hashlib
import json
import os
import sys
import time
import urllib.request

USERNAME = sys.argv[1] if len(sys.argv) > 1 else "budi-imam-prasetyo"
API = f"https://api.github.com/users/{USERNAME}/starred"
DIR = os.path.dirname(os.path.abspath(__file__))


def fetch_stars():
    page, all_repos = 1, []
    while True:
        req = urllib.request.Request(f"{API}?per_page=100&page={page}")
        req.add_header("User-Agent", "github-stars-scraper/1.0")
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
    bak = os.path.join(DIR, "budi-stars.json.bak")
    new_hash = hashlib.md5(json.dumps(rows).encode()).hexdigest()
    if os.path.exists(bak):
        with open(bak) as f:
            old_hash = hashlib.md5(f.read().encode()).hexdigest()
        if old_hash == new_hash:
            return False
    with open(bak, "w") as f:
        json.dump(rows, f)
    return True


def categorize(r):
    desc = (r["description"] or "").lower()
    topics = set((r.get("topics") or "").lower().split(", "))
    lang = r["language"].lower()
    words = set(desc.split())
    all_k = topics | words | {lang}

    has = lambda s: bool(all_k & s)

    if lang == "kotlin" and has({"android", "kotlin-android", "jetpack-compose", "material-design", "f-droid", "tachiyomi", "manga", "rss-reader", "light-novel"}):
        return "📱 Android Apps"
    if has({"ai-agent", "ai-agents", "coding-agent", "coding-agents", "agent-orchestration", "hermes-agent", "codex", "claude-code", "agent"}):
        return "🤖 AI Agents & Coding Assistants"
    if has({"machine-learning", "deep-learning", "artificial-intelligence", "deep-research", "swarm-intelligence", "token-optimization", "face-swap", "deepfake", "rag", "ai-gateway", "llm"}):
        return "🧠 AI/ML Tools & Research"
    if has({"security", "penetration", "bug-bounty", "vulnerability", "owasp", "static-analysis", "malware"}):
        return "🛡️ Security"
    if has({"awesome", "curated", "learning", "education", "beginners", "resources", "free-for-dev", "app-ideas", "no-signups"}):
        return "📚 Awesome Lists & Learning"
    if has({"design", "ui", "ux", "figma", "css", "tailwind", "components", "canvas", "slide", "icons", "svg", "neobrutalism", "admin-dashboard"}):
        return "🎨 UI/UX & Design Tools"
    if has({"terminal", "cli", "tui", "shell", "zsh", "bash", "neovim", "multiplexer", "text-expander", "typing"}):
        return "💻 Terminal & CLI Tools"
    if has({"video", "player", "downloader", "streaming", "anime", "subtitle", "media"}):
        return "🎬 Media & Downloads"
    if has({"desktop", "electron", "tauri", "wails", "headless"}):
        return "🖥️ Desktop Applications"
    if has({"self-hosted", "privacy", "wireguard", "tailscale", "vpn", "decentralized", "mesh", "whatsapp", "cloud-storage", "captcha", "backup", "snapshot"}):
        return "🔒 Self-Hosted & Privacy"
    if has({"framework", "cms", "backend", "api", "server", "bun", "nodejs", "laravel", "development-environment", "docker"}):
        return "🌐 Web Frameworks & Backend"
    return "🎮 Fun & Misc"


def generate_readme(rows):
    cats = {
        "🤖 AI Agents & Coding Assistants": [],
        "🧠 AI/ML Tools & Research": [],
        "🎨 UI/UX & Design Tools": [],
        "📱 Android Apps": [],
        "💻 Terminal & CLI Tools": [],
        "🖥️ Desktop Applications": [],
        "🎬 Media & Downloads": [],
        "🌐 Web Frameworks & Backend": [],
        "🔒 Self-Hosted & Privacy": [],
        "📚 Awesome Lists & Learning": [],
        "🛡️ Security": [],
        "🛠️ Developer Utilities": [],
        "🎮 Fun & Misc": [],
    }

    for r in rows:
        cat = categorize(r)
        if cat not in cats:
            cats[cat] = []
        cats[cat].append(r)

    # Lang stats
    langs = {}
    for r in rows:
        l = r["language"] or "Unknown"
        langs[l] = langs.get(l, 0) + 1
    langs_sorted = sorted(langs.items(), key=lambda x: -x[1])

    own = [r for r in rows if "budi-imam-prasetyo" in r["repo"]]

    def rr(r):
        desc = (r["description"] or "—")[:80]
        return f'| [{r["repo"]}]({r["url"]}) | {r["stars"]:,} | {r["language"]} | {desc} |'

    L = []
    L.append(f"# ⭐ {USERNAME}'s Starred Repositories\n")
    L.append(f"> {len(rows)} repositories starred on GitHub. Categorized by domain.\n")
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

    if own:
        L.append("## 📁 Own Projects (starred)\n")
        L.append("| Repository | ⭐ | Language | Description |")
        L.append("|---|---:|---|---|")
        for r in own:
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
    L.append(f"| Own repos starred | {len(own)} |")

    with open(os.path.join(DIR, "README.md"), "w") as f:
        f.write("\n".join(L) + "\n")


# --- main ---
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
