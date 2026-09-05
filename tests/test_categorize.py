"""Regression tests for the category engine (engine.py).

Each case pins a real repo from the starred list to its intended category,
using the signals (description/topics/language) that actually come from
the GitHub API. Run: python3 -m unittest discover tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import engine  # noqa: E402


def row(repo, lang="", desc="", topics=""):
    return {"repo": repo, "language": lang, "description": desc, "topics": topics}


def cat(r):
    return engine.classify(r)[0]


class TestAIAgents(unittest.TestCase):
    def test_hermes_agent(self):
        r = row("NousResearch/hermes-agent", "Python",
                "The agent that grows with you",
                "ai, ai-agent, ai-agents, anthropic, claude, claude-code, codex, hermes, hermes-agent, llm, openai")
        self.assertEqual(cat(r), engine.AI)

    def test_opencode_coding_agent(self):
        r = row("anomalyco/opencode", "TypeScript", "The open source coding agent.", "")
        self.assertEqual(cat(r), engine.AI)

    def test_prime_agent_by_name(self):
        r = row("PrimeIntellect-ai/prime-agent", "TypeScript",
                "A self-improving RLM agent for coding workflows and long-running autonomous tasks.", "")
        self.assertEqual(cat(r), engine.AI)

    def test_uteke_agent_memory(self):
        r = row("codecoradev/uteke", "Rust",
                "The Brain for Your AI — Local-first memory engine for AI agents. Store, recall, and search memories",
                "agent-memory, ai, ai-agents, cli, embeddings, llm, local-first, mcp, mcp-server, memory, rag, vector-database")
        self.assertEqual(cat(r), engine.AI)

    def test_picoclaw_override(self):
        # misleading signals — explicit override
        r = row("sipeed/picoclaw", "Go",
                "Tiny, Fast, and Deployable anywhere — automate the mundane, unleash your creativity", "")
        self.assertEqual(cat(r), engine.AI)

    def test_ai_gateway_router(self):
        r = row("diegosouzapw/OmniRoute", "TypeScript",
                "Free MIT AI gateway: one endpoint, 352 providers",
                "ai-agents, ai-gateway, claude-code, codex, cursor, llm-gateway, mcp")
        self.assertEqual(cat(r), engine.AI)

    def test_ai_skill_for_coding_agents(self):
        # ui-ux-pro-max-skill: an AI skill (agent enhancement), not a design tool
        r = row("nextlevelbuilder/ui-ux-pro-max-skill", "Python",
                "An AI skill that provides design intelligence for building professional UI/UX across multiple platforms.",
                "ai-skills, antigravity, claude, claude-code, codex, copilot, cursor-ai, kiro, ui-design, uikit, windsurf-ai")
        self.assertEqual(cat(r), engine.AI)

    def test_herdr_agent_runtime(self):
        r = row("herdrdev/herdr", "Rust",
                "the runtime your coding agents live on",
                "agent, agent-orchestration, ai-agents, claude-code, coding-agents, terminal, terminal-multiplexer, workspace-manager")
        self.assertEqual(cat(r), engine.AI)


class TestAIML(unittest.TestCase):
    def test_jan_local_llm(self):
        r = row("janhq/jan", "TypeScript",
                "Jan is an open source alternative to ChatGPT that runs 100% offline on your computer",
                "chatgpt, local-ai, llm, offline")
        self.assertEqual(cat(r), engine.ML)

    def test_deepfake(self):
        r = row("hacksider/Deep-Live-Cam", "Python",
                "real time face swap and one-click video deepfake with only a single image",
                "deepfake, faceswap")
        self.assertEqual(cat(r), engine.ML)

    def test_agentic_browser(self):
        r = row("browseros-ai/BrowserOS", "TypeScript",
                "The open-source Agentic browser; alternative to ChatGPT Atlas",
                "agentic, browser, llm")
        self.assertEqual(cat(r), engine.ML)


class TestDesign(unittest.TestCase):
    def test_tldraw_canvas_sdk(self):
        r = row("tldraw/tldraw", "TypeScript",
                "Build infinite canvas apps in React with the tldraw SDK.",
                "canvas, sdk, whiteboard, collaboration")
        self.assertEqual(cat(r), engine.DESIGN)

    def test_design_tokens(self):
        r = row("dembrandt/dembrandt", "TypeScript",
                "Extract any website's design system into tokens in seconds",
                "design-system, design-tokens")
        self.assertEqual(cat(r), engine.DESIGN)

    def test_nativewind_tailwind(self):
        r = row("nativewind/nativewind", "TypeScript",
                "The utility-first workflow you love from Tailwind CSS in your React Native applications",
                "css, tailwind, tailwindcss, react-native")
        self.assertEqual(cat(r), engine.DESIGN)


class TestMobile(unittest.TestCase):
    def test_komikku_manga_reader(self):
        r = row("komikku-app/komikku", "Kotlin",
                "Free and open source manga reader for Android",
                "android, jetpack-compose, material-design")
        self.assertEqual(cat(r), engine.MOBILE)

    def test_android_vpn_adblock(self):
        r = row("pass-with-high-score/blockads-android", "Kotlin",
                "Block ads system-wide on Android using local VPN-based DNS filtering. No root needed.",
                "android, ad-blocker, vpn")
        self.assertEqual(cat(r), engine.MOBILE)

    def test_filepipe_android_storage(self):
        # android topic + app-shaped purpose, thin description
        r = row("bikram-agarwal/FilePipe", "Kotlin",
                "Turn messy Android storage into a rule-driven library: choose sources, filters, destinations",
                "android, app, filesystem, organization")
        self.assertEqual(cat(r), engine.MOBILE)


class TestTerminal(unittest.TestCase):
    def test_glances_system_monitor(self):
        r = row("nicolargo/glances", "Python",
                "Glances an Eye on your system. A top/htop alternative for GNU/Linux, BSD, macOS and Windows",
                "monitoring, python, system, terminal, web")
        self.assertEqual(cat(r), engine.TERMINAL)

    def test_sd_sed_alternative(self):
        r = row("chmln/sd", "Rust",
                "Intuitive find & replace CLI (sed alternative)",
                "cli, command-line, regex, rust, terminal, text-processing")
        self.assertEqual(cat(r), engine.TERMINAL)

    def test_zellij(self):
        r = row("zellij-org/zellij", "Rust",
                "A terminal workspace with batteries included",
                "multiplexer, terminal, workspace")
        self.assertEqual(cat(r), engine.TERMINAL)

    def test_ani_cli(self):
        r = row("pystardust/ani-cli", "Shell",
                "A cli tool to browse and play anime",
                "anime, cli, terminal, shell")
        self.assertEqual(cat(r), engine.TERMINAL)


class TestDesktop(unittest.TestCase):
    def test_pake(self):
        r = row("tw93/Pake", "Rust",
                "Turn any webpage into a desktop app with one command.",
                "desktop, tauri, macos, windows, linux")
        self.assertEqual(cat(r), engine.DESKTOP)

    def test_kudu_system_cleaner(self):
        r = row("AdventDevInc/kudu", "TypeScript",
                "Free Windows, Mac and Linux cleaner, scanner, and more.",
                "ccleaner-alternative, cleaner, system-cleaner, windows-cleaner, "
                "mac-cleaner, linux-cleaner, system-maintenance, pc-optimization")
        self.assertEqual(cat(r), engine.DESKTOP)

    def test_electrobun(self):
        r = row("blackboardsh/electrobun", "TypeScript",
                "Build ultra fast, tiny, and cross-platform desktop apps with Typescript.", "")
        self.assertEqual(cat(r), engine.DESKTOP)

    def test_wails(self):
        r = row("wailsapp/wails", "Go",
                "Create beautiful applications using Go",
                "desktop, gui, framework, golang")
        self.assertEqual(cat(r), engine.DESKTOP)


class TestMedia(unittest.TestCase):
    def test_moviebox_tui(self):
        # media purpose beats terminal interface
        r = row("mesamirh/MovieBox-Tui", "Rust",
                "Terminal interface to find, download, and stream movies, TV shows, and live TV",
                "anime, cli, downloader, iptv, moviebox, movies, mpv, series, streaming, terminal, tui, tv-shows")
        self.assertEqual(cat(r), engine.MEDIA)

    def test_sonora_music_player(self):
        # audit fix: native music streaming client is Media
        r = row("nolight132/sonora", "Rust",
                "A native music streaming client, built with Rust and GPUI",
                "gpui, music-player, spotify, streaming, youtube")
        self.assertEqual(cat(r), engine.MEDIA)

    def test_vidbee_downloader(self):
        r = row("nexmoe/VidBee", "TypeScript",
                "Download video and audio from YouTube, TikTok, Twitter",
                "downloader, youtube-downloader")
        self.assertEqual(cat(r), engine.MEDIA)


class TestSelfHosted(unittest.TestCase):
    def test_headscale(self):
        r = row("juanfont/headscale", "Go",
                "An open source, self-hosted implementation of the Tailscale control server",
                "wireguard, tailscale, server, control-server, vpn")
        self.assertEqual(cat(r), engine.SELFHOST)

    def test_telegram_drive(self):
        r = row("caamer20/Telegram-Drive", "TypeScript",
                "Turn your Telegram account into an unlimited, secure cloud storage drive.",
                "open-source, react, rust, tauri, telegram, typescript")
        self.assertEqual(cat(r), engine.SELFHOST)


class TestLists(unittest.TestCase):
    def test_awesome_go(self):
        r = row("avelino/awesome-go", "Go",
                "A curated list of awesome Go frameworks, libraries and software",
                "awesome, awesome-list, go")
        self.assertEqual(cat(r), engine.LISTS)

    def test_ml_for_beginners(self):
        r = row("microsoft/ML-For-Beginners", "Jupyter Notebook",
                "12 weeks, 26 lessons, 52 quizzes, classic Machine Learning for all",
                "education, beginners, lessons, quizzes")
        self.assertEqual(cat(r), engine.LISTS)

    def test_android_foss_is_a_list(self):
        # "A list of FOSS for Android" is a curated list, NOT a mobile app
        r = row("offa/android-foss", "Python",
                "A list of Free and Open Source Software (FOSS) for Android – saving Freedom and Privacy.",
                "android, android-apps, f-droid, foss, open-source")
        self.assertEqual(cat(r), engine.LISTS)

    def test_awesome_design_md_is_a_list(self):
        # awesome-<domain> IS a curated list even when domain == design
        r = row("VoltAgent/awesome-design-md", "",
                "A collection of DESIGN.md files analysis by popular brand design systems.",
                "design, design-md, design-system, design-tokens, figma")
        self.assertEqual(cat(r), engine.LISTS)


class TestSecurity(unittest.TestCase):
    def test_mobsf(self):
        r = row("MobSF/Mobile-Security-Framework-MobSF", "JavaScript",
                "Mobile Security Framework (MobSF) is an automated, all-in-one mobile application pen-testing framework",
                "mobile-security, android-security, static-analysis, owasp")
        self.assertEqual(cat(r), engine.SECURITY)

    def test_cybermes_redteam(self):
        r = row("Zyrexnn/Cybermes", "Python",
                "Autonomous Offensive Security, Bug Bounty & Red Teaming Agent Framework",
                "bug-bounty, devsecops, offensive-security, penetration-testing, red-teaming")
        self.assertEqual(cat(r), engine.SECURITY)

    def test_reverse_skill(self):
        r = row("zhaoxuya520/reverse-skill", "PowerShell",
                "Reverse Engineering / Authorized Penetration Testing / Security Research Skill Router Pack", "")
        self.assertEqual(cat(r), engine.SECURITY)


class TestWeb(unittest.TestCase):
    def test_strapi(self):
        r = row("strapi/strapi", "TypeScript",
                "Strapi is the leading open-source headless CMS.",
                "headless-cms, cms, nodejs")
        self.assertEqual(cat(r), engine.WEB)

    def test_pocketbase(self):
        r = row("pocketbase/pocketbase", "Go",
                "Open Source realtime backend in 1 file",
                "backend, realtime, authentication, golang")
        self.assertEqual(cat(r), engine.WEB)

    def test_bun_js_runtime(self):
        r = row("oven-sh/bun", "Zig",
                "Incredibly fast JavaScript runtime, bundler, test runner, and package manager – all in one",
                "bun, bundler, javascript, nodejs, npm, transpiler, typescript")
        self.assertEqual(cat(r), engine.WEB)

    def test_elysia_framework(self):
        r = row("elysiajs/elysia", "TypeScript",
                "Ergonomic Framework for Humans",
                "bun, framework, http, server, typescript, web")
        self.assertEqual(cat(r), engine.WEB)

    def test_laravel_forum_package(self):
        r = row("Team-Tea-Time/laravel-forum", "PHP",
                "A slim, lean forum package designed for quick and easy integration in Laravel projects",
                "forum, laravel, laravel-package, php")
        self.assertEqual(cat(r), engine.WEB)

    def test_laravel_brain_tooling(self):
        # Laravel ecosystem tooling stays in Web Frameworks & Backend
        r = row("laramint/laravel-brain", "PHP",
                "Visualize your Laravel request lifecycle as an interactive graph",
                "laravel, laravel-packages, php")
        self.assertEqual(cat(r), engine.WEB)


class TestDevUtils(unittest.TestCase):
    def test_scrapling_framework(self):
        r = row("D4Vinci/Scrapling", "Python",
                "An adaptive Web Scraping framework that handles everything from a single request to a full-scale crawl!",
                "ai-scraping, crawler, crawling, data-extraction, scraping, "
                "web-scraper, web-scraping, webscraping, playwright")
        self.assertEqual(cat(r), engine.DEVUTILS)

    def test_anydoc_converter(self):
        r = row("firecrawl/anydoc", "Rust",
                "Convert Word, PowerPoint, Excel, OpenDocument, RTF, EPUB, CSV, and PDF to clean Markdown.", "")
        self.assertEqual(cat(r), engine.DEVUTILS)

    def test_flyenv(self):
        r = row("xpf0000/FlyEnv", "TypeScript",
                "Native local development environment for Windows, macOS & Linux. A modern alternative to XAMPP",
                "dev-environment, development-environment, local-development, docker-alternative")
        self.assertEqual(cat(r), engine.DEVUTILS)


class TestMessaging(unittest.TestCase):
    def test_whatsapp_api(self):
        r = row("aldinokemal/go-whatsapp-web-multidevice", "Go",
                "WhatsApp REST API with support for UI, Multi Account, Webhooks",
                "whatsapp, rest-api, bot, golang-whatsapp")
        self.assertEqual(cat(r), engine.MESSAGING)

    def test_whatrust_desktop_client(self):
        # audit fix: a WhatsApp client belongs to Messaging (purpose > interface)
        r = row("karem505/whatRust", "Rust",
                "whatRust — a lightweight, open-source WhatsApp Web desktop client built with Rust + Tauri.",
                "cross-platform, desktop-app, tauri, whatsapp, whatsapp-client, whatsapp-desktop, whatsapp-web")
        self.assertEqual(cat(r), engine.MESSAGING)


class TestOwnAndFallback(unittest.TestCase):
    def test_own_project(self):
        r = row("budi-imam-prasetyo/one-satu", "TypeScript", "—", "")
        self.assertEqual(cat(r), engine.OWN)

    def test_zero_signal_is_uncategorized(self):
        # zero-signal repos are explicit, not silently "fun"
        r = row("unknown/nothing-here", "", "", "")
        self.assertEqual(cat(r), engine.UNCATEGORIZED)

    def test_weak_signal_falls_back_to_fun(self):
        # signals exist but score below threshold -> fun fallback
        r = row("unknown/some-thing", "Rust", "just a weird experiment", "rust")
        self.assertEqual(cat(r), engine.FUN)

    def test_waylandcraft_fallback(self):
        # real fun repo
        r = row("EVV1E/waylandcraft", "Java", "Wayland Compositor in Minecraft",
                "minecraft, wayland, wayland-compositor")
        self.assertEqual(cat(r), engine.FUN)


class TestExplainability(unittest.TestCase):
    def test_score_details_returns_evidence(self):
        r = row("zellij-org/zellij", "Rust",
                "A terminal workspace with batteries included",
                "multiplexer, terminal, workspace")
        det = engine.score_details(r)
        self.assertIn(engine.TERMINAL, det)
        score, ev = det[engine.TERMINAL]
        self.assertGreaterEqual(score, engine.MIN_SCORE)
        self.assertTrue(all(isinstance(e, str) for e in ev))

    def test_classify_returns_evidence_list(self):
        r = row("nolight132/sonora", "Rust",
                "A native music streaming client", "music-player, spotify, streaming")
        c, ev = engine.classify(r)
        self.assertEqual(c, engine.MEDIA)
        self.assertTrue(len(ev) > 0)


if __name__ == "__main__":
    unittest.main()
