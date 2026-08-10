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
    """Evidence-based repo classifier.

    Scores each category independently using weighted signals:
      - Name signals (what the repo IS named):  weight 3
      - Description signals (what it SAYS it does): weight 2
      - Topic signals (how it's TAGGED): weight 1

    The category with the highest score wins, provided it exceeds
    a minimum threshold. This avoids priority-ordering bugs and
    single-keyword false positives.
    """
    desc = (r["description"] or "").lower()
    topics_list = [t.strip().lower() for t in (r.get("topics") or "").split(",") if t.strip()]
    topics = set(topics_list)
    lang = (r["language"] or "").lower()
    words = set(desc.split())
    repo = r["repo"].lower()

    # --- Feature helpers ---
    def has_topics(*args): return bool(topics & set(args))
    def has_all_topics(*args): return set(args).issubset(topics)
    def in_desc(s): return s in desc
    def in_name(s): return s in repo
    def topic_n(*args): return len(topics & set(args))

    # --- Instant returns ---
    if in_name("budi-imam-prasetyo"):
        return "🔧 Own Projects"

    # --- Scoring ---
    scores = {}

    # ---- 🤖 AI Agents & Coding Assistants ----
    # What it IS: a coding agent, agent runtime, agent skills, AI gateway for agents
    s = 0
    # Strong: explicitly a coding agent
    if in_desc("coding agent") or in_desc("agent that"):
        s += 6
    # Strong: agent infrastructure topics (compound required)
    if has_topics("agent-orchestration", "coding-agents"):
        s += 5
    if has_topics("ai-agents") and has_topics("claude-code", "codex", "coding-agents"):
        s += 5
    if has_topics("ai-agent") and has_topics("anthropic", "openai", "claude-code", "codex"):
        s += 5
    # Strong: known agent names
    if in_name("hermes-agent") or in_name("herdr"):
        s += 6
    # Medium: agent skills with coding context
    if has_topics("agent-skills", "ai-skills") and has_topics("claude-code", "codex", "cursor", "cursor-ai", "antigravity"):
        s += 4
    # Medium: AI gateway serving agents (gateway + coding agent keywords)
    if has_topics("ai-gateway", "llm-gateway") and has_topics("claude-code", "codex", "coding-agent", "copilot", "cursor"):
        s += 4
    if in_name("router") and has_topics("ai-agents", "ai-gateway", "claude-code"):
        s += 4
    # Medium: workspace-manager for agents
    if "workspace-manager" in topics and has_topics("ai-agents", "terminal", "multiplexer"):
        s += 4
    # Weak: bare "agent" + AI context (won't win alone)
    if "agent" in topics and has_topics("ai", "mcp"):
        s += 1
    scores["🤖 AI Agents & Coding Assistants"] = s

    # ---- 🧠 AI/ML ----
    # What it IS: an AI/ML application, local LLM client, deep learning tool
    s = 0
    # Strong: deepfake/faceswap (specific AI application)
    if has_topics("deepfake", "faceswap", "ai-deep-fake", "deep-fake"):
        s += 5
    if in_desc("deepfake") or in_desc("face swap"):
        s += 5
    # Strong: local LLM client (offline + LLM/chatgpt)
    if in_desc("alternative to chatgpt") and in_desc("offline"):
        s += 6
    if has_topics("localai", "llamacpp") and in_desc("offline"):
        s += 5
    # Medium: AI app builder
    if has_topics("ai-app-builder") or in_desc("ai app builder"):
        s += 4
    if has_topics("generative-ai") and has_topics("ollama", "llm"):
        s += 3
    # Medium: agentic browser (AI-powered browser)
    if in_desc("agentic browser") or in_desc("agentic browser"):
        s += 4
    if has_topics("ollama", "llm") and in_desc("browser"):
        s += 3
    # Weak: "llm" alone (not enough to win)
    if "llm" in topics and not (in_desc("offline") or in_desc("local")):
        s += 0
    scores["🧠 AI/ML"] = s

    # ---- 📚 Curated Lists & Learning ----
    # What it IS: a curated list, awesome list, educational course
    s = 0
    # Strong: awesome-list topic (unambiguous)
    if has_topics("awesome-list", "awesome-lists"):
        s += 6
    if has_topics("awesome") and not has_topics("awesome-bun"):
        s += 5  # "awesome" alone is strong
    if in_desc("curated list"):
        s += 6
    # Strong: known list patterns
    if in_name("awesome-") or in_name("free-for-dev"):
        s += 6
    if in_name("app-ideas"):
        s += 5
    if in_name("android-foss") and in_desc("list"):
        s += 5
    # Strong: educational course patterns
    if in_desc("weeks") and in_desc("lessons") and in_desc("quizzes"):
        s += 6  # ML-For-Beginners pattern
    if in_name("for-beginners"):
        s += 5
    if has_topics("education") and has_topics("beginners", "quizzes", "lessons"):
        s += 5
    # Medium: "list of" + specific context
    if in_desc("a list of tools"):
        s += 5
    if in_desc("a list of") and in_desc("free and open source"):
        s += 5
    if in_desc("a list of") and has_topics("software", "open-source"):
        s += 4
    if in_desc("a list of") and has_topics("no-signups"):
        s += 5
    if in_desc("no-signups") or in_desc("no signups"):
        s += 4
    if in_desc("a list of") and has_topics("resources", "software", "tools", "applications"):
        s += 3
    if in_desc("collection of") and has_topics("pdf", "books", "templates"):
        s += 3
    # Medium: knowledge/education server
    if in_desc("education server") or in_desc("knowledge and education"):
        s += 4
    scores["📚 Curated Lists & Learning"] = s

    # ---- 🛡️ Security ----
    # What it IS: a security tool, bug bounty resource, pen-testing framework
    s = 0
    # Strong: security framework/analysis
    if has_topics("mobile-security", "android-security", "ios-security", "devsecops"):
        s += 5
    if has_topics("static-analysis", "malware-analysis", "dynamic-analysis"):
        s += 5
    if in_desc("security framework") or in_desc("pen-testing"):
        s += 6
    if has_topics("owasp"):
        s += 4
    # Strong: bug bounty resources
    if has_topics("bug-bounty", "bugbounty", "bugbountybooks", "bugbountypdf"):
        s += 5
    if in_desc("bug bounty") and in_desc("templates"):
        s += 5
    if in_desc("bug bounty") and in_desc("pdf"):
        s += 5
    # Medium: security in description + specific context
    if in_desc("security") and in_desc("book"):
        s += 4
    # Medium: known security names
    if in_name("mobsf") or in_name("bugbounty"):
        s += 5
    # Weak: "security" alone (won't win without other signals)
    if "security" in topics and not has_topics("mobile-security", "android-security", "owasp", "devsecops"):
        s += 1
    scores["🛡️ Security"] = s

    # ---- 🎨 UI/UX & Design ----
    # What it IS: a design system, icon library, canvas/whiteboard, design token tool
    s = 0
    # Strong: design system / tokens / extraction
    if has_topics("design-system", "design-tokens", "design-md"):
        s += 5
    if in_desc("design system") or in_desc("design tokens"):
        s += 5
    # Strong: icon/SVG library
    if has_topics("icon-pack", "svg-icons") and has_topics("icons", "svg"):
        s += 5
    if in_desc("icon") and in_desc("svg"):
        s += 4
    # Strong: canvas/whiteboard SDK
    if has_topics("whiteboard", "canvas", "drawing", "sketch") and has_topics("sdk", "collaboration"):
        s += 5
    if in_name("tldraw"):
        s += 6  # known canvas SDK
    # Medium: diagramming tools
    if has_topics("diagramming", "flowchart", "architecture-diagrams"):
        s += 4
    if in_desc("architecture diagrams") or in_desc("diagramming"):
        s += 4
    # Medium: 3D visual editor
    if in_desc("3d gaussian splat") or in_desc("splat editor"):
        s += 4
    # Medium: UI sound effects
    if in_desc("sound effects") and has_topics("ui", "sfx"):
        s += 4
    # Medium: design tool extraction
    if has_topics("design-engineering", "ui-audit", "design-to-code"):
        s += 4
    # Weak: single design keywords (1pt each, need multiple to win)
    if "design" in topics: s += 1
    if "figma" in topics: s += 1
    if has_topics("css", "tailwind", "tailwindcss") and has_topics("components"):
        s += 1
    # CSS framework itself IS a design tool (nativewind pattern)
    if has_topics("tailwind", "tailwindcss") and has_topics("css") and not has_topics("android"):
        s += 3
    scores["🎨 UI/UX & Design"] = s

    # ---- 📱 Mobile Apps ----
    # What it IS: an end-user Android/iOS application
    s = 0
    # Strong: explicitly an app (description says so)
    if in_desc("android app") or in_desc("for android"):
        s += 5
    if in_desc("manga reader") or in_desc("file manager") or in_desc("music app"):
        s += 5
    if in_desc("ad blocker") or in_desc("block ads"):
        s += 5
    if in_desc("puzzle games"):
        s += 4
    if in_desc("circle to search"):
        s += 5
    # Strong: app-like topics (compound: platform + UI framework)
    if has_topics("jetpack-compose", "material-design") and has_topics("android"):
        s += 4
    if has_topics("file-manager", "filemanager") and has_topics("android"):
        s += 5
    if has_topics("android-app", "android-game", "android-apps"):
        s += 4
    # Strong: known app names
    if in_name("komikku"):
        s += 6  # manga reader
    if in_name("nagram"):
        s += 5  # Telegram client
    # Medium: Kotlin/Java/Dart + android context
    if lang in ("kotlin", "java", "dart") and has_topics("android"):
        s += 2
    # Medium: Dart + flutter + app-like desc
    if lang == "dart" and has_topics("flutter", "android") and in_desc("app"):
        s += 3
    # Medium: Telegram client (Java, desc mentions telegram, not a REST API)
    if lang == "java" and in_desc("telegram") and not has_topics("rest-api", "bot"):
        s += 4
    # Weak: "android" alone (1pt)
    if "android" in topics and lang in ("kotlin", "java", "dart"):
        s += 1
    scores["📱 Mobile Apps"] = s

    # ---- 💻 Terminal & CLI ----
    # What it IS: a terminal tool, TUI, shell enhancement, CLI utility
    s = 0
    # Strong: terminal-specific topics
    if has_topics("terminal-app", "terminal-emulator", "terminal-multiplexer", "terminal-dashboard"):
        s += 5
    if has_topics("tui", "terminal-ui"):
        s += 5
    if has_topics("neovim", "neovim-plugin", "nvim", "plugin-manager"):
        s += 5
    if has_topics("command-line-tool"):
        s += 5
    # Strong: CLI + specific purpose (not just "cli" alone)
    if has_topics("cli") and has_topics("tool", "tools", "filedownloader", "command-line"):
        s += 4
    if in_desc("on the cli") or in_desc("cli tool") or in_desc("terminal tool"):
        s += 5
    if in_desc("terminal-first") or in_desc("terminal-based"):
        s += 4
    if in_desc("terminal workspace"):
        s += 5
    # Strong: shell enhancements (compound: shell + specific plugin type)
    if has_topics("shell", "zsh", "bash", "fish") and has_topics("syntax-highlighting", "autosuggest", "history", "shell-extension", "shell-scripts"):
        s += 4
    if in_desc("shell magical") or in_desc("syntax highlighter"):
        s += 5
    if in_desc("autosuggest"):
        s += 4
    # Medium: text expander
    if has_topics("text-expander"):
        s += 5
    # Medium: known terminal names
    if in_name("tui") or in_name("npkill") or in_name("zsh"):
        s += 5
    if in_name("enhancd"):
        s += 4
    # Weak: bare "terminal" or "cli" (1pt, won't win alone)
    if "terminal" in topics and not has_topics("desktop", "web", "mobile"):
        s += 1
    if "cli" in topics and has_topics("tool", "tools"):
        s += 1
    scores["💻 Terminal & CLI"] = s

    # ---- 🖥️ Desktop Apps ----
    # What it IS: an end-user desktop app, or a desktop app framework
    s = 0
    # Strong: desktop application framework
    if has_topics("desktop-application"):
        s += 5
    if in_desc("desktop app") or in_desc("desktop application"):
        s += 5
    # Strong: electron + desktop context
    if has_topics("electron") and (in_desc("desktop") or in_desc("screen recorder")):
        s += 5
    # Strong: known desktop tools
    if in_name("pake"):
        s += 6  # webpage → desktop
    if in_name("recordly"):
        s += 5  # screen recorder
    if has_topics("electrobun"):
        s += 5
    # Medium: tauri + desktop desc
    if has_topics("tauri") and in_desc("desktop"):
        s += 4
    # Medium: Windows utility
    if lang == "c#" and has_topics("memory", "cleaner", "windows-optimization-tool"):
        s += 5
    # Weak: "desktop" alone (1pt)
    if "desktop" in topics and not has_topics("android", "mobile"):
        s += 1
    scores["🖥️ Desktop Apps"] = s

    # ---- 🎬 Media ----
    # What it IS: media consumption tool, video/audio downloader, streaming tool
    s = 0
    # Strong: video/audio downloader
    if has_topics("downloader", "youtube-downloader", "audio-downloader") and not has_topics("android"):
        s += 5
    if in_desc("download") and in_desc("video") and not has_topics("android"):
        s += 5
    # Strong: streaming client (TUI)
    if has_topics("streaming", "movies-streaming") and has_topics("anime", "moviebox"):
        s += 4
    # Medium: player keywords
    if has_topics("player", "youtube-player") and not has_topics("android"):
        s += 3
    # Medium: screen recorder (but prefer Desktop if electron/desktop context)
    if in_desc("screen recorder") and not has_topics("electron", "desktop"):
        s += 4
    # Weak: "video" alone
    if "video" in topics and has_topics("downloader", "player"):
        s += 1
    scores["🎬 Media"] = s

    # ---- 🔒 Self-Hosted & Privacy ----
    # What it IS: a self-hosted service, VPN, privacy tool, cloud storage gateway
    s = 0
    # Strong: self-hosted (explicit)
    if in_desc("self-hosted") or has_topics("self-hosted"):
        s += 5
    # Strong: VPN infrastructure (compound: vpn/wireguard + server/control)
    if has_topics("wireguard", "tailscale") and has_topics("server", "control-server"):
        s += 6
    # Strong: cloud storage gateway/aggregation
    if has_topics("drive", "gateway") and has_topics("storage"):
        s += 5
    if in_desc("cloud storage") and in_desc("unlimited"):
        s += 5
    if in_desc("multiple google drive") or in_desc("drive aggregation"):
        s += 5
    # Strong: privacy-focused app
    if in_desc("privacy first") or in_desc("privacy-first"):
        s += 4
    if in_desc("gps") and in_desc("privacy"):
        s += 5
    # Medium: known names
    if in_name("headscale"):
        s += 6
    if in_name("9drive"):
        s += 5
    if in_name("omnicloud") and in_desc("drive"):
        s += 5
    # Weak: "storage" alone (0pt — too generic)
    if "storage" in topics and not has_topics("cloud-storage", "drive", "gateway"):
        s += 0
    scores["🔒 Self-Hosted & Privacy"] = s

    # ---- 🌐 Web Frameworks & Backend ----
    # What it IS: a backend framework, JS runtime, CMS, web server
    s = 0
    # Strong: headless CMS
    if has_topics("headless-cms", "cms-framework", "content-management-system"):
        s += 5
    if in_desc("headless cms"):
        s += 6
    # Strong: known frameworks/runtimes
    if in_name("strapi"):
        s += 6
    if in_name("elysia"):
        s += 5
    # Strong: backend (compound: backend + realtime/auth + language)
    if has_topics("backend", "realtime", "authentication") and lang == "go":
        s += 5
    if in_desc("realtime backend"):
        s += 5
    # Strong: JS runtime/toolchain
    if has_topics("bun", "bundler", "transpiler") and in_desc("javascript runtime"):
        s += 5
    # Medium: framework + web context
    if has_topics("framework") and has_topics("http", "server", "web"):
        s += 4
    # Medium: Laravel package
    if has_topics("laravel", "laravel-package") and has_topics("forum", "php"):
        s += 4
    if in_name("laravel"):
        s += 2
    # Medium: Node.js in browser
    if has_topics("webcontainers", "nodejs") and in_desc("browser"):
        s += 3
    # Weak: "api" + "rest" (but NOT if whatsapp/telegram)
    if has_topics("api", "rest") and not has_topics("whatsapp", "telegram"):
        s += 1
    scores["🌐 Web Frameworks & Backend"] = s

    # ---- 🔧 Developer Utilities ----
    # What it IS: dev environment, document converter, monitoring dashboard, productivity tool
    s = 0
    # Strong: development environment
    if in_desc("development environment") or in_desc("local development"):
        s += 5
    if has_topics("development-environment", "docker-alternative", "local-development"):
        s += 5
    # Strong: document converter
    if in_desc("convert") and in_desc("markdown"):
        s += 5
    # Strong: intelligence/OSINT dashboard
    if in_desc("intelligence dashboard") or in_desc("geopolitical monitoring"):
        s += 5
    if has_topics("osint") and has_topics("dashboard", "monitoring"):
        s += 5
    # Medium: developer tools + dashboard
    if has_topics("developer-tools", "devtools") and has_topics("dashboard"):
        s += 4
    # Medium: known names
    if in_name("anydoc"):
        s += 6
    if in_name("flyenv"):
        s += 6
    if in_name("worldmonitor"):
        s += 5
    if in_name("devhub"):
        s += 4
    # Medium: browser extension
    if has_topics("chrome-extension", "firefox-addon", "firefox-extension"):
        s += 4
    # Medium: toolkit
    if in_desc("toolkit") or in_desc("tool kit"):
        s += 3
    # Weak: "developer-tools" alone
    if "developer-tools" in topics and not has_topics("dashboard", "monitoring"):
        s += 1
    scores["🔧 Developer Utilities"] = s

    # ---- 💬 Messaging ----
    # What it IS: a WhatsApp/Telegram bot, API, or messaging client
    s = 0
    # Strong: WhatsApp bot/API (compound: whatsapp + api/bot/rest)
    if has_topics("whatsapp", "whatsapp-api", "golang-whatsapp") and has_topics("bot", "rest-api"):
        s += 6
    if in_desc("whatsapp") and in_desc("rest api"):
        s += 6
    if in_desc("whatsapp") and in_desc("api"):
        s += 4
    # Medium: WhatsApp + bot
    if has_topics("whatsapp") and has_topics("bot"):
        s += 4
    scores["💬 Messaging"] = s

    # ---- Winner selection ----
    THRESHOLD = 3
    viable = {k: v for k, v in scores.items() if v >= THRESHOLD}
    if not viable:
        return "🎮 Fun & Creative"
    return max(viable, key=viable.get)


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
    L.append("# ⭐ My Starred Repositories\n")
    L.append(f"> {len(rows)} repositories starred on GitHub. Categorized by domain.\n")

    # TOC
    def cat_anchor(name):
        # GitHub anchor: lowercase, strip non-alphanum except space/hyphen, space→hyphen, strip leading/trailing hyphens
        import re
        a = name.lower()
        a = re.sub(r'[^a-z0-9 -]', '', a)
        a = a.replace(' ', '-').strip('-')
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
