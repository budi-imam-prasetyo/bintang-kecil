"""Regression tests for scrape.categorize().

Each case pins a real repo from the starred list to its intended category,
using the signals (description/topics/language) that actually come from the
GitHub API. Run: python3 -m unittest discover tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scrape  # noqa: E402


def row(repo, lang="", desc="", topics=""):
    return {"repo": repo, "language": lang, "description": desc, "topics": topics}


class TestCategorize(unittest.TestCase):
    # --- AI Agents & Coding Assistants ---
    def test_hermes_agent(self):
        r = row("NousResearch/hermes-agent", "Python",
                "The agent that grows with you",
                "ai, ai-agent, ai-agents, anthropic, claude, claude-code, codex, hermes, hermes-agent, llm, openai")
        self.assertEqual(scrape.categorize(r), "🤖 AI Agents & Coding Assistants")

    def test_opencode_coding_agent(self):
        r = row("anomalyco/opencode", "TypeScript", "The open source coding agent.", "")
        self.assertEqual(scrape.categorize(r), "🤖 AI Agents & Coding Assistants")

    def test_prime_agent_by_name(self):
        r = row("PrimeIntellect-ai/prime-agent", "TypeScript",
                "A self-improving RLM agent for coding workflows and long-running autonomous tasks.", "")
        self.assertEqual(scrape.categorize(r), "🤖 AI Agents & Coding Assistants")

    def test_uteke_agent_memory(self):
        r = row("codecoradev/uteke", "Rust",
                "The Brain for Your AI — Local-first memory engine for AI agents. Store, recall, and search memories",
                "agent-memory, ai, ai-agents, cli, embeddings, llm, local-first, mcp, mcp-server, memory, rag, vector-database")
        self.assertEqual(scrape.categorize(r), "🤖 AI Agents & Coding Assistants")

    def test_picoclaw_override(self):
        # zero-signal repo (empty desc+topics) — explicit override
        r = row("sipeed/picoclaw", "Go",
                "Tiny, Fast, and Deployable anywhere — automate the mundane, unleash your creativity", "")
        self.assertEqual(scrape.categorize(r), "🤖 AI Agents & Coding Assistants")

    def test_ai_gateway_router(self):
        r = row("diegosouzapw/OmniRoute", "TypeScript",
                "Free MIT AI gateway: one endpoint, 352 providers",
                "ai-agents, ai-gateway, claude-code, codex, cursor, llm-gateway, mcp")
        self.assertEqual(scrape.categorize(r), "🤖 AI Agents & Coding Assistants")

    # --- AI/ML ---
    def test_jan_local_llm(self):
        r = row("janhq/jan", "TypeScript",
                "Jan is an open source alternative to ChatGPT that runs 100% offline on your computer",
                "chatgpt, local-ai, llm, offline")
        self.assertEqual(scrape.categorize(r), "🧠 AI/ML")

    def test_deepfake(self):
        r = row("hacksider/Deep-Live-Cam", "Python",
                "real time face swap and one-click video deepfake with only a single image",
                "deepfake, faceswap")
        self.assertEqual(scrape.categorize(r), "🧠 AI/ML")

    # --- UI/UX & Design ---
    def test_tldraw_canvas_sdk(self):
        r = row("tldraw/tldraw", "TypeScript",
                "Build infinite canvas apps in React with the tldraw SDK.",
                "canvas, sdk, whiteboard, collaboration")
        self.assertEqual(scrape.categorize(r), "🎨 UI/UX & Design")

    def test_design_tokens(self):
        r = row("dembrandt/dembrandt", "TypeScript",
                "Extract any website's design system into tokens in seconds",
                "design-system, design-tokens")
        self.assertEqual(scrape.categorize(r), "🎨 UI/UX & Design")

    # --- Mobile Apps ---
    def test_komikku_manga_reader(self):
        r = row("komikku-app/komikku", "Kotlin",
                "Free and open source manga reader for Android",
                "android, jetpack-compose, material-design")
        self.assertEqual(scrape.categorize(r), "📱 Mobile Apps")

    def test_android_vpn_adblock(self):
        r = row("pass-with-high-score/blockads-android", "Kotlin",
                "Block ads system-wide on Android using local VPN-based DNS filtering. No root needed.",
                "android, ad-blocker, vpn")
        self.assertEqual(scrape.categorize(r), "📱 Mobile Apps")

    # --- Terminal & CLI ---
    def test_glances_system_monitor(self):
        r = row("nicolargo/glances", "Python",
                "Glances an Eye on your system. A top/htop alternative for GNU/Linux, BSD, macOS and Windows",
                "monitoring, python, system, terminal, web")
        self.assertEqual(scrape.categorize(r), "💻 Terminal & CLI")

    def test_ani_cli(self):
        r = row("pystardust/ani-cli", "Shell",
                "A cli tool to browse and play anime",
                "anime, cli, terminal, shell")
        self.assertEqual(scrape.categorize(r), "💻 Terminal & CLI")

    def test_zellij(self):
        r = row("zellij-org/zellij", "Rust",
                "A terminal workspace with batteries included",
                "multiplexer, terminal, workspace")
        self.assertEqual(scrape.categorize(r), "💻 Terminal & CLI")

    # --- Desktop Apps ---
    def test_pake(self):
        r = row("tw93/Pake", "Rust",
                "Turn any webpage into a desktop app with one command.",
                "desktop, tauri, macos, windows, linux")
        self.assertEqual(scrape.categorize(r), "🖥️ Desktop Apps")

    def test_kudu_system_cleaner(self):
        r = row("AdventDevInc/kudu", "TypeScript",
                "Free Windows, Mac and Linux cleaner, scanner, and more.",
                "ccleaner-alternative, cleaner, system-cleaner, windows-cleaner, "
                "mac-cleaner, linux-cleaner, system-maintenance, pc-optimization")
        self.assertEqual(scrape.categorize(r), "🖥️ Desktop Apps")

    def test_electrobun(self):
        r = row("blackboardsh/electrobun", "TypeScript",
                "Build ultra fast, tiny, and cross-platform desktop apps with Typescript.", "")
        self.assertEqual(scrape.categorize(r), "🖥️ Desktop Apps")

    # --- Media ---
    def test_moviebox_tui(self):
        r = row("mesamirh/MovieBox-Tui", "Rust",
                "Terminal interface to find, download, and stream movies, TV shows, and live TV",
                "anime, cli, downloader, iptv, movies, mpv, series, streaming, terminal, tui, tv-shows")
        self.assertEqual(scrape.categorize(r), "🎬 Media")

    def test_vidbee_downloader(self):
        r = row("nexmoe/VidBee", "TypeScript",
                "Download video and audio from YouTube, TikTok, Twitter",
                "downloader, youtube-downloader")
        self.assertEqual(scrape.categorize(r), "🎬 Media")

    # --- Self-Hosted & Privacy ---
    def test_headscale(self):
        r = row("juanfont/headscale", "Go",
                "An open source, self-hosted implementation of the Tailscale control server",
                "wireguard, tailscale, server, control-server, vpn")
        self.assertEqual(scrape.categorize(r), "🔒 Self-Hosted & Privacy")

    def test_telegram_drive(self):
        r = row("caamer20/Telegram-Drive", "TypeScript",
                "Turn your Telegram account into an unlimited, secure cloud storage drive.",
                "open-source, react, rust, tauri, telegram, typescript")
        self.assertEqual(scrape.categorize(r), "🔒 Self-Hosted & Privacy")

    # --- Curated Lists ---
    def test_awesome_go(self):
        r = row("avelino/awesome-go", "Go",
                "A curated list of awesome Go frameworks, libraries and software",
                "awesome, awesome-list, go")
        self.assertEqual(scrape.categorize(r), "📚 Curated Lists & Learning")

    def test_ml_for_beginners(self):
        r = row("microsoft/ML-For-Beginners", "Jupyter Notebook",
                "12 weeks, 26 lessons, 52 quizzes, classic Machine Learning for all",
                "education, beginners, lessons, quizzes")
        self.assertEqual(scrape.categorize(r), "📚 Curated Lists & Learning")

    # --- Security ---
    def test_mobsf(self):
        r = row("MobSF/Mobile-Security-Framework-MobSF", "JavaScript",
                "Mobile Security Framework (MobSF) is an automated, all-in-one mobile application pen-testing framework",
                "mobile-security, android-security, static-analysis, owasp")
        self.assertEqual(scrape.categorize(r), "🛡️ Security")

    def test_cybermes_redteam(self):
        r = row("Zyrexnn/Cybermes", "Python",
                "Autonomous Offensive Security, Bug Bounty & Red Teaming Agent Framework",
                "bug-bounty, devsecops, offensive-security, penetration-testing, red-teaming")
        self.assertEqual(scrape.categorize(r), "🛡️ Security")

    def test_reverse_skill(self):
        r = row("zhaoxuya520/reverse-skill", "PowerShell",
                "Reverse Engineering / Authorized Penetration Testing / Security Research Skill Router Pack", "")
        self.assertEqual(scrape.categorize(r), "🛡️ Security")

    # --- Web Frameworks & Backend ---
    def test_strapi(self):
        r = row("strapi/strapi", "TypeScript",
                "Strapi is the leading open-source headless CMS.",
                "headless-cms, cms, nodejs")
        self.assertEqual(scrape.categorize(r), "🌐 Web Frameworks & Backend")

    def test_pocketbase(self):
        r = row("pocketbase/pocketbase", "Go",
                "Open Source realtime backend in 1 file",
                "backend, realtime, authentication, go")
        self.assertEqual(scrape.categorize(r), "🌐 Web Frameworks & Backend")

    # --- Developer Utilities ---
    def test_scrapling_framework(self):
        r = row("D4Vinci/Scrapling", "Python",
                "An adaptive Web Scraping framework that handles everything from a single request to a full-scale crawl!",
                "ai-scraping, crawler, crawling, data-extraction, scraping, "
                "web-scraper, web-scraping, webscraping, playwright")
        self.assertEqual(scrape.categorize(r), "🔧 Developer Utilities")

    def test_anydoc_converter(self):
        r = row("firecrawl/anydoc", "Rust",
                "Convert Word, PowerPoint, Excel, OpenDocument, RTF, EPUB, CSV, and PDF to clean Markdown.", "")
        self.assertEqual(scrape.categorize(r), "🔧 Developer Utilities")

    def test_flyenv(self):
        r = row("xpf0000/FlyEnv", "TypeScript",
                "Native local development environment for Windows, macOS & Linux. A modern alternative to XAMPP",
                "dev-environment, development-environment, local-development, docker-alternative")
        self.assertEqual(scrape.categorize(r), "🔧 Developer Utilities")

    # --- Messaging ---
    def test_whatsapp_api(self):
        r = row("aldinokemal/go-whatsapp-web-multidevice", "Go",
                "WhatsApp REST API with support for UI, Multi Account, Webhooks",
                "whatsapp, rest-api, bot, golang-whatsapp")
        self.assertEqual(scrape.categorize(r), "💬 Messaging")

    # --- Own Projects / fallback ---
    def test_own_project(self):
        r = row("budi-imam-prasetyo/one-satu", "TypeScript", "—", "")
        self.assertEqual(scrape.categorize(r), "🔧 Own Projects")

    def test_zero_signal_fallback(self):
        # no override, no signals → catch-all
        r = row("unknown/nothing-here", "", "", "")
        self.assertEqual(scrape.categorize(r), "🎮 Fun & Creative")


if __name__ == "__main__":
    unittest.main()