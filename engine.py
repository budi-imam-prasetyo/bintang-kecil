"""Category engine: declarative rules over normalized repo features.

Replaces the previous 500-line single-function scorer in scrape.py with
data-driven rules so that:
  - each rule declares its category, signal source, and weight;
  - score_details() returns per-category evidence (explainability);
  - zero-signal repos land in Uncategorized instead of Fun & Creative.

Public API:
  classify(row)      -> (category, evidence_list)
  score_details(row) -> {category: (score, [evidence])}
"""

import re

# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

AI = "🤖 AI Agents & Coding Assistants"
ML = "🧠 AI/ML"
DESIGN = "🎨 UI/UX & Design"
MOBILE = "📱 Mobile Apps"
TERMINAL = "💻 Terminal & CLI"
DESKTOP = "🖥️ Desktop Apps"
MEDIA = "🎬 Media"
WEB = "🌐 Web Frameworks & Backend"
SELFHOST = "🔒 Self-Hosted & Privacy"
LISTS = "📚 Curated Lists & Learning"
SECURITY = "🛡️ Security"
DEVUTILS = "🔧 Developer Utilities"
MESSAGING = "💬 Messaging"
OWN = "🔧 Own Projects"
FUN = "🎮 Fun & Creative"

CATEGORIES = [AI, ML, DESIGN, MOBILE, TERMINAL, DESKTOP, MEDIA, WEB,
              SELFHOST, LISTS, SECURITY, DEVUTILS, MESSAGING, OWN, FUN]

FALLBACK_CATEGORY = FUN
UNCATEGORIZED = "❓ Uncategorized"
MIN_SCORE = 3

# Explicit labels for repos whose API signals are absent or misleading.
REPO_OVERRIDES = {
    "sipeed/picoclaw": AI,          # ultra-light personal AI assistant (Go)
    "levy-street/world-of-claudecraft": FUN,  # zero-signal; Minecraft-style demo
}

# ---------------------------------------------------------------------------
# Rule constructors — every rule carries its category
# ---------------------------------------------------------------------------


def T(cat, *pats, w=5):
    """Any topic tag present."""
    return {"cat": cat, "src": "topics", "kind": "any", "pats": set(pats), "w": w}


def T2(cat, topic_pats, desc_pats, w=5):
    """Any topic AND any desc substring (compound)."""
    return {"cat": cat, "src": "td", "kind": "compound",
            "tp": set(topic_pats), "dp": list(desc_pats), "w": w}


def TL(cat, langs, topic_pats, w=5):
    """Language in langs AND any topic tag (compound)."""
    return {"cat": cat, "src": "lang", "kind": "langtopic",
            "langs": set(langs), "tp": set(topic_pats), "w": w}


def TN(cat, pats, min_, w=5):
    """At least `min_` of the topic tags present."""
    return {"cat": cat, "src": "topics", "kind": "n", "pats": set(pats), "min": min_, "w": w}


def D(cat, *pats, w=5):
    """Any substring in description."""
    return {"cat": cat, "src": "desc", "kind": "any", "pats": list(pats), "w": w}


def D2(cat, *pats, w=5):
    """ALL substrings in description."""
    return {"cat": cat, "src": "desc", "kind": "all", "pats": list(pats), "w": w}


def N(cat, *pats, w=5):
    """Any substring in repo name."""
    return {"cat": cat, "src": "name", "kind": "any", "pats": list(pats), "w": w}


# ---------------------------------------------------------------------------
# Rules — ported from the legacy scorer, deduplicated, plus audit fixes
# (sonora music-player, whatRust whatsapp-client, next-ai-draw-io, etc.)
# ---------------------------------------------------------------------------

RULES = [
    # ---- AI Agents & Coding Assistants ----
    D(AI, "coding agent", "agent that", w=6),
    # AI skills that enhance coding agents (ui-ux-pro-max-skill pattern)
    T2(AI, ["ai-skills", "agent-skills"], ["design", "coding", "professional"], w=5),
    T(AI, "agent-orchestration", "coding-agents", w=5),
    T2(AI, ["ai-agents"], ["claude", "codex", "openai"], w=5),
    T2(AI, ["ai-agent"], ["anthropic", "openai", "claude", "codex"], w=5),
    N(AI, "hermes-agent", "herdr", "claw", "-agent", "agent-", w=5),
    T2(AI, ["agent-memory"], ["mcp", "llm", "ai"], w=5),
    D(AI, "ai agent", "coding workflow", "autonomous task", w=4),
    T2(AI, ["mcp", "mcp-server"], ["agent", "llm", "ai", "rag"], w=4),
    T2(AI, ["agent-skills", "ai-skills"], ["claude-code", "codex", "cursor", "antigravity"], w=4),
    T2(AI, ["ai-gateway", "llm-gateway"], ["claude-code", "codex", "copilot", "cursor"], w=4),
    T2(AI, ["workspace-manager"], ["multiplexer", "terminal"], w=4),

    # ---- AI/ML ----
    T(ML, "deepfake", "faceswap", "ai-deep-fake", "deep-fake", w=5),
    D(ML, "deepfake", "face swap", w=5),
    D2(ML, "alternative to chatgpt", "offline", w=6),
    T2(ML, ["localai", "llamacpp"], ["offline"], w=5),
    T(ML, "ai-app-builder", w=4),
    D(ML, "ai app builder", "agentic browser", w=4),
    T2(ML, ["generative-ai"], ["ollama", "llm"], w=3),
    T2(ML, ["ollama", "llm"], ["browser"], w=3),

    # ---- UI/UX & Design ----
    T(DESIGN, "design-system", "design-tokens", "design-md", w=5),
    D(DESIGN, "design system", "design tokens", w=5),
    # "awesome-X" where X is a design domain stays a curated list, not design tool
    # (guarded by LISTS' higher score when the repo IS a list; see awesome-design-md)
    T(LISTS, "awesome-design-md", w=6),
    T2(DESIGN, ["icon-pack", "svg-icons"], ["icons", "svg"], w=5),
    D2(DESIGN, "icon", "svg", w=4),
    T2(DESIGN, ["whiteboard", "canvas", "drawing", "sketch"], ["sdk", "collaboration"], w=5),
    N(DESIGN, "tldraw", w=6),
    T(DESIGN, "diagramming", "flowchart", "architecture-diagrams", w=4),
    D(DESIGN, "architecture diagrams", "diagramming", "3d gaussian splat",
       "splat editor", w=4),
    T2(DESIGN, ["ui", "sfx"], ["sound effects"], w=4),
    T(DESIGN, "design-engineering", "ui-audit", "design-to-code", w=4),
    T(DESIGN, "design", "figma", w=1),
    T2(DESIGN, ["css", "tailwind", "tailwindcss"], ["components"], w=1),
    T2(DESIGN, ["tailwind", "tailwindcss", "css"], ["utility-first"], w=3),

    # ---- Mobile Apps ----
    D(MOBILE, "android app", "for android", "manga reader", "file manager",
      "music app", "ad blocker", "block ads", "circle to search", w=5),
    # "A list of ... for Android" is a curated list, not an app (android-foss guard)
    D2(LISTS, "a list of", "for android", w=6),
    D(MOBILE, "puzzle games", w=4),
    T2(MOBILE, ["jetpack-compose", "material-design"], ["android"], w=4),
    T2(MOBILE, ["file-manager", "filemanager"], ["android"], w=5),
    T(MOBILE, "android-app", "android-game", "android-apps", w=4),
    # "android" topic + app-shaped language is a mobile app even without
    # strong description (FilePipe pattern)
    TL(MOBILE, [""], ["android"], w=2),
    T2(MOBILE, ["android"], ["storage", "library", "rule"], w=3),
    N(MOBILE, "komikku", "nagram", w=6),
    TL(MOBILE, ["kotlin", "java", "dart"], ["android"], w=2),
    T2(MOBILE, ["flutter"], ["app"], w=3),

    # ---- Terminal & CLI ----
    T(TERMINAL, "terminal-app", "terminal-emulator", "terminal-multiplexer",
      "terminal-dashboard", "tui", "terminal-ui", "neovim", "neovim-plugin",
      "nvim", "plugin-manager", "command-line-tool", "text-expander", w=5),
    T(TERMINAL, "cli", "command-line", w=4),
    T2(TERMINAL, ["cli"], ["tool", "command-line"], w=4),
    D(TERMINAL, "on the cli", "cli tool", "terminal tool", "terminal workspace", w=5),
    D(TERMINAL, "terminal-first", "terminal-based", "autosuggest", w=4),
    D(TERMINAL, "top/htop", "htop alternative", "alternative to top", w=6),
    T2(TERMINAL, ["system-monitor"], ["terminal", "monitoring"], w=5),
    T2(TERMINAL, ["shell", "zsh", "bash", "fish"],
       ["syntax-highlighting", "autosuggest", "history", "shell-extension"], w=4),
    D(TERMINAL, "shell magical", "syntax highlighter", w=5),
    N(TERMINAL, "tui", "npkill", "zsh", "enhancd", w=4),
    T(TERMINAL, "terminal", w=1),
    T2(TERMINAL, ["cli"], ["tool", "tools"], w=1),

    # ---- Desktop Apps ----
    T(DESKTOP, "desktop-application", "electrobun", "desktop-app", w=5),
    T(DESKTOP, "desktop", "gui", w=4),
    D(DESKTOP, "desktop app", "desktop application", w=5),
    T2(DESKTOP, ["electron"], ["desktop", "screen recorder"], w=5),
    N(DESKTOP, "pake", "recordly", w=5),
    TN(DESKTOP, ["cleaner", "system-cleaner", "linux-cleaner", "mac-cleaner",
                 "windows-cleaner", "system-maintenance", "pc-optimization",
                 "windows-optimization-tool"], 2, w=6),
    T2(DESKTOP, ["tauri"], ["desktop"], w=4),
    TL(DESKTOP, ["c#"], ["memory", "cleaner", "ram"], w=5),

    # ---- Media (audit fixes: players + streaming are media) ----
    T(MEDIA, "music-player", "youtube-player", "video-player",
      "youtube-downloader", "audio-downloader", "downloader", w=5),
    T(MEDIA, "streaming", "spotify", "iptv", w=4),
    # Media purpose beats terminal interface: mpv/anime/series context
    T2(MEDIA, ["mpv", "anime", "series", "tv-shows", "moviebox"], ["terminal", "tui", "cli"], w=6),
    T2(MEDIA, ["movies", "tv-shows", "series", "iptv"], ["streaming", "downloader"], w=5),
    D2(MEDIA, "download", "video", w=5),
    T2(MEDIA, ["player"], ["music", "streaming"], w=3),
    T2(MEDIA, ["player", "youtube-player"], ["music", "streaming"], w=3),

    # ---- Self-Hosted & Privacy ----
    T(SELFHOST, "self-hosted", w=5),
    D(SELFHOST, "self-hosted", w=5),
    T2(SELFHOST, ["wireguard", "tailscale"], ["server", "control-server"], w=6),
    T2(SELFHOST, ["drive", "gateway"], ["storage"], w=5),
    D2(SELFHOST, "cloud storage", "drive", w=6),
    D2(SELFHOST, "cloud storage", "unlimited", w=5),
    D(SELFHOST, "multiple google drive", "drive aggregation", w=5),
    D(SELFHOST, "privacy first", "privacy-first", w=4),
    D2(SELFHOST, "gps", "privacy", w=5),
    N(SELFHOST, "headscale", "9drive", "omnicloud", w=5),

    # ---- Curated Lists & Learning ----
    T(LISTS, "awesome-list", "awesome-lists", w=6),
    T(LISTS, "awesome", "awesome-go", "awesome-python", "awesome-design-md", w=5),
    # name "awesome-" prefix: it IS a list, even if the domain is design
    N(LISTS, "awesome-", w=7),
    D(LISTS, "curated list", "list of awesome", w=6),
    N(LISTS, "awesome-", "free-for-dev", "app-ideas", "for-beginners", w=5),
    T2(LISTS, ["android-foss"], ["list"], w=5),
    D2(LISTS, "weeks", "lessons", w=6),
    T2(LISTS, ["education"], ["beginners", "quizzes", "lessons"], w=5),
    D(LISTS, "a list of", "no-signups", "no signups", w=4),
    T2(LISTS, ["resources", "software", "tools", "applications"], ["a list of"], w=3),
    T2(LISTS, ["pdf", "books", "templates"], ["collection of"], w=3),
    D(LISTS, "education server", "knowledge and education", w=4),

    # ---- Security ----
    T(SECURITY, "mobile-security", "android-security", "ios-security", "devsecops",
      "static-analysis", "malware-analysis", "dynamic-analysis",
      "penetration-testing", "offensive-security", "red-teaming", w=5),
    D(SECURITY, "security framework", "pen-testing", "reverse engineering",
      "penetration testing", w=6),
    T(SECURITY, "owasp", "bug-bounty", "bugbounty", "bugbountybooks",
      "bugbountypdf", w=4),
    D2(SECURITY, "bug bounty", "templates", w=5),
    D2(SECURITY, "bug bounty", "pdf", w=5),
    D2(SECURITY, "security", "book", w=4),
    N(SECURITY, "mobsf", "bugbounty", w=5),
    T(SECURITY, "security", w=1),

    # ---- Developer Utilities ----
    D(DEVUTILS, "development environment", "local development", w=5),
    T(DEVUTILS, "development-environment", "docker-alternative", "local-development", w=5),
    D2(DEVUTILS, "convert", "markdown", w=5),
    TN(DEVUTILS, ["web-scraping", "web-scraper", "scraping", "crawler", "crawling",
                  "data-extraction", "webscraping"], 3, w=6),
    D(DEVUTILS, "intelligence dashboard", "geopolitical monitoring", w=5),
    T2(DEVUTILS, ["osint"], ["dashboard", "monitoring"], w=5),
    T2(DEVUTILS, ["developer-tools", "devtools"], ["dashboard"], w=4),
    N(DEVUTILS, "anydoc", "flyenv", "worldmonitor", "devhub", w=4),
    T(DEVUTILS, "chrome-extension", "firefox-addon", "firefox-extension", w=4),
    D(DEVUTILS, "toolkit", "tool kit", w=3),
    T(DEVUTILS, "developer-tools", w=1),

    # ---- Web Frameworks & Backend ----
    T(WEB, "headless-cms", "cms-framework", "content-management-system", w=5),
    D(WEB, "headless cms", w=6),
    N(WEB, "strapi", "elysia", w=5),
    T2(WEB, ["laravel", "laravel-package"], ["forum", "package", "php"], w=4),
    D(WEB, "laravel", w=2),
    # Laravel ecosystem tooling (laramint/laravel-brain pattern)
    T2(WEB, ["laravel", "laravel-packages", "laravel-package"], ["laravel", "request", "lifecycle", "graph"], w=5),
    T2(WEB, ["framework"], ["http", "server", "web"], w=4),
    T2(WEB, ["backend", "realtime", "authentication"], ["realtime backend", "backend in"], w=5),
    D(WEB, "realtime backend", w=5),
    T2(WEB, ["bun", "bundler", "transpiler"], ["javascript runtime", "runtime"], w=5),
    T2(WEB, ["webcontainers", "nodejs"], ["browser"], w=3),
    T2(WEB, ["api", "rest"], ["not-whatsapp-guard"], w=1),

    # ---- Messaging (audit fixes: whatsapp/telegram clients) ----
    T2(MESSAGING, ["whatsapp", "whatsapp-api", "golang-whatsapp"], ["bot", "rest-api"], w=6),
    D2(MESSAGING, "whatsapp", "rest api", w=6),
    D2(MESSAGING, "whatsapp", "api", w=4),
    T2(MESSAGING, ["whatsapp"], ["bot"], w=4),
    # Client apps for a messaging platform are Messaging, even if desktop
    # (whatRust pattern: purpose beats interface)
    T(MESSAGING, "whatsapp-client", "whatsapp-desktop", "whatsapp-web",
      "telegram-client", "whatsapp-bot", w=7),
    D2(MESSAGING, "whatsapp", "client", w=6),
    D2(MESSAGING, "telegram", "client", w=6),
]

# ---------------------------------------------------------------------------
# Feature extraction + matching
# ---------------------------------------------------------------------------


def _features(row):
    return {
        "repo": row["repo"].lower(),
        "desc": (row.get("description") or "").lower(),
        "topics": {t.strip().lower() for t in (row.get("topics") or "").split(",") if t.strip()},
        "lang": (row.get("language") or "").lower(),
    }


def _fires(rule, f):
    src = rule["src"]
    if src == "topics":
        hit = f["topics"] & rule["pats"]
        if rule["kind"] == "any":
            return bool(hit)
        return len(hit) >= rule["min"]  # kind == "n"
    if src == "desc":
        if rule["kind"] == "any":
            return any(p in f["desc"] for p in rule["pats"])
        return all(p in f["desc"] for p in rule["pats"])
    if src == "name":
        return any(p in f["repo"] for p in rule["pats"])
    if src == "td":
        return bool(f["topics"] & rule["tp"]) and any(p in f["desc"] for p in rule["dp"])
    if src == "lang":
        return f["lang"] in rule["langs"] and bool(f["topics"] & rule["tp"])
    raise ValueError(f"unknown rule source: {src}")


def _evidence(rule):
    src = rule["src"]
    if src == "td":
        return f"topic~{sorted(rule['tp'])[:3]}+desc~{rule['dp'][:2]}"
    if src == "lang":
        return f"lang{sorted(rule['langs'])}+topic~{sorted(rule['tp'])}"
    p = sorted(rule.get("pats", []))[:3]
    if rule.get("kind") == "n":
        return f"{rule['min']}+ of topic~{p}"
    return f"{src}~{p}"


def score_details(row):
    """Return {category: (score, [evidence,...])} for every category > 0."""
    f = _features(row)
    out = {}
    for rule in RULES:
        if _fires(rule, f):
            cat = rule["cat"]
            score, ev = out.get(cat, (0, []))
            out[cat] = (score + rule["w"], ev + [_evidence(rule)])
    return out


def classify(row):
    """Return (category, evidence_list) for a repo row."""
    if row["repo"].startswith("budi-imam-prasetyo/"):
        return OWN, ["own repo"]
    if row["repo"] in REPO_OVERRIDES:
        return REPO_OVERRIDES[row["repo"]], ["override"]

    scores = score_details(row)
    viable = {c: v for c, v in scores.items() if v[0] >= MIN_SCORE}
    if not viable:
        if (row.get("description") or "").strip() or (row.get("topics") or "").strip():
            return FALLBACK_CATEGORY, ["weak signals, below threshold"]
        return UNCATEGORIZED, ["no signals"]
    best = max(viable, key=lambda c: viable[c][0])
    return best, viable[best][1]
