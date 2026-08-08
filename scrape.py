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
    lang = (r["language"] or "").lower()
    words = set(desc.split())
    all_k = topics | words | {lang}
    repo = r["repo"].lower()

    has = lambda s: bool(all_k & s)
    desc_has = lambda s: s in desc
    name_has = lambda s: s in repo

    # --- 1. Own repos ---
    if name_has("budi-imam-prasetyo"):
        return "🔧 Own Projects"

    # --- Name overrides BEFORE keyword checks (mis-tagged repos) ---
    if name_has("flyenv"):
        return "🔧 Developer Utilities"
    if name_has("horizon"):
        return "💻 Terminal & CLI"
    # komikku-preview: companion repo to komikku manga reader
    if name_has("komikku"):
        return "📱 Mobile Apps"

    # --- 2. AI Agents & Coding Assistants ---
    # Compound keywords only (no bare "agent" to avoid false positives)
    agent_kw = {"ai-agent", "ai-agents", "coding-agent", "coding-agents",
                "agent-orchestration", "hermes-agent", "claude-code",
                "workspace-manager"}
    if has(agent_kw):
        return "🤖 AI Agents & Coding Assistants"
    # agent-skills: only if also coding-related (not mis-tagged icon/design repos)
    if "agent-skills" in topics and has({"claude", "claude-code", "codex", "cursor"}):
        return "🤖 AI Agents & Coding Assistants"
    # AI gateways / routers (serve coding agents)
    if has({"ai-gateway", "llm-gateway", "token-saver"}) and has({"claude", "gpt", "openai", "llm"}):
        return "🤖 AI Agents & Coding Assistants"
    if name_has("router") and has({"ai", "llm", "claude", "codex"}):
        return "🤖 AI Agents & Coding Assistants"
    # Coding agent by description
    if desc_has("coding agent") or desc_has("open source coding agent"):
        return "🤖 AI Agents & Coding Assistants"
    # Agent runtimes by name (not by bare keyword)
    if name_has("herdr"):
        return "🤖 AI Agents & Coding Assistants"

    # --- 3. Curated Lists & Learning (before AI/ML: education trumps topic tags) ---
    if has({"education", "beginners", "quizzes", "lessons"}) or name_has("for-beginners"):
        return "📚 Curated Lists & Learning"

    # --- 4. AI/ML ---
    if has({"machine-learning", "deep-learning", "artificial-intelligence",
            "deepfake", "faceswap", "localai", "llamacpp", "ollama",
            "ai-app-builder", "generative-ai"}):
        return "🧠 AI/ML"
    if has({"llm", "chatgpt", "gpt"}) and has({"offline", "local"}):
        return "🧠 AI/ML"

    # --- 5. Security ---
    if has({"security", "penetration", "bug-bounty", "vulnerability", "owasp",
            "static-analysis", "malware", "mobile-security", "devsecops",
            "hacking", "bugbounty", "hackingbooks"}):
        return "🛡️ Security"
    if name_has("mobsf") or name_has("bugbounty") or name_has("security"):
        return "🛡️ Security"

    # --- 5. Curated Lists & Learning ---
    # Match substrings: "awesome-list" starts with "awesome", etc.
    if any(t.startswith("awesome") for t in topics) or has({"curated", "no-signups"}):
        return "📚 Curated Lists & Learning"
    if desc_has("no-signups") or desc_has("no signups"):
        return "📚 Curated Lists & Learning"
    if name_has("awesome-") or name_has("free-for-dev") or name_has("app-ideas") or name_has("android-foss"):
        return "📚 Curated Lists & Learning"
    if has({"education", "beginners", "quizzes", "lessons"}) or name_has("for-beginners"):
        return "📚 Curated Lists & Learning"
    # Curated lists with "list" in topics + educational context
    if "list" in topics and has({"resources", "software", "tools"}):
        return "📚 Curated Lists & Learning"

    # --- 6. UI/UX & Design ---
    design_kw = {"design", "ui", "figma", "css", "tailwind", "tailwindcss",
                 "components", "icons", "svg", "design-system", "design-tokens",
                 "design-md", "whiteboard", "sketch", "drawing", "canvas",
                 "diagram", "diagramming", "design-tool", "gaussian-splatting"}
    if has(design_kw):
        return "🎨 UI/UX & Design"
    if name_has("design") or name_has("svg") or name_has("ui-ux"):
        return "🎨 UI/UX & Design"
    # tldraw: canvas SDK, not AI agent
    if name_has("tldraw"):
        return "🎨 UI/UX & Design"

    # --- 7. Mobile Apps (any language) ---
    mobile_kw = {"android", "kotlin-android", "jetpack-compose", "material-design",
                 "f-droid", "tachiyomi", "manga", "mangareader", "android-apps",
                 "android-app", "android-game", "react-native", "flutter",
                 "file-manager", "filemanager"}
    if has(mobile_kw):
        return "📱 Mobile Apps"
    # Name-based: repos with "android" in name + mobile language
    if name_has("android") and lang in ("kotlin", "java", "dart"):
        return "📱 Mobile Apps"
    # NagramX: Telegram client (Java), Puzzle (Dart+flutter+android)
    if lang == "java" and desc_has("telegram"):
        return "📱 Mobile Apps"
    if lang == "java" and name_has("nagram"):
        return "📱 Mobile Apps"
    if lang == "dart" and has({"android", "flutter", "ios"}):
        return "📱 Mobile Apps"

    # --- 8. Terminal & CLI ---
    terminal_kw = {"terminal", "cli", "tui", "shell", "zsh", "bash", "neovim",
                   "nvim", "multiplexer", "text-expander", "typing",
                   "command-line", "console", "ratatui", "syntax-highlighting",
                   "autosuggest", "tmux", "terminal-app", "terminal-game"}
    if has(terminal_kw):
        return "💻 Terminal & CLI"
    if name_has("tui") or name_has("cli") or name_has("zsh") or name_has("npkill"):
        return "💻 Terminal & CLI"

    # --- 9. Desktop Apps ---
    # Removed "headless" (false positive for "headless CMS")
    desktop_kw = {"desktop", "desktop-application", "electron", "tauri", "wails",
                  "electrobun"}
    if has(desktop_kw):
        return "🖥️ Desktop Apps"
    if name_has("pake") or name_has("recordly") or name_has("desktop"):
        return "🖥️ Desktop Apps"
    # WinMemoryCleaner: Windows desktop utility
    if lang == "c#" and has({"windows", "memory", "cleaner"}):
        return "🖥️ Desktop Apps"

    # --- 10. Media ---
    media_kw = {"video", "player", "downloader", "streaming", "anime", "subtitle",
                "media", "screen-recorder", "movie", "music", "youtube-downloader",
                "youtube-player", "audio-downloader"}
    if has(media_kw):
        return "🎬 Media"

    # --- 11. Self-Hosted & Privacy ---
    selfhost_kw = {"self-hosted", "privacy", "wireguard", "tailscale", "vpn",
                   "decentralized", "mesh", "cloud-storage", "backup", "snapshot",
                   "local-first", "storage", "gateway", "drive", "gps-tracking"}
    if has(selfhost_kw):
        return "🔒 Self-Hosted & Privacy"

    # --- 12. Web Frameworks & Backend ---
    web_kw = {"framework", "cms", "backend", "api", "server", "bun", "nodejs",
              "laravel", "realtime", "http", "rest", "rest-api", "webcontainers",
              "headless-cms"}
    if has(web_kw):
        return "🌐 Web Frameworks & Backend"
    # Strapi: "headless CMS" → web framework
    if name_has("strapi"):
        return "🌐 Web Frameworks & Backend"

    # --- 13. Developer Utilities ---
    devutil_kw = {"developer-tools", "devtools", "productivity", "toolkit",
                  "converter", "document", "development-environment",
                  "local-development", "docker-alternative", "monitoring",
                  "dashboard", "osint"}
    if has(devutil_kw):
        return "🔧 Developer Utilities"
    if name_has("anydoc") or name_has("flyenv") or name_has("devhub"):
        return "🔧 Developer Utilities"
    # worldmonitor: intelligence dashboard (not an agent)
    if name_has("worldmonitor"):
        return "🔧 Developer Utilities"

    # --- 14. Messaging ---
    if has({"whatsapp", "telegram"}) and not has({"ai-agent", "cloud-storage"}):
        return "💬 Messaging"

    # --- Catch-all ---
    return "🎮 Fun & Creative"


def generate_readme(rows):
    cats = {
        "🤖 AI Agents & Coding Assistants": [],
        "🧠 AI/ML": [],
        "🎨 UI/UX & Design": [],
        "📱 Mobile Apps": [],
        "💻 Terminal & CLI": [],
        "🖥️ Desktop Apps": [],
        "🎬 Media": [],
        "🌐 Web Frameworks & Backend": [],
        "🔒 Self-Hosted & Privacy": [],
        "📚 Curated Lists & Learning": [],
        "🛡️ Security": [],
        "🔧 Developer Utilities": [],
        "💬 Messaging": [],
        "🔧 Own Projects": [],
        "🎮 Fun & Creative": [],
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
