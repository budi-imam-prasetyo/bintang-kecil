"""engine v2.0.0 — deterministic repository taxonomy engine.

Classify what a repository IS primarily FOR, not merely what technologies
it uses.  Purpose > domain > application type > interface > technology.

Architecture (v2 overhaul):
  * semantic lexicon, not scattered keywords
  * explicit category definitions + conflict rules
  * signals typed by layer: PURPOSE / APP_TYPE / DOMAIN / INTERFACE / TECH
  * boundary-safe token & phrase matching (no raw substring for short words)
  * positive + negative evidence
  * confidence + margin (deterministic), ambiguity reported, not hidden
  * audit mode:  python3 engine.py --audit budi-stars.json
  * fallback = ❓ Uncategorized when evidence is absent
    (Fun & Creative requires actual fun/creative evidence)

Public API (unchanged contract, richer internals):
  classify(row)      -> (category, evidence_list)
  score_details(row) -> {category: (score, [evidence])}
  audit(rows)        -> list of audit dicts (see --audit)
"""

__version__ = "2.1.0"

import json
import re
import sys
import unicodedata

# ---------------------------------------------------------------------------
# Categories + taxonomy tree
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

UNCATEGORIZED = "❓ Uncategorized"

# Minimum accumulated score for a category to count as a candidate.
MIN_SCORE = 3
# Single-candidate score at or below this is treated as too weak to commit.
WEAK_SINGLE_SCORE = 4

# Display + README order.  UNCATEGORIZED is appended by scrape.py.
CATEGORIES = [AI, ML, DESIGN, MOBILE, TERMINAL, DESKTOP, MEDIA, WEB,
              SELFHOST, LISTS, SECURITY, DEVUTILS, MESSAGING, OWN, FUN]

# Conceptual taxonomy (documentation + conflict reasoning).
TAXONOMY = {
    "AI": {"children": [AI, ML]},
    "Applications": {"children": [MOBILE, DESKTOP, MEDIA, MESSAGING]},
    "Developer / Computing": {"children": [TERMINAL, DEVUTILS, WEB, SECURITY]},
    "Design": {"children": [DESIGN]},
    "Infrastructure": {"children": [SELFHOST]},
    "Knowledge": {"children": [LISTS]},
    "Personal": {"children": [OWN]},
    "Other": {"children": [FUN, UNCATEGORIZED]},
}

# Precedence for tie / interface-vs-purpose conflicts (lower index wins).
# Purpose-first: interface & technology categories yield to purpose categories.
_PURPOSE_CATS = {AI, ML, MEDIA, MESSAGING, SECURITY, SELFHOST, LISTS, WEB,
                 DESIGN, MOBILE, FUN}
# Application-type categories that win only when no stronger purpose exists.
_APPTYPE_CATS = {DESKTOP}
# Interface categories: never win over a real purpose.
_INTERFACE_CATS = {TERMINAL}
# Dev utilities: purpose is "building/dev tooling" — yields to end-user purpose.
_DEVUTIL_CATS = {DEVUTILS}

# ---------------------------------------------------------------------------
# Category definitions (audit / documentation / conflict resolution)
# ---------------------------------------------------------------------------

CATEGORY_DEFS = {
    AI: dict(
        definition="Repositories whose primary purpose is AI agents, coding "
                   "assistants, agent infrastructure (memory/gateways/skills), "
                   "or tooling whose purpose is building/running coding agents.",
        include_when=["coding agent", "agent runtime/infra", "agent skills",
                      "AI gateway for coding agents"],
        exclude_when=["generic LLM app without agent framing", "pure ML models"],
        conflicts_with=[TERMINAL, DEVUTILS, WEB, ML],
        strong_signals=["coding-agents", "claude-code", "ai-agent", "agent-memory"],
        examples=["NousResearch/hermes-agent", "anomalyco/opencode"],
    ),
    ML: dict(
        definition="Repositories whose primary purpose is AI/ML applications, "
                   "models, local LLM clients, AI generators or ML tooling "
                   "(excluding coding-agent-focused projects).",
        include_when=["local LLM app", "AI content generator", "deepfake",
                      "ML training/inference tooling"],
        exclude_when=["coding agents (see AI Agents)"],
        conflicts_with=[AI, DEVUTILS],
        strong_signals=["deepfake", "faceswap", "localai", "llamacpp",
                        "machine-learning", "generative-ai"],
        examples=["janhq/jan", "hacksider/Deep-Live-Cam"],
    ),
    DESIGN: dict(
        definition="Repositories whose primary purpose is visual/UI design: "
                   "design systems, tokens, icon libraries, canvas/whiteboard "
                   "SDKs, UI component libraries, diagramming, design tooling.",
        include_when=["design system", "icon pack", "UI component library",
                      "Figma plugin", "canvas SDK"],
        exclude_when=["curated lists of design resources (see Lists)",
                      "websites that merely use Tailwind"],
        conflicts_with=[LISTS, WEB, DEVUTILS],
        strong_signals=["design-system", "design-tokens", "icon-pack",
                        "svg-icons", "tldraw", "tailwindcss+components"],
        examples=["tldraw/tldraw", "glincker/thesvg"],
    ),
    MOBILE: dict(
        definition="End-user applications distributed/run on mobile platforms "
                   "(Android/iOS), regardless of UI framework.",
        include_when=["'for Android' app", "manga reader app", "mobile music app",
                      "flutter/kotlin app with mobile framing"],
        exclude_when=["lists OF mobile apps", "cross-platform desktop apps"],
        conflicts_with=[LISTS, MEDIA, DEVUTILS],
        strong_signals=["android-app", "for android", "jetpack-compose+android"],
        examples=["komikku-app/komikku", "parallelcc/MiCTS"],
    ),
    TERMINAL: dict(
        definition="Tools whose primary purpose is terminal/CLI work: terminal "
                   "emulators/multiplexers, TUI apps, shell enhancements, CLI "
                   "utilities.  Yields to purpose when a repo IS a messaging/"
                   "media/security tool that merely ships a CLI.",
        include_when=["terminal multiplexer", "TUI app", "zsh plugin",
                      "CLI developer utility"],
        exclude_when=["CLI is only an interface for another purpose "
                      "(messaging client, media player, security scanner)"],
        conflicts_with=[MESSAGING, MEDIA, SECURITY, AI],
        strong_signals=["terminal-multiplexer", "terminal-ui", "neovim",
                        "command-line-tool", "tui"],
        examples=["zellij-org/zellij", "atuinsh/atuin", "chmln/sd"],
    ),
    DESKTOP: dict(
        definition="End-user desktop applications (electron/tauri/native GUI). "
                   "App-type category: yields to purpose (e.g. a WhatsApp "
                   "desktop client is Messaging, not Desktop).",
        include_when=["desktop GUI app", "electron app", "tauri app",
                      "system cleaner"],
        exclude_when=["messaging/media clients whose purpose is elsewhere"],
        conflicts_with=[MESSAGING, MEDIA, AI, DEVUTILS],
        strong_signals=["desktop-app", "electron+desktop", "tauri+desktop"],
        examples=["tw93/Pake", "AdventDevInc/kudu"],
    ),
    MEDIA: dict(
        definition="Repositories whose primary purpose is consuming, playing, "
                   "downloading, streaming, or managing audio/video/media.",
        include_when=["music player", "streaming client", "video downloader",
                      "anime/movie client"],
        exclude_when=["generic download libraries", "media processing "
                      "libraries whose purpose is developer tooling"],
        conflicts_with=[TERMINAL, DESKTOP, MOBILE, DEVUTILS],
        strong_signals=["music-player", "youtube-downloader", "streaming",
                        "mpv", "youtube-player"],
        examples=["nolight132/sonora", "mesamirh/MovieBox-Tui"],
    ),
    WEB: dict(
        definition="Web frameworks, backend runtimes/servers, CMS, API "
                   "frameworks, and web development tooling whose purpose is "
                   "building/running web backends.",
        include_when=["JS runtime", "headless CMS", "realtime backend",
                      "Laravel ecosystem", "web framework"],
        exclude_when=["end-user web apps with a different purpose",
                      "static site generators aimed at docs (Dev Utils)"],
        conflicts_with=[DEVUTILS, DESIGN],
        strong_signals=["headless-cms", "realtime backend", "javascript runtime",
                        "laravel", "framework+http/server"],
        examples=["oven-sh/bun", "pocketbase/pocketbase"],
    ),
    SELFHOST: dict(
        definition="Self-hostable services, VPN/network control servers, cloud "
                   "storage gateways, and privacy-first infrastructure.",
        include_when=["self-hosted server", "Tailscale/WireGuard control",
                      "private cloud storage", "privacy tool"],
        exclude_when=["public SaaS client apps", "generic storage libraries"],
        conflicts_with=[DESKTOP, DEVUTILS, WEB],
        strong_signals=["self-hosted", "wireguard+server", "tailscale+server",
                        "cloud storage drive"],
        examples=["juanfont/headscale", "caamer20/Telegram-Drive"],
    ),
    LISTS: dict(
        definition="Content repositories: curated lists (awesome-*), resource "
                   "collections, educational courses, link lists.  Treated by "
                   "content type FIRST — the listed domain never re-categorizes "
                   "the list itself.",
        include_when=["awesome-*", "free-for-dev", "app-ideas", "ML-for-"
                      "Beginners course", "FOSS list"],
        exclude_when=["the repo IS the app/tool, not a list of others"],
        conflicts_with=[MOBILE, SECURITY, DESIGN, AI, WEB, DEVUTILS, MEDIA],
        strong_signals=["awesome-", "curated list", "a list of",
                        "free-for-dev", "app-ideas"],
        examples=["avelino/awesome-go", "offa/android-foss",
                  "VoltAgent/awesome-design-md"],
    ),
    SECURITY: dict(
        definition="Repositories whose purpose is offensive/defensive security: "
                   "pen-testing frameworks, scanners, RE, malware analysis, "
                   "bug-bounty resources.",
        include_when=["pentest framework", "vuln scanner", "RE tool",
                      "bug bounty list", "EDR/siem tooling"],
        exclude_when=["a generic CLI that happens to be usable for security",
                      "OSINT dashboards (Dev Utils)"],
        conflicts_with=[TERMINAL, DEVUTILS, AI],
        strong_signals=["penetration-testing", "offensive-security",
                        "mobile-security", "malware-analysis",
                        "reverse-engineering", "bug-bounty", "nmap"],
        examples=["MobSF/Mobile-Security-Framework-MobSF", "Zyrexnn/Cybermes"],
    ),
    DEVUTILS: dict(
        definition="Developer productivity tooling: dev environments, "
                   "converters, scraping frameworks, dashboards, browser "
                   "extensions for devs, local servers.  Purpose is helping "
                   "developers build — not end-user media/messaging.",
        include_when=["dev environment", "doc converter", "web scraping "
                      "framework", "OSINT dashboard", "browser extension"],
        exclude_when=["end-user apps (desktop/media/messaging)",
                      "coding agents (see AI)"],
        conflicts_with=[AI, WEB, MEDIA, TERMINAL, DESKTOP],
        strong_signals=["development-environment", "convert+markdown",
                        "web-scraping x3", "chrome-extension"],
        examples=["xpf0000/FlyEnv", "D4Vinci/Scrapling"],
    ),
    MESSAGING: dict(
        definition="Repositories whose purpose is messaging: WhatsApp/Telegram/"
                   "Matrix clients (any interface), bots, messaging APIs.",
        include_when=["WhatsApp client", "Telegram client", "chat bot",
                      "messaging REST API"],
        exclude_when=["generic notification libs without messaging framing"],
        conflicts_with=[TERMINAL, DESKTOP, WEB],
        strong_signals=["whatsapp-client", "whatsapp-desktop", "telegram-client",
                        "whatsapp+api", "telegram+client"],
        examples=["karem505/whatRust", "aldinokemal/go-whatsapp-web-multidevice"],
    ),
    FUN: dict(
        definition="Repositories whose primary purpose is playful/creative: "
                   "games, toys, art, generative visuals, demos, Minecraft "
                   "projects.  Requires positive fun evidence — never used as a "
                   "'misc' fallback.",
        include_when=["game", "minecraft project", "visual art/demo",
                      "creative toy"],
        exclude_when=["unknown purpose (→ Uncategorized)"],
        conflicts_with=[DEVUTILS, WEB],
        strong_signals=["game", "minecraft", "art", "creative", "simulator"
                        "+browser/3d"],
        examples=["EVV1E/waylandcraft", "jeremy-prt/bloub"],
    ),
    OWN: dict(
        definition="Repositories owned by the user (budi-imam-prasetyo/*).",
        include_when=["owner == budi-imam-prasetyo"],
        exclude_when=["everything else"],
        strong_signals=["owner namespace"],
        examples=["budi-imam-prasetyo/one-satu"],
    ),
}

# ---------------------------------------------------------------------------
# CATEGORY_DEFS is REFERENCE DOCUMENTATION for the taxonomy, not runtime
# logic.  Only RULES, COMPOUNDS, LEXICON and _PRECEDENCE below execute.
# In particular 'exclude_when' entries are NOT evaluated at runtime —
# exclusions are expressed through rule weights, negative/weak signals, and
# REPO_OVERRIDES.  Keep this dict in sync by hand when changing RULES.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Explicit overrides (every override carries a reason)
# ---------------------------------------------------------------------------

REPO_OVERRIDES = {
    "sipeed/picoclaw": {
        "category": AI,
        "reason": ("metadata says 'automate the mundane' only; it is an "
                   "ultra-lightweight personal AI assistant (per repo README)"),
    },
    "levy-street/world-of-claudecraft": {
        "category": FUN,
        "reason": "zero metadata; project is a Minecraft-style creative demo",
    },
    "risin42/NagramX": {
        "category": MOBILE,
        "reason": "Nagram is an Android Telegram client fork; metadata only "
                  "says 'a variant of Nagram'",
    },
}


def _repo_key(row):
    """Normalized repository identifier: lowercase, stripped of whitespace.

    Used consistently for own-project detection and override lookup so
    'Owner/Repo', 'owner/repo ' and 'owner/repo' all resolve the same way.
    """
    return " ".join((row.get("repo") or "").split()).lower()


# Override lookup keyed by normalized repo id (see _repo_key).
_OVERRIDES_KEYED = {
    " ".join(k.split()).lower(): v for k, v in REPO_OVERRIDES.items()
}

# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

# Topic aliases that collapse to one canonical concept.
_TOPIC_ALIASES = {
    "ai-agents": "ai-agents", "ai_agents": "ai-agents",
    "ai-agent": "ai-agent", "ai_agent": "ai-agent",
    "coding-agents": "coding-agents", "coding-agents-assistant": "coding-agents",
    "coding-agent": "coding-agent",
    "ai-agents-assistant": "ai-agents",
    "machine-learning": "machine-learning", "machinelearning": "machine-learning",
    "deep-learning": "deep-learning", "deeplearning": "deep-learning",
    "chatgpt": "chatgpt", "chat-gpt": "chatgpt",
    "llm": "llm", "large-language-model": "llm",
    "web-scraping": "web-scraping", "webscraping": "web-scraping",
    "web-scraper": "web-scraper", "webscraper": "web-scraper",
    "pen-testing": "penetration-testing",
    "pentesting": "penetration-testing",
    "red-team": "red-teaming",
    "desktop-app": "desktop-app", "desktopapp": "desktop-app",
    "android-app": "android-app", "androidapp": "android-app",
    "mobile-app": "mobile-app",
    "music-player": "music-player", "musicplayer": "music-player",
    "video-player": "video-player", "videoplayer": "video-player",
    "youtube-downloader": "youtube-downloader",
    "terminal-app": "terminal-app",
    "selfhosted": "self-hosted",
    "ui-ux": "ui-ux", "uiux": "ui-ux",
    "design-system": "design-system", "designsystem": "design-system",
    "design-tokens": "design-tokens", "designtokens": "design-tokens",
}

# unicode-normalize + lowercase + strip
def _norm(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


def _norm_topics(raw):
    out = set()
    for t in re.split(r"[\s,;]+", _norm(raw or "")):
        t = t.strip().strip("._")
        if not t:
            continue
        t = t.replace("_", "-")
        out.add(_TOPIC_ALIASES.get(t, t))
    return out


_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+.#-]*")


def _clean_token(tok):
    # strip trailing punctuation (. , ; : ! ? ) ] } and quotes
    return tok.rstrip(".,;:!?)]}\"' ")


def _tokenize(text):
    return [_clean_token(t) for t in _TOKEN_RE.findall(_norm(text or "")) if _clean_token(t)]


def _phrase_set(text):
    """All contiguous 1-3 token windows as phrases (boundary-safe)."""
    toks = _tokenize(text)
    phrases = {t for t in toks if len(t) >= 2}
    for i in range(len(toks)):
        for n in (2, 3):
            if i + n <= len(toks):
                phrases.add(" ".join(toks[i:i + n]))
    return phrases


def _features(row):
    desc = row.get("description") or ""
    repo = row.get("repo") or ""
    name = repo.split("/")[-1] if "/" in repo else repo
    topics = _norm_topics(row.get("topics"))
    desc_phrases = _phrase_set(desc)
    # name candidates: full name + bare repo name, phrase-matched too
    name_phrases = _phrase_set(name) | _phrase_set(repo)
    return {
        "topics": topics,
        "desc_phrases": desc_phrases,
        "name_phrases": name_phrases,
        "lang": _norm(row.get("language")),
        "owner": repo.split("/")[0].lower() if "/" in repo else "",
        "name": name,
    }


# ---------------------------------------------------------------------------
# Semantic lexicon  (concept -> canonical token)
# ---------------------------------------------------------------------------
# Values are canonical tokens matched against normalized topics and phrases.
# Purpose/domain/interface/tech is decided per-category in RULES below, but the
# vocabulary itself lives here so terms are reused and auditable.

LEXICON = {
    # --- AI / agents ---
    "coding_agent": {"coding-agent", "coding agent", "coding agent that",
                     "the open source coding agent", "agent that grows"},
    "agent_infra": {"agent-orchestration", "agent-runtime", "workspace-manager",
                    "agent-memory", "coding-agents", "agents"},
    "claude_codex": {"claude-code", "codex", "copilot", "cursor", "antigravity",
                     "opencode", "kilo-code", "gemini-cli"},
    "agent_skill": {"agent-skills", "ai-skills"},
    "ai_gateway": {"ai-gateway", "llm-gateway", "9router", "router"},
    "mcp": {"mcp", "mcp-server"},
    "llm_generic": {"llm", "large-language-model"},
    # --- AI/ML apps ---
    "deepfake": {"deepfake", "deep-fake", "face swap", "faceswap"},
    "local_llm": {"localai", "llamacpp", "offline chatgpt", "alternative to chatgpt"},
    "gen_ai": {"generative-ai", "ai-app-builder", "ai app builder", "agentic-browser",
               "ai-powered"},
    # --- design ---
    "design_system": {"design-system", "design system", "design-tokens", "design tokens",
                      "design-md", "design-engineering", "ui-audit", "design-to-code"},
    "icons": {"icon-pack", "svg-icons", "icons", "svg icon"},
    "canvas_sdk": {"whiteboard", "canvas", "tldraw", "drawing", "sketch",
                   "collaboration", "infinite-canvas"},
    "diagram": {"diagramming", "flowchart", "architecture-diagrams", "draw.io",
                "diagrams"},
    "ui_components": {"tailwindcss", "tailwind", "components", "component library",
                      "ui component", "shadcn", "uikit", "component"},
    "figma": {"figma", "figma-plugin"},
    # --- mobile ---
    "android": {"android", "android-app", "for android", "android-apps", "android-app",
                "android-game", "jetpack-compose", "material-design"},
    "flutter": {"flutter", "dart"},
    "mobile_app_type": {"mobile-app", "android app", "app for android", "app"},
    # --- terminal ---
    "tui": {"tui", "terminal-ui", "terminal-app", "terminal-ui"},
    "terminal": {"terminal", "cli", "command-line", "command-line-tool", "shell"},
    "terminal_phrase": {"terminal emulator", "terminal multiplexer",
                        "terminal workspace", "terminal-based",
                        "terminal-first", "terminal tool",
                        "terminal app", "terminal apps", "terminal dashboard",
                        "for the terminal", "in your terminal",
                        "from the terminal", "on the cli", "cli tool"},
    "multiplexer": {"terminal-multiplexer", "multiplexer", "tmux", "zellij"},
    "shell_enh": {"syntax-highlighting", "autosuggestions", "autosuggest", "zsh",
                  "shell history", "history", "shell-extension", "zsh-syntax",
                  "syntax highlighter"},
    "editor": {"neovim", "nvim", "plugin-manager", "neovim-plugin", "lazy.nvim",
               "editor"},
    # --- desktop ---
    "desktop": {"desktop", "desktop-app", "desktop-application", "desktop app",
                "gui", "desktop application"},
    "electron": {"electron", "electrobun", "tray", "system-tray"},
    "tauri": {"tauri", "tauri-v2", "wails", "webview"},
    "cleaner": {"cleaner", "system-cleaner", "windows-cleaner", "mac-cleaner",
                "linux-cleaner", "pc-optimization", "system-maintenance",
                "memory-cleaner", "ccleaner-alternative", "ram-cleaner"},
    # --- media ---
    "media_player": {"music-player", "music player", "youtube-player", "video-player",
                     "player", "mpv", "music streaming", "music app", "music",
                     "spotify", "apple-music", "youtube music", "ytmusic"},
    "streaming": {"streaming", "stream", "iptv", "live tv", "live-tv"},
    "video_dl": {"youtube-downloader", "audio-downloader", "video downloader",
                 "download videos", "download video", "downloader"},
    "media_content": {"movies", "tv-shows", "series", "anime", "shows", "moviebox"},
    # --- self-host / privacy ---
    "selfhost": {"self-hosted", "self-hosted server", "self hosted"},
    "vpn_server": {"wireguard", "tailscale", "control-server", "vpn", "headscale"},
    "cloud_drive": {"google-drive", "drive", "storage gateway", "cloud storage",
                    "telegram-drive", "unlimited storage", "9drive", "omnicloud"},
    "privacy": {"privacy", "privacy-first", "privacy first", "foss", "no-account",
                "end-to-end-encryption"},
    # --- lists ---
    "awesome": {"awesome", "awesome-list", "awesome-lists", "awesome-"},
    "list_phrase": {"curated list", "a list of", "list of", "collection of",
                    "free-for-dev", "app-ideas", "resources", "no-signups"},
    # Educational content needs an explicit course/tutorial-style token.
    # Bare 'learning' is NOT here on purpose: 'machine learning' must never
    # read as educational content (see ml_phrase + learning_weak).
    "learning_strong": {"course", "tutorial", "tutorials", "lessons",
                        "education", "quizzes", "for beginners",
                        "for-beginners", "learning path", "12 weeks",
                        "26 lessons", "step by step"},
    "learning_weak": {"learning", "learn"},
    # --- security ---
    "sec_re": {"reverse-engineering", "reverse engineering", "exploit", "exploits",
               "malware-analysis", "malware analysis", "ctf"},
    "sec_pentest": {"penetration-testing", "pen testing", "pentest", "offensive-security",
                    "red-teaming", "red team", "nuclei", "sqlmap", "metasploit",
                    "payload", "c2", "ransomware", "nmap", "vulnerability-scanner",
                    "vuln", "exploit-validation", "security scanner",
                    "port scanner"},
    "sec_mobile": {"mobile-security", "android-security", "ios-security", "mobsf",
                   "appsec", "devsecops"},
    "sec_research": {"bug-bounty", "bugbounty", "bug bounty", "bugbountybooks",
                     "owasp", "cybersecurity", "infosec", "security research",
                     "security-research", "hacking", "threat-research"},
    "sec_framework": {"security framework", "security-framework"},
    "sec_resources": {"templates for bug bounty", "bug bounty templates",
                      "bug bounty reporting"},
    # --- dev utils ---
    "dev_env": {"development-environment", "dev-environment", "local-development",
                "development environment", "docker-alternative", "xampp",
                "laragon-alternative", "herd-alternative"},
    "doc_conv": {"convert", "converter", "markdown", "epub", "pdf to",
                 "to clean markdown", "office", "docx", "pptx"},
    "scraping": {"web-scraping", "web scraping", "scraping", "web-scraper",
                 "scraper", "crawler", "crawling", "data-extraction",
                 "data extraction", "playwright", "selectors"},
    "osint": {"osint", "intelligence", "geopolitical", "threat-intel",
              "situational-awareness"},
    "osint_dashboard": {"intelligence dashboard", "global intelligence",
                        "geopolitical monitoring", "news aggregation"},
    "devtool_ext": {"chrome-extension", "firefox-extension", "firefox-addon",
                    "browser extension", "extension"},
    "devtool": {"developer-tools", "devtools", "toolkit", "tool kit", "tool",
                "utility", "productivity", "productivity-tools"},
    # --- web/backend ---
    "cms": {"headless-cms", "cms", "cms-framework", "content-management-system",
            "content management", "strapi"},
    "web_runtime": {"javascript runtime", "js runtime", "bundler",
                    "transpiler", "javascriptcore", "bun", "deno"},
    "web_runtime_weak": {"nodejs", "npm", "runtime", "node"},
    "web_framework": {"framework", "laravel", "symfony", "elysia", "django",
                      "rails", "express", "http", "server", "web", "web-framework",
                      "realtime", "backend", "api", "rest", "graphql",
                      "websocket", "web development", "web server", "rest-api",
                      "authentication", "forum package", "laravel package",
                      "laravel-packages", "php", "headless", "jamstack"},
    "webcontainers": {"webcontainers", "nodejs in your browser"},
    "coding_agent_desc": {"coding agent", "agent that grows", "coding agents",
                          "open source coding agent", "coding workflows",
                          "autonomous tasks", "agent for coding"},
    "genai_topic": {"ai-agents", "ai-agent", "agent", "claude", "codex",
                    "mcp", "llm", "openai", "copilot", "cursor"},
    "autonomous_desc": {"self-improving", "autonomous", "autonomous tasks",
                        "long-running autonomous", "coding workflow"},
    "sim3d": {"3d-gaussian-splatting", "3dgs", "gaussian-splatting", "webgl",
              "3d", "threejs", "webgpu", "globe", "gis", "spatial", "cesium",
              "photoreal", "satellite", "flight-tracking"},
    "android_tool": {"non-root", "root", "magisk", "xposed", "adb",
                     "circle to search", "trigger circle", "on any android"},
    "devtoolkit": {"toolkit", "tool kit", "dev tools", "developer tool",
                   "devtool", "toolbox"},
    "spam": {"spam", "spammer", "spamming", "ngl-link", "spamming-tool"},

    # --- messaging ---
    "whatsapp": {"whatsapp", "whatsapp-api", "whatsapp-client", "whatsapp-web",
                 "whatsapp-desktop", "whatsapp-bot", "golang-whatsapp",
                 "whatsapp-client", "whatsapp web", "whatsapp rest"},
    "telegram": {"telegram", "telegram-client", "telegram-api", "telegram-bot",
                 "nagram", "telegram client"},
    "messaging": {"messaging", "chat", "messenger", "matrix", "irc", "signal",
                  "xmpp", "discord", "slack"},
    # --- fun / creative ---
    "fun_game": {"game", "games", "gaming", "minecraft", "tetris", "puzzle",
                 "puzzle-games", "open-source-games", "toy", "playful"},
    "fun_art": {"art", "artistic", "creative", "generative-art", "svg-art",
                "ascii-art", "animation", "morphing", "avatar"},
    "fun_demo": {"demo", "experiment", "fun", "prank", "satire", "parody",
                 "remake", "demake", "clone"},
    "simulator": {"simulator", "simulation", "simulate"},
    "sim3d_editor": {"3d-gaussian-splatting", "3dgs", "gaussian-splatting",
                     "splat-editor", "3d editor", "3d-modeling", "voxel-editor"},
    "world_builder": {"world-builder", "worldbuilder", "isometric",
                      "middle-earth", "tolkien", "voxel", "landscape",
                      "map-builder", "creative-tool", "procedural",
                      "map editor"},
    "fun_game_names": {"minecraft", "in minecraft", "tetris", "game"},
    "sound_fx": {"sound-effect", "sound-effects", "sfx", "sound effect",
                 "ui sound", "sound-effects-library"},
    # "-agent" is a STRICT name-suffix pattern (see _match_name); the bare
    # token "agent" is deliberately NOT included — it would match any repo
    # merely mentioning agents and is covered by desc/topic rules instead.
    "agent_suffix": {"-agent"},
}

# ---------------------------------------------------------------------------
# Rules: (category, layer, source, lexicon_key, weight, evidence_format)
#   layer: purpose=100 | apptype=70 | domain=50 | interface=35 | tech=20
#   source: "topic" | "desc" | "name" | "compound"
# ---------------------------------------------------------------------------
# weight scale: 8-10 decisive purpose, 5-6 strong, 3-4 medium, 1-2 weak
# generic single keywords live at the bottom of LEXICON_*_WEAK lists.

P = "purpose"      # 100
A = "apptype"      # 70
Dm = "domain"      # 50
I = "interface"    # 35
T = "tech"         # 20

RULES = [
    # ---------------- AI Agents & Coding Assistants ----------------
    (AI, P, "topic", "coding_agent", 10, "explicit coding-agent identity"),
    (AI, P, "desc", "coding_agent", 8, "description says coding agent"),
    (AI, P, "topic", "agent_infra", 8, "agent infrastructure topic"),
    (AI, P, "topic", "agent_skill", 8, "skill/plugin for coding agents"),
    (AI, P, "topic", "claude_codex", 4, "coding-agent ecosystem topic"),
    (AI, P, "topic", "ai_gateway", 6, "AI gateway for coding agents"),
    (AI, P, "compound", "mcp_agent", 7, "MCP server with agent framing"),
    (AI, P, "name", "agent_infra", 5, "name signals agent infra"),
    (AI, Dm, "desc", "autonomous", 4, "autonomous task framing"),
    (AI, P, "desc", "coding_agent_desc", 8, "description: coding agent purpose"),
    (AI, P, "desc", "autonomous_desc", 7, "description: self-improving agent"),
    # prime-agent: name "-agent" + autonomous desc
    (AI, P, "name", "agent_suffix", 6, "name ends with -agent"),

    # ---------------- AI/ML ----------------
    (ML, P, "topic", "deepfake", 9, "deepfake/face-swap purpose"),
    (ML, P, "desc", "deepfake", 8, "description: deepfake/face-swap"),
    (ML, P, "topic", "local_llm", 7, "local LLM purpose"),
    (ML, P, "desc", "local_llm", 7, "description: local LLM client"),
    (ML, P, "topic", "gen_ai", 6, "generative-AI app purpose"),
    (ML, P, "desc", "gen_ai", 6, "description: AI generator/app"),
    (ML, Dm, "topic", "llm_generic", 3, "generic LLM domain"),
    (ML, Dm, "topic", "machine_learning", 3, "ML domain"),
    (ML, P, "desc", "ml_phrase", 5, "description: machine-learning subject"),

    # ---------------- Design ----------------
    (DESIGN, P, "topic", "design_system", 9, "design-system/token purpose"),
    (DESIGN, P, "desc", "design_system", 8, "description: design system/tokens"),
    (DESIGN, P, "topic", "icons", 7, "icon/svg purpose"),
    (DESIGN, P, "desc", "icons", 6, "description: icons/SVG"),
    (DESIGN, P, "topic", "canvas_sdk", 7, "canvas/whiteboard SDK purpose"),
    (DESIGN, P, "name", "tldraw", 8, "known canvas SDK name"),
    (DESIGN, P, "topic", "diagram", 6, "diagramming purpose"),
    (DESIGN, P, "desc", "diagram", 5, "description: diagramming"),
    (DESIGN, P, "topic", "figma", 7, "Figma purpose"),
    (DESIGN, P, "compound", "ui_components", 7, "UI component library purpose"),
    (DESIGN, P, "topic", "sim3d_editor", 6, "3D visual editor purpose"),
    (DESIGN, P, "desc", "sim3d", 6, "3D/visual editor description"),
    (DESIGN, P, "topic", "sound_fx", 7, "UI sound effects purpose"),
    (DESIGN, Dm, "topic", "design_generic", 2, "generic design topic"),

    # ---------------- Mobile ----------------
    (MOBILE, P, "topic", "android_app_specific", 9, "'android-app' identity"),
    (MOBILE, P, "desc", "for_android", 8, "description: for Android"),
    (MOBILE, P, "desc", "android_device", 7, "Android device-purpose phrase"),
    (MOBILE, P, "topic", "flutter", 4, "Flutter app framework"),
    (MOBILE, A, "topic", "android", 4, "android platform topic"),
    (MOBILE, A, "compound", "mobile_app", 7, "mobile-app framing"),
    (MOBILE, P, "compound", "android_app_strong", 6,
     "explicit Android app framing"),
    # security purpose on mobile beats generic mobile framing (purpose > apptype)
    (MOBILE, Dm, "topic", "app_generic", 1, "generic app topic"),

    # ---------------- Terminal ----------------
    (TERMINAL, P, "topic", "multiplexer", 10, "terminal multiplexer purpose"),
    (TERMINAL, P, "topic", "tui", 7, "TUI app identity"),
    (TERMINAL, P, "topic", "editor", 7, "editor/neovim purpose"),
    (TERMINAL, P, "topic", "shell_enh", 7, "shell enhancement purpose"),
    (TERMINAL, P, "desc", "shell_enh", 7, "shell enhancement description"),
    (TERMINAL, P, "topic", "commandline", 6, "command-line tool identity"),
    (TERMINAL, P, "topic", "text_expander", 6, "text-expander purpose"),
    (TERMINAL, P, "topic", "ph_terminal_strong", 7, "terminal-focused purpose"),
    (TERMINAL, P, "desc", "terminal_phrase", 6, "explicit terminal/CLI purpose phrase"),
    (TERMINAL, P, "desc", "sys_monitor", 7, "htop/system monitor purpose"),
    (TERMINAL, I, "desc", "cli_phrase", 3, "CLI interface phrase"),

    # ---------------- Desktop ----------------
    (DESKTOP, A, "topic", "desktop", 6, "desktop application identity"),
    (DESKTOP, A, "desc", "desktop", 5, "description: desktop app"),
    (DESKTOP, A, "topic", "electron", 5, "electron app"),
    (DESKTOP, A, "topic", "tauri", 5, "tauri/wails app"),
    (DESKTOP, P, "topic", "cleaner", 8, "system cleaner purpose"),
    (DESKTOP, P, "compound", "gui_app", 6, "GUI app framing"),

    # ---------------- Media ----------------
    (MEDIA, P, "topic", "media_player", 9, "media-player purpose"),
    (MEDIA, P, "desc", "media_player", 7, "description: music/player"),
    (MEDIA, P, "topic", "video_dl", 8, "video/audio downloader purpose"),
    (MEDIA, P, "desc", "video_dl", 7, "description: downloader"),
    (MEDIA, P, "topic", "streaming", 6, "streaming purpose"),
    (MEDIA, P, "desc", "streaming", 5, "description: streaming"),
    (MEDIA, P, "topic", "media_content", 2, "media content domain"),
    (MEDIA, P, "desc", "media_content", 1, "media content phrase"),

    # ---------------- Self-Hosted & Privacy ----------------
    (SELFHOST, P, "topic", "selfhost", 9, "self-hosted identity"),
    (SELFHOST, P, "desc", "selfhost", 8, "description: self-hosted"),
    (SELFHOST, P, "compound", "vpn_server_ctx", 8, "VPN/control-server purpose"),
    (SELFHOST, P, "compound", "drive_server", 7, "cloud-storage drive"),
    (SELFHOST, P, "desc", "cloud_drive", 6, "description: cloud storage"),
    (SELFHOST, P, "topic", "cloud_drive", 5, "cloud storage topic"),
    (SELFHOST, P, "topic", "privacy", 3, "privacy-first purpose"),
    (SELFHOST, P, "desc", "privacy", 5, "privacy-first description"),
    (SELFHOST, Dm, "topic", "privacy_dm", 3, "privacy domain"),
    (SELFHOST, P, "compound", "drive_strong", 12,
     "explicit storage/drive purpose overriding transport"),
    (SELFHOST, P, "topic", "drive_strong_t", 8,
     "storage-drive topic with transport context"),

    # ---------------- Curated Lists (content-type guard) ----------------
    (LISTS, P, "name", "awesome", 10, "name: awesome-* list"),
    (LISTS, P, "topic", "awesome", 9, "topic: awesome list"),
    (LISTS, P, "desc", "list_phrase", 8, "description: curated/list phrase"),
    (LISTS, P, "desc", "learning_strong", 8, "educational/course content"),
    # Bare 'learning'/'learn' is weak SUPPORT only: score 2 < MIN_SCORE (3), so
    # it can never make LISTS a candidate on its own.  'machine learning model'
    # stays ML (ml_phrase drives it); 'machine learning tutorial' becomes Lists
    # via learning_strong, not via this rule.  Redesign, not deletion, per spec.
    (LISTS, Dm, "desc", "learning_weak", 2, "educational context (weak support)"),
    (LISTS, P, "name", "app_ideas", 9, "name: app-ideas list"),

    # ---------------- Security ----------------
    (SECURITY, P, "topic", "sec_pentest", 9, "pentest/scanner purpose"),
    (SECURITY, P, "desc", "sec_pentest", 8, "description: pentest/security"),
    (SECURITY, P, "topic", "sec_mobile", 8, "mobile-security purpose"),
    (SECURITY, P, "topic", "sec_re", 8, "RE/malware-analysis purpose"),
    (SECURITY, P, "desc", "sec_re", 7, "description: reverse engineering"),
    (SECURITY, P, "topic", "sec_research", 6, "security research/bug bounty"),
    (SECURITY, P, "desc", "sec_research", 7, "security research phrase"),
    (SECURITY, P, "desc", "sec_resources", 7, "security resources/templates"),
    (SECURITY, P, "desc", "sec_framework", 8, "security framework phrase"),
    (SECURITY, Dm, "topic", "security_generic", 1, "generic security topic"),

    # ---------------- Developer Utilities ----------------
    (DEVUTILS, P, "topic", "dev_env", 8, "dev-environment purpose"),
    (DEVUTILS, P, "desc", "dev_env", 7, "description: dev environment"),
    (DEVUTILS, P, "compound", "doc_conv", 7, "document converter purpose"),
    (DEVUTILS, P, "desc", "doc_conv", 6, "description: converter"),
    (DEVUTILS, P, "topic", "scraping", 6, "web-scraping framework"),
    (DEVUTILS, P, "desc", "scraping", 5, "description: scraping"),
    (DEVUTILS, P, "compound", "scrape_heavy", 8, "multi scraping topic"),
    (DEVUTILS, P, "topic", "osint", 6, "OSINT/dashboard purpose"),
    (DEVUTILS, P, "desc", "osint", 5, "description: dashboard/monitoring"),
    (DEVUTILS, P, "topic", "devtool_ext", 6, "browser-extension devtool"),
    (DEVUTILS, P, "desc", "dev_toolkit_phrase", 6, "developer toolkit purpose"),
    (DEVUTILS, P, "desc", "devtool", 3, "developer tool purpose"),
    (DEVUTILS, Dm, "topic", "devtool", 2, "generic developer-tools topic"),

    # ---------------- Web / Backend ----------------
    (WEB, P, "topic", "cms", 9, "headless-CMS purpose"),
    (WEB, P, "desc", "cms", 8, "description: CMS"),
    (WEB, P, "topic", "web_runtime", 8, "JS runtime/toolchain purpose"),
    (WEB, Dm, "topic", "web_runtime_weak", 2, "JS-ecosystem domain"),
    (WEB, P, "desc", "web_runtime", 7, "description: runtime"),
    (WEB, P, "topic", "backend_web", 7, "backend/framework purpose"),
    (WEB, P, "desc", "backend_web", 6, "description: framework/server"),
    (WEB, P, "topic", "php_laravel", 5, "Laravel/PHP framework topic"),
    (WEB, P, "desc", "php_laravel", 5, "Laravel/PHP framework description"),
    (WEB, P, "desc", "realtime_backend", 8, "description: realtime backend"),
    (WEB, P, "topic", "webcontainers", 6, "web-container runtime"),
    (WEB, P, "desc", "webcontainers", 6, "description: node-in-browser"),
    (WEB, Dm, "topic", "php_laravel", 3, "Laravel/PHP domain"),

    # ---------------- Messaging ----------------
    (MESSAGING, P, "topic", "whatsapp", 10, "whatsapp client/API purpose"),
    (MESSAGING, P, "desc", "whatsapp", 8, "description: WhatsApp"),
    (MESSAGING, P, "topic", "telegram", 10, "telegram client/API purpose"),
    (MESSAGING, P, "desc", "telegram", 8, "description: Telegram"),
    (MESSAGING, P, "topic", "messaging", 6, "messaging purpose"),
    (MESSAGING, P, "desc", "messaging", 6, "description: messaging"),

    # ---------------- Fun (evidence-gated) ----------------
    (FUN, P, "topic", "spam", 5, "spam/prank tool purpose"),
    (FUN, P, "topic", "fun_game", 8, "game/playful purpose"),
    (FUN, P, "desc", "fun_game", 6, "description: game/playful"),
    (FUN, P, "topic", "fun_art", 6, "art/creative purpose"),
    (FUN, P, "desc", "fun_art", 5, "description: art/creative"),
    (FUN, P, "topic", "fun_demo", 4, "demo/experiment framing"),
    (FUN, P, "desc", "fun_demo", 4, "description: demo/experiment"),
    (FUN, P, "compound", "sim_visual", 6, "simulator with visual/browser purpose"),
    (FUN, P, "topic", "world_builder", 7, "world-builder/creative-toy purpose"),
    (FUN, P, "desc", "world_builder", 6, "description: world/landscape builder"),
    (FUN, P, "desc", "fun_game_names", 6, "description: minecraft/game"),

    # ---------------- Uncategorized helpers (non-scoring) ----------------
]

# Small lexicon additions used above that are easier to read here than inline.


# Small lexicon additions used above that are easier to read here than inline.
LEXICON.update({
    "machine_learning": {"machine-learning", "deep-learning", "neural-network",
                         "tensorflow", "pytorch", "ml"},
    "ml_phrase": {"machine learning", "deep learning", "neural network",
                  "neural networks", "machine-learning model", "ml model",
                  "training", "inference"},
    "autonomous": {"autonomous", "autonomous tasks", "self-improving"},
    "design_generic": {"design", "ui", "ux", "ui-ux", "user-interface",
                       "interface-design"},
    "android_app_specific": {"android-app", "android-apps", "android-game"},
    "for_android": {"for android", "android app", "an android app",
                    "runs on android", "on android"},
    "mobile_app": {"flutter+app", "kotlin app", "android studio"},
    "app_generic": {"app", "application", "mobile"},
    "commandline": {"command-line-tool", "commandline", "cli-tool",
                    "terminal tool", "terminal utility", "cli", "command-line",
                    "terminal"},
    "text_expander": {"text-expander", "text expander"},
    "gui_app": {"gui application", "graphical application", "screen recorder",
                "screen-recorder"},
    "cli_phrase": {"on the cli", "cli tool", "for the terminal", "terminal app",
                   "terminal-first", "terminal-based", "from the terminal",
                   "in your terminal", "cli", "a cli", "terminal"},
    "security_generic": {"security", "secure", "privacy-security"},
    "backend_web": {"backend", "realtime", "authentication", "web-framework",
                    "web-server", "api", "rest-api", "graphql", "framework+http",
                    "framework+server", "framework+web", "headless", "jamstack",
                    "server+web", "http+server", "bun+framework", "elysia"},
    "realtime_backend": {"realtime backend", "backend in 1 file", "in 1 file",
                         "realtime database"},
    "php_laravel": {"laravel", "php", "laravel-package", "laravel-packages",
                    "php7", "php8", "livewire"},
    "laravel_phrase": {"laravel request", "laravel project", "laravel app"},
    "webcontainers": {"webcontainers", "nodejs in your browser"},
    "coding_agent_desc": {"coding agent", "agent that grows", "coding agents",
                          "open source coding agent", "coding workflows",
                          "autonomous tasks", "agent for coding"},
    "autonomous_desc": {"self-improving", "autonomous", "autonomous tasks",
                        "long-running autonomous", "coding workflow"},
    "sys_monitor": {"top/htop", "htop alternative", "system-monitor",
                    "system monitor", "alternative to top"},
    "android_device": {"non-root", "circle to search", "on any android",
                       "root", "android 9"},
    "telegram_extra": {"telegram-drive", "9drive", "telegram account",
                       "telegram drive"},
    "ph_terminal_strong": {"top/htop", "htop alternative", "system-monitor",
                           "system monitor", "terminal multiplexer",
                           "terminal emulator", "terminal dashboard"},
    "tldraw": {"tldraw"},
    "app_ideas": {"app-ideas"},
    "privacy_dm": {"end-to-end-encryption", "no-account",
                   "private", "anonymous"},
    "dev_toolkit_phrase": {"toolkit for devs", "toolkit for developers",
                           "tools for developers"},
    "drive_strong_t": {"telegram-drive", "9drive", "google-drive-storage",
                       "cloud-storage", "storage-gateway"},
})

# Compound signatures: source="compound", key in COMPOUNDS.
COMPOUNDS = {
    "mcp_agent": {
        "topic_any": LEXICON["mcp"] | {"ai", "agent", "agents"},
        "desc_any": LEXICON["coding_agent"] | LEXICON["claude_codex"]
                    | {"agent", "memory", "remember"},
        "ev": "MCP topic + agent/LLM description"},
    "ui_components": {
        "topic_any": {"tailwindcss", "tailwind", "shadcn", "uikit",
                      "component-library", "react-components", "nativewind"},
        "desc_any": {"component", "components", "ui library", "design",
                     "utility-first", "utility first", "tailwind css",
                     "design system"},
        "ev": "component/tailwind + UI context"},
    "mobile_app": {
        "topic_any": {"kotlin", "java", "dart", "flutter", "android"},
        "desc_any": {"app", "application", "for android", "mobile"},
        "ev": "mobile language/topic + app description"},
    "gui_app": {
        "topic_any": {"desktop", "electron", "tauri", "wails", "gui",
                      "system-tray", "webview"},
        "desc_any": {"app", "application", "client", "desktop", "mac",
                     "windows", "linux"},
        "ev": "desktop technology + app description"},
    "drive_server": {
        "topic_any": {"drive", "gateway", "storage", "telegram-drive",
                      "cloud-storage", "9drive"},
        "desc_any": {"storage", "drive", "cloud", "unlimited"},
        "ev": "storage/drive topic + storage description"},
    "drive_strong": {
        "topic_any": {"drive", "gateway", "storage", "telegram-drive",
                      "cloud-storage", "9drive", "telegram"},
        "desc_any": {"unlimited, secure cloud storage", "cloud storage drive",
                     "storage drive", "secure cloud storage"},
        "ev": "explicit cloud-storage-drive purpose"},
    "vpn_server_ctx": {
        "topic_any": LEXICON["vpn_server"],
        "desc_any": {"server", "self-hosted", "self hosted", "control server",
                     "gateway", "hosted"},
        "ev": "VPN/wireguard topic + server context"},
    "drive_strong_t": {
        "topic_any": {"telegram-drive", "9drive", "cloud-storage",
                      "storage-gateway"},
        "desc_any": {"storage", "drive", "cloud", "unlimited"},
        "ev": "storage-drive topic + storage description"},
    "doc_conv": {
        "topic_any": {"convert", "conversion", "markdown", "pdf"},
        "desc_any": {"convert", "to markdown", "to clean markdown", "converter"},
        "ev": "conversion topic + description"},
    "scrape_heavy": {
        "topic_any": LEXICON["scraping"],
        "desc_any": {"scraping", "scrape", "crawling", "crawl",
                     "extract", "extraction"},
        "min_topics": 3,
        "ev": "3+ scraping topics"},
    "sim_visual": {
        "topic_any": {"webgl", "cesium", "browser", "3d", "globe", "gis",
                      "geospatial", "web"},
        "desc_any": {"simulator", "simulation", "simulate"},
        "ev": "simulator + visual/browser technology"},
    "android_app_strong": {
        "topic_any": {"android", "kotlin", "java", "dart", "flutter",
                      "jetpack-compose"},
        "desc_any": {"app", "application", "for android", "android", "mobile"},
        "ev": "explicit Android app framing"},
}

# Weak support topics for interface/tech layers — pulled from LEXICON.
_WEAK_TOPIC_RULES = []  # (not needed — the typed rules above suffice)


# ===========================================================================
# Matching engine (deterministic)
# ===========================================================================


def _match_topics(f, pats):
    return f["topics"] & pats


def _match_desc(f, pats):
    hit = set()
    tokens = {t for t in f["desc_phrases"] if " " not in t}
    phrases = {p for p in f["desc_phrases"] if " " in p}
    for p in pats:
        if " " in p:
            if p in f["desc_phrases"]:
                hit.add(p)
        elif p.endswith("-"):
            # prefix marker (e.g. "terminal-") -> token startswith
            pre = p[:-1]
            if any(t.startswith(pre) for t in tokens) or \
               any(ph.startswith(pre) or pre in ph.split()
                   for ph in phrases):
                hit.add(p)
        elif p in tokens:
            # any single word: exact token equality, never substring
            hit.add(p)
        elif any(t.startswith(p + "-") for t in tokens):
            # "terminal" matches token "terminal-based" via hyphen boundary
            hit.add(p)
    return hit


def _match_name(f, pats):
    hit = set()
    for p in pats:
        if p.startswith("-"):
            # strict suffix pattern (e.g. "-agent"): the bare repo name must
            # END with it — "prime-agent" matches, "agent-extra" does not,
            # and a bare name "agent" does not claim -agent suffix semantics.
            if _norm(f["name"]).endswith(p):
                hit.add(p)
        elif p.endswith("-"):
            if p[:-1] in f["name"] or any(t.startswith(p[:-1]) for t in f["name_phrases"]):
                hit.add(p)
        elif p in f["name_phrases"]:
            hit.add(p)
    return hit


def _has_compound(f, spec):
    """Boundary-safe compound check.

    topic_any: set intersection on normalized topics (exact).
    desc_any : same semantics as _match_desc — exact token, exact phrase,
               or controlled hyphen-prefix.  NEVER raw substring, so short
               generic tokens like 'app', 'mac', 'tool' cannot fire via
               unrelated words ('machine', 'toolkit', ...).
    """
    t_hit = bool(f["topics"] & spec["topic_any"])
    if "min_topics" in spec:
        t_hit = len(f["topics"] & spec["topic_any"]) >= spec["min_topics"]
    if not t_hit:
        return False
    return any(_match_desc(f, {d}) for d in spec["desc_any"])


def score_details(row):
    """Return {category: (score, [evidence])}.

    score_details output remains compatible with v1: category -> (score,
    evidence list).  Internally every rule fires only on typed signals.
    """
    f = _features(row)
    out = {}  # cat -> [accumulated score, evidence list]

    def bump(cat, w, ev):
        s, lst = out.get(cat, (0, []))
        out[cat] = (s + w, lst + [ev])

    # compound rules first
    for key, spec in COMPOUNDS.items():
        if _has_compound(f, spec):
            # find which category uses this compound
            for cat, layer, src, k, w, ev in RULES:
                if src == "compound" and k == key:
                    bump(cat, w, spec.get("ev", ev))

    for cat, layer, src, key, w, ev in RULES:
        if src == "compound":
            continue
        if src == "topic":
            pats = LEXICON.get(key)
            if pats and _match_topics(f, pats):
                bump(cat, w, ev)
        elif src == "desc":
            pats = LEXICON.get(key)
            if pats and _match_desc(f, pats):
                bump(cat, w, ev)
        elif src == "name":
            pats = LEXICON.get(key)
            if pats and _match_name(f, pats):
                bump(cat, w, ev)

    return out


# ---------------------------------------------------------------------------
# Conflict / precedence resolution
# ---------------------------------------------------------------------------
# Purpose categories outrank interface (Terminal) and apptype (Desktop) when
# both scored.  Specific beats generic via margin; tie-break by precedence.

_PRECEDENCE = [
    # content-type guard: curated lists never get re-categorized by their
    # listed domain (awesome-design-md stays a list, not Design)
    (MOBILE, {LISTS}, "always"), (SECURITY, {LISTS}, "score"),
    (DESIGN, {LISTS}, "always"), (AI, {LISTS}, "always"),
    (ML, {LISTS}, "always"), (WEB, {LISTS}, "always"),
    (DEVUTILS, {LISTS}, "always"), (MEDIA, {LISTS}, "always"),
    (SELFHOST, {LISTS}, "always"), (TERMINAL, {LISTS}, "always"),
    (DESKTOP, {LISTS}, "always"), (MESSAGING, {LISTS}, "always"),
    (FUN, {LISTS}, "always"),
    # purpose beats interface when the purpose evidence is comparable in
    # strength (>= 0.8x the interface score): a terminal WhatsApp client is
    # Messaging, yet a CLI tool whose subject IS the terminal (ani-cli) or
    # one with only incidental domain topics (espanso) stays Terminal.
    (TERMINAL, {MESSAGING, MEDIA, SECURITY, AI, ML}, "ratio"),
    (TERMINAL, {SELFHOST, WEB, DEVUTILS}, "score"),
    # apptype (desktop) always yields to a present purpose: a WhatsApp
    # desktop client is Messaging even when tauri/electron topics dominate
    # (whatRust).
    (DESKTOP, {MESSAGING, MEDIA, AI, SELFHOST}, "always"),
    (DEVUTILS, {MEDIA, MESSAGING, SECURITY, MOBILE, AI}, "score"),
    # dev-environment purpose is a dev utility, not a web framework (FlyEnv)
    (WEB, {DEVUTILS}, "score"),
    # mobile is an apptype: a comparable-strength real purpose (security
    # scanner etc.) beats it, while incidental domain topics do not
    # (blockads stays Mobile)
    (MOBILE, {SECURITY, ML, SELFHOST}, "ratio"),
    (MOBILE, {MEDIA, MESSAGING}, "score"),
    # messaging as a mere transport for storage/infra yields to it
    (MESSAGING, {SELFHOST}, "score"),
]


def _resolve(cands):
    """cands: list of (cat, score).  Return (winner, ranked_after_precedence)."""
    if not cands:
        return None, []
    if len(cands) == 1:
        return cands[0][0], cands

    by_cat = {c: s for c, s in cands}
    for weaker, stronger_set, mode in _PRECEDENCE:
        if weaker not in by_cat:
            continue
        strong = [by_cat[c] for c in stronger_set
                  if c in by_cat and by_cat[c] >= 4]
        if not strong:
            continue
        # "always": content-type/purpose guard wins regardless of score.
        # "score": yield only when the stronger category actually outscores
        # the weaker one — presence alone is not enough.
        # "ratio": yield when the stronger category is at least 0.8x the
        # weaker one — comparable-strength purpose beats interface/apptype.
        if mode == "always" or max(strong) > by_cat[weaker] \
                or (mode == "ratio" and max(strong) >= 0.8 * by_cat[weaker]):
            by_cat.pop(weaker, None)
    ranked = sorted(by_cat.items(), key=lambda x: (-x[1], _order_rank(x[0])))
    winner = ranked[0][0] if ranked else cands[0][0]
    return winner, ranked


# App-type/interface categories that a *described* purpose can overrule:
# when the description explicitly states a distinct function ("security
# scanner app for Android"), that function beats the platform/app-type
# identity.  App-kind purposes (music player, chat client) do NOT overrule —
# a "music player for Android" is filed under Mobile by design.
_APPTYPE_LIKE = (MOBILE, DESKTOP, TERMINAL)
_DESC_PURPOSE_CATS = {SECURITY, AI, ML, SELFHOST, WEB, DEVUTILS, LISTS}


def _desc_purpose_cats(f):
    """Categories whose purpose is stated in the description (strong rules)."""
    hits = set()
    for cat, layer, src, key, w, ev in RULES:
        if src == "desc" and layer == P and w >= 7 and cat in _DESC_PURPOSE_CATS:
            pats = LEXICON.get(key)
            if pats and _match_desc(f, pats):
                hits.add(cat)
    return hits


def _order_rank(cat):
    try:
        return CATEGORIES.index(cat)
    except ValueError:
        return 99


def _confidence(margin, best_score):
    """Deterministic confidence in [0,1]: score & margin driven."""
    # normalize: margin >= 10 -> 1.0; scale with best score magnitude
    c = min(1.0, (0.35 + 0.45 * min(1.0, best_score / 12.0)
                  + 0.2 * min(1.0, margin / 8.0)))
    return round(c, 2)


def _decide(row):
    """Single source of truth for the final classification decision.

    Runs the full pipeline: own-project detection, repository overrides,
    typed scoring, candidate threshold, precedence resolution, described-
    purpose override, weak-evidence handling, and ambiguity handling.

    Returns a decision dict:
        category        final category
        ranked          [(cat, score), ...] candidates that SURVIVED
                        precedence, final winner first
        best_score      score of the top ranked candidate (0 if none)
        runner_up       second ranked category (None if absent)
        margin          best_score - runner_up score (or best_score alone)
        confidence      deterministic [0,1] from margin + best_score
        evidence        list of human-readable evidence strings
        ambiguous       True when a close runner-up exists
        decision_source 'own' | 'override' | 'rules'

    classify() and audit() both consume this — do not duplicate decision
    logic elsewhere.
    """
    repo = _repo_key(row)

    # 1) own projects — hard decision, no scorer behind it
    if repo.startswith("budi-imam-prasetyo/"):
        return {
            "category": OWN,
            "ranked": [(OWN, 0)], "best_score": 0, "runner_up": None,
            "margin": 0, "confidence": 1.0,
            "evidence": ["own repository (owner == budi-imam-prasetyo)"],
            "ambiguous": False, "decision_source": "own",
        }

    # 2) explicit repository overrides — hard decisions too
    if repo in _OVERRIDES_KEYED:
        o = _OVERRIDES_KEYED[repo]
        return {
            "category": o["category"],
            "ranked": [(o["category"], 0)], "best_score": 0, "runner_up": None,
            "margin": 0, "confidence": 1.0,
            "evidence": [f"override: {o['reason']}"],
            "ambiguous": False, "decision_source": "override",
        }

    # 3) typed scoring + candidate threshold
    d = score_details(row)
    f = _features(row)
    cands = sorted(((c, s) for c, (s, _e) in d.items()), key=lambda x: -x[1])
    cands = [(c, s) for c, s in cands if s >= MIN_SCORE]

    if not cands:
        if (row.get("description") or "").strip() or (row.get("topics") or "").strip():
            ev = ["no strong evidence (below threshold); refusing to guess"]
        else:
            ev = ["no signals at all"]
        return {
            "category": UNCATEGORIZED,
            "ranked": [], "best_score": 0, "runner_up": None,
            "margin": 0, "confidence": 1.0,
            "evidence": ev, "ambiguous": False, "decision_source": "rules",
        }

    # 4) precedence resolution
    winner, ranked = _resolve(cands)
    if winner is None:
        winner = cands[0][0]

    # 5) described-purpose override: an explicitly described function beats
    #    an app-type/interface identity that only outranks it via topic mass
    if winner in _APPTYPE_LIKE and len(ranked) > 1:
        dp = _desc_purpose_cats(f)
        if dp:
            for c, _s in ranked[1:]:
                if c in dp:
                    winner = c
                    break

    # 6) re-rank with the FINAL winner first so best_score/runner_up/margin
    #    always describe the actual decision (not the raw scorer); margin
    #    may be negative when an override picked a lower-scored purpose.
    if ranked and ranked[0][0] != winner:
        scores = dict(ranked)
        ranked = [(winner, scores[winner])] + \
                 [(c, s) for c, s in ranked if c != winner]
    if len(ranked) > 1:
        margin = ranked[0][1] - ranked[1][1]
    else:
        margin = ranked[0][1] if ranked else 0
    best_score = ranked[0][1] if ranked else 0
    runner_up = ranked[1][0] if len(ranked) > 1 else None

    # 7) very weak overall — factual refusal.  Fun requires real fun/creative
    #    evidence, so a weak single signal is never promoted to Fun either.
    if best_score <= WEAK_SINGLE_SCORE and len(cands) == 1:
        return {
            "category": UNCATEGORIZED,
            "ranked": ranked, "best_score": best_score, "runner_up": None,
            "margin": margin, "confidence": 1.0,
            "evidence": [f"only weak evidence (score {best_score}); "
                         "refusing to guess"],
            "ambiguous": False, "decision_source": "rules",
        }

    # 8) ambiguity note on the winner's evidence
    ev_list = d[winner][1] if winner in d else []
    ambiguous = len(ranked) > 1 and margin <= 2
    if ambiguous:
        ev_list = ev_list + [f"ambiguous: close runner-up {runner_up} "
                             f"(margin {margin})"]
    return {
        "category": winner, "ranked": ranked, "best_score": best_score,
        "runner_up": runner_up, "margin": margin,
        "confidence": _confidence(margin, best_score),
        "evidence": ev_list, "ambiguous": ambiguous,
        "decision_source": "rules",
    }


def classify(row):
    """Return (category, evidence_list).

    Deterministic, offline, local.  Thin wrapper over _decide(): own
    projects first, then overrides, then typed scoring + precedence.
    Fallback = ❓ Uncategorized when no positive evidence clears MIN_SCORE;
    Fun requires fun evidence.
    """
    dec = _decide(row)
    return dec["category"], dec["evidence"]


def audit(rows):
    """Run classifier over dataset; return list of audit dicts.

    Every audit dict is derived from _decide(), so predicted/best_score/
    runner_up/margin/confidence always describe the SAME final decision —
    including own/override repos (hard decisions report confidence 1.0 and
    no misleading scorer numbers).
    """
    res = []
    for r in rows:
        dec = _decide(r)
        res.append({
            "repo": r.get("repo"),
            "predicted": dec["category"],
            "confidence": dec["confidence"],
            "best_score": dec["best_score"],
            "runner_up": dec["runner_up"],
            "margin": dec["margin"],
            "evidence": dec["evidence"],
            "ambiguous": dec["ambiguous"],
            "decision_source": dec["decision_source"],
            "ranked": [[c, s] for c, s in dec["ranked"]],
            "description": (r.get("description") or "")[:80],
            "topics": (r.get("topics") or "")[:90],
        })
    return res


def _print_audit(res):
    for a in res:
        print(f"\nRepository: {a['repo']}")
        print(f"  Category: {a['predicted']}")
        print(f"  Confidence: {a['confidence']:.2f}  "
              f"(score {a['best_score']}, margin {a['margin']}, "
              f"runner-up {a['runner_up']})")
        for e in a["evidence"]:
            print(f"    + {e}")
        if a["ambiguous"]:
            print("    ~ AMBIGUOUS")


def _load_rows(path):
    with open(path) as fh:
        data = json.load(fh)
    if isinstance(data, dict) and "repos" in data:
        return data["repos"]
    return data


if __name__ == "__main__":
    if "--audit" in sys.argv:
        idx = sys.argv.index("--audit")
        p = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "budi-stars.json"
        rows = _load_rows(p)
        results = audit(rows)
        if "--json" in sys.argv:
            print(json.dumps(results, indent=1, ensure_ascii=False))
        else:
            _print_audit(results)
            high = sum(1 for a in results if a["confidence"] >= 0.7)
            amb = sum(1 for a in results if a["ambiguous"])
            unc = sum(1 for a in results if a["predicted"] == UNCATEGORIZED)
            print(f"\n=== audit summary: {len(results)} repos | "
                  f"high-conf: {high} | ambiguous: {amb} | "
                  f"uncategorized: {unc}")
    else:
        print(f"engine v{__version__}")
        print("usage: python3 engine.py --audit <json> [--json]")

