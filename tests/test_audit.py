"""Regression tests for the audit/decision pipeline (engine.py + scrape.py).

Locks down the behaviors required by the audit spec:
  * classify() and audit() share one decision pipeline (_decide)
  * compound matching is boundary-safe (no raw substring)
  * 'learning' alone never forces Curated Lists (machine learning stays ML)
  * OWN / overrides produce honest audit metadata
  * repo identifier lookups are case/whitespace insensitive

Run: python3 -m pytest tests/ -v   (or python3 -m unittest discover tests)
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import engine  # noqa: E402


def _patch_dir(module, path):
    """Swap module.DIR to a temp dir; returns a restore callable (run in
    tearDown via addCleanup) so scrape's DIR is never left pointing at a
    deleted temp dir."""
    old = getattr(module, "DIR", None)
    module.DIR = path
    return lambda: (setattr(module, "DIR", old) if old is not None
                    else delattr(module, "DIR"))


def row(repo, lang="", desc="", topics=""):
    return {"repo": repo, "language": lang, "description": desc, "topics": topics}


def cat(r):
    return engine.classify(r)[0]


# ---------------------------------------------------------------------------
# 1-2: OWN + explicit overrides (classify AND audit consistency)
# ---------------------------------------------------------------------------

class TestOwnAndOverrides(unittest.TestCase):
    def test_own_project(self):
        assert cat(row("budi-imam-prasetyo/one-satu", "TypeScript")) == engine.OWN

    def test_own_project_audit_metadata(self):
        a = engine.audit([row("budi-imam-prasetyo/one-satu", "TypeScript")])[0]
        assert a["predicted"] == engine.OWN
        assert a["decision_source"] == "own"
        assert a["confidence"] == 1.0
        # hard decision: no misleading scorer numbers
        assert a["best_score"] == 0
        assert a["runner_up"] is None
        assert a["margin"] == 0
        assert not a["ambiguous"]

    def test_explicit_override(self):
        assert cat(row("sipeed/picoclaw", "Go",
                       "Tiny, Fast, and Deployable anywhere")) == engine.AI

    def test_explicit_override_audit_metadata(self):
        a = engine.audit([row("sipeed/picoclaw", "Go",
                              "Tiny, Fast, and Deployable anywhere")])[0]
        assert a["predicted"] == engine.AI
        assert a["decision_source"] == "override"
        assert a["confidence"] == 1.0
        assert a["best_score"] == 0
        assert any(e.startswith("override:") for e in a["evidence"])

    def test_override_lookup_case_and_whitespace(self):
        # P2-11: repo identifiers are normalized (case + whitespace)
        assert cat(row("SIPEED/PICOCLAW", "Go", "anything")) == engine.AI
        assert cat(row("  sipeed/picoclaw  ", "Go", "anything")) == engine.AI
        assert cat(row("Budi-Imam-Prasetyo/One-Satu")) == engine.OWN

    def test_rules_decision_source(self):
        a = engine.audit([row("zellij-org/zellij", "Rust",
                              "A terminal workspace with batteries included",
                              "multiplexer, terminal, workspace")])[0]
        assert a["decision_source"] == "rules"


# ---------------------------------------------------------------------------
# 3, 12: weak / no signal -> Uncategorized
# ---------------------------------------------------------------------------

class TestWeakEvidence(unittest.TestCase):
    def test_unknown_weak_evidence_is_uncategorized(self):
        assert cat(row("unknown/some-thing", "Rust",
                       "just a weird experiment", "rust")) == engine.UNCATEGORIZED

    def test_no_signal_is_uncategorized(self):
        assert cat(row("unknown/nothing-here")) == engine.UNCATEGORIZED

    def test_weak_evidence_audit_refuses(self):
        a = engine.audit([row("unknown/some-thing", "Rust",
                              "just a weird experiment", "rust")])[0]
        assert a["predicted"] == engine.UNCATEGORIZED
        assert "refusing to guess" in " ".join(a["evidence"])


# ---------------------------------------------------------------------------
# 4-5: machine learning model vs tutorial (learning-signal redesign)
# ---------------------------------------------------------------------------

class TestLearningVsML(unittest.TestCase):
    def test_ml_model_is_ai_ml(self):
        r = row("x/ml-model", "Python", "Machine learning model",
                "machine-learning")
        assert cat(r) == engine.ML

    def test_ml_model_topic_only_is_ai_ml(self):
        r = row("x/ml-model", "Python", "Trains neural networks", "")
        assert cat(r) == engine.ML

    def test_ml_tutorial_is_lists(self):
        r = row("x/ml-tutorial", "", "Machine learning tutorial", "")
        assert cat(r) == engine.LISTS

    def test_course_for_beginners_is_lists(self):
        r = row("x/course", "", "Course for beginners", "")
        assert cat(r) == engine.LISTS

    def test_bare_learning_word_is_not_lists_evidence(self):
        # negative test: 'learning' inside an unrelated ML description must
        # never make Lists a CANDIDATE.  Redesign per spec P0-3: bare
        # 'learning' fires as weak support (score 2, visible in score_details
        # for honesty) but 2 < MIN_SCORE (3), so it is filtered out of the
        # decision pipeline — LISTS never appears in ranked candidates.
        r = row("x/deep-ml", "Python", "Deep learning inference engine",
                "deep-learning")
        details = engine.score_details(r)
        # weak support may appear in raw scoring...
        if engine.LISTS in details:
            assert details[engine.LISTS][0] < engine.MIN_SCORE
        # ...but never survives to a real candidate
        dec = engine._decide(r)
        assert all(c != engine.LISTS for c, _s in dec["ranked"])
        assert cat(r) == engine.ML

    def test_lessons_and_quizzes_stay_lists(self):
        r = row("x/ml-course", "Jupyter Notebook",
                "12 weeks, 26 lessons, 52 quizzes, classic Machine Learning",
                "education, lessons, quizzes")
        assert cat(r) == engine.LISTS


# ---------------------------------------------------------------------------
# 6-11: conflict resolution pins (purpose > interface/apptype)
# ---------------------------------------------------------------------------

class TestConflicts(unittest.TestCase):
    def test_music_player_for_android_is_mobile(self):
        r = row("x/tune", "Kotlin", "A music player app for Android",
                "android, music-player, kotlin")
        assert cat(r) == engine.MOBILE

    def test_security_scanner_for_android_is_security(self):
        r = row("x/sec-app", "Kotlin", "security scanner app for Android",
                "android, security, mobile-security")
        assert cat(r) == engine.SECURITY

    def test_terminal_telegram_client_is_messaging(self):
        r = row("x/tg-cli", "Rust", "Telegram client for the terminal",
                "telegram, cli, terminal, tui")
        assert cat(r) == engine.MESSAGING

    def test_cli_security_conflict(self):
        r = row("x/scan", "Go", "port scanner for pentesting",
                "security, cli, penetration-testing, nmap")
        assert cat(r) == engine.SECURITY

    def test_desktop_whatsapp_client_is_messaging(self):
        r = row("x/wa-desktop", "TS", "WhatsApp desktop client",
                "whatsapp, electron, desktop")
        assert cat(r) == engine.MESSAGING

    def test_curated_list_of_other_domain_stays_lists(self):
        r = row("x/awesome-android", "", "A curated list of Android libraries",
                "awesome, android, list")
        assert cat(r) == engine.LISTS

    def test_awesome_design_is_lists_not_design(self):
        r = row("VoltAgent/awesome-design-md", "",
                "A collection of DESIGN.md files analysis by popular brand "
                "design systems.",
                "design, design-md, design-system, design-tokens, figma")
        assert cat(r) == engine.LISTS


# ---------------------------------------------------------------------------
# 13: ambiguity handling
# ---------------------------------------------------------------------------

class TestAmbiguity(unittest.TestCase):
    def test_ambiguous_candidate_flagged(self):
        # Two real PURPOSE categories with close scores and no precedence
        # between them -> ambiguous flag + evidence note.  (An interface-vs-
        # purpose pair like media-vs-terminal is NOT ambiguous after
        # precedence drops the interface candidate.)
        r = row("x/fun-music", "JavaScript", "make music in the browser, a fun toy",
                "music, web-audio, fun")
        c, ev = engine.classify(r)
        assert c == engine.MEDIA
        a = engine.audit([r])[0]
        assert a["ambiguous"] is True
        assert any("ambiguous" in e for e in a["evidence"])
        assert 0 <= a["margin"] <= 2

    def test_interface_precedence_not_ambiguous(self):
        # Terminal (interface) loses to Media (purpose) via precedence; the
        # decision is clear-cut, so the post-precedence margin is honest and
        # the result must NOT be flagged ambiguous.
        r = row("x/term-music", "Rust", "play music in your terminal",
                "music-player, cli, terminal")
        c, ev = engine.classify(r)
        assert c == engine.MEDIA
        a = engine.audit([r])[0]
        assert a["ambiguous"] is False
        # ranked list survived precedence: interface candidate is gone
        assert all(cat != engine.TERMINAL for cat, _s in a["ranked"])

    def test_clear_winner_not_ambiguous(self):
        r = row("zellij-org/zellij", "Rust",
                "A terminal workspace with batteries included",
                "multiplexer, terminal, workspace")
        a = engine.audit([r])[0]
        assert a["ambiguous"] is False
        assert a["margin"] > 2


# ---------------------------------------------------------------------------
# 14: compound matcher boundary safety (P0-2)
# ---------------------------------------------------------------------------

class TestCompoundBoundarySafety(unittest.TestCase):
    def test_no_raw_substring_app(self):
        # 'app' must not fire via 'application'-bearing unrelated words like
        # 'happy'/'apple'; compound needs a real app token
        f = engine._features(row("x/happy", "", "A happy little apple picker",
                                 "kotlin"))
        assert not engine._has_compound(f, engine.COMPOUNDS["mobile_app"])

    def test_no_raw_substring_mac(self):
        # 'mac' must not match inside 'machine': with a desc whose only
        # gui_app-ish word is 'machine' (and no real app/desktop/client
        # token), the compound must NOT fire despite the electron topic.
        f = engine._features(row("x/ml-thing", "",
                                 "Machine learning model trainer",
                                 "electron"))
        assert not engine._has_compound(f, engine.COMPOUNDS["gui_app"])
        # ...while an exact 'desktop' token legitimately fires it
        f2 = engine._features(row("x/ml-desktop", "",
                                  "Machine learning desktop widget",
                                  "electron"))
        assert engine._has_compound(f2, engine.COMPOUNDS["gui_app"])

    def test_no_raw_substring_tool(self):
        # 'tool' must not match inside 'toolkit' for gui_app compound
        f = engine._features(row("x/toolkit", "", "A GUI analysis toolkit",
                                 "tauri"))
        # 'toolkit' alone in desc_any? gui_app has no 'tool' — verify no hit
        assert not engine._has_compound(f, engine.COMPOUNDS["gui_app"])

    def test_compound_fires_on_exact_tokens(self):
        f = engine._features(row("x/notes", "TS",
                                 "Sticky notes desktop application",
                                 "electron"))
        assert engine._has_compound(f, engine.COMPOUNDS["gui_app"])

    def test_scrape_heavy_requires_real_scraping_words(self):
        # 'scrap' substring must NOT match 'scrapbook'
        f = engine._features(row("x/scrapbook", "",
                                 "A digital scrapbook for memories",
                                 "web-scraping, crawler, crawling, scraper"))
        assert not engine._has_compound(f, engine.COMPOUNDS["scrape_heavy"])

    def test_agent_suffix_strict_semantics(self):
        # P1-5: '-agent' is a strict NAME suffix
        assert cat(row("PrimeIntellect-ai/prime-agent", "TypeScript",
                       "A self-improving RLM agent for coding workflows and "
                       "long-running autonomous tasks.")) == engine.AI
        # 'agent-extra' does NOT end with '-agent' -> no suffix evidence
        f = engine._features(row("x/agent-extra", "", "", ""))
        assert not engine._match_name(f, engine.LEXICON["agent_suffix"])
        # unrelated name containing 'agent' mid-word gets nothing
        f2 = engine._features(row("x/agentsmith", "", "", ""))
        assert not engine._match_name(f2, engine.LEXICON["agent_suffix"])


# ---------------------------------------------------------------------------
# 15: classify() == audit() on the same decision pipeline
# ---------------------------------------------------------------------------

class TestClassifyAuditConsistency(unittest.TestCase):
    def test_audit_matches_classify_synthetic(self):
        cases = [
            row("zellij-org/zellij", "Rust",
                "A terminal workspace with batteries included",
                "multiplexer, terminal, workspace"),
            row("karem505/whatRust", "Rust",
                "whatRust — a lightweight WhatsApp Web desktop client",
                "whatsapp, tauri, desktop-app"),
            row("x/unknown", "", "", ""),
            row("budi-imam-prasetyo/x", "TS", "", ""),
        ]
        for r in cases:
            a = engine.audit([r])[0]
            assert a["predicted"] == engine.classify(r)[0]

    def test_audit_matches_classify_real_dataset(self):
        data = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "budi-stars.json")
        if not os.path.exists(data):
            raise unittest.SkipTest("budi-stars.json not available")
        rows = json.load(open(data))
        for a in engine.audit(rows):
            r = next(x for x in rows if x.get("repo") == a["repo"])
            assert a["predicted"] == engine.classify(r)[0], a["repo"]

    def test_audit_predicted_uses_final_decision_not_raw_scorer(self):
        # security scanner for Android: raw Mobile score is HIGHEST, but the
        # final decision is Security — audit must report Security numbers.
        r = row("x/sec-app", "Kotlin", "security scanner app for Android",
                "android, security, mobile-security")
        a = engine.audit([r])[0]
        assert a["predicted"] == engine.SECURITY
        assert a["best_score"] > 0
        # best_score must belong to the FINAL category's pipeline position
        ranked = dict(a["ranked"]) if a.get("ranked") else {}
        if ranked:
            assert a["best_score"] == ranked[
                [c for c, _s in a["ranked"]][0]]


# ---------------------------------------------------------------------------
# Negative tests: deliberate false-positive attempts
# ---------------------------------------------------------------------------

class TestNegativeCases(unittest.TestCase):
    def test_no_false_positives(self):
        # weak/generic phrases must never guess a category
        cases = [
            ("A fast web server for cats", ""),
            ("Personal blog about AI", ""),
            ("Maintain your hair with this app", ""),
            ("This tool helps you design", "design"),
            ("A library for book", ""),
            ("Framework for happiness", "framework"),
            ("Terminal velocity calculator", ""),
            ("Contains calcium", ""),
            ("Trained to remain available", ""),
        ]
        for desc, topics in cases:
            with self.subTest(desc=desc, topics=topics):
                self.assertEqual(
                    cat(row("x/probe", "", desc, topics)), engine.UNCATEGORIZED)

    def test_happy_apple_not_mobile(self):
        # 'app' substring inside 'happy'/'apple' must not fire the
        # mobile_app compound: no app-word compound, no mobile identity
        f = engine._features(row("x/orchard", "", "Happy apple orchard management",
                                 "kotlin, android"))
        assert not engine._has_compound(f, engine.COMPOUNDS["mobile_app"])
        assert cat(row("x/orchard", "", "Happy apple orchard management",
                       "")) == engine.UNCATEGORIZED


# ---------------------------------------------------------------------------
# scrape.py robustness (P2-8/9/10) — pure helpers, no network
# ---------------------------------------------------------------------------

class TestScrapeRobustness(unittest.TestCase):
    def _scrape(self):
        import scrape
        return scrape

    def test_save_csv_empty_rows(self):
        s = self._scrape()
        with tempfile.TemporaryDirectory() as td:
            self.addCleanup(_patch_dir(s, td))
            s.save_csv([])  # must not raise
            out = (Path(td) / "budi-stars.csv").read_text()
            assert out.strip().startswith("repo,")

    def test_save_json_and_csv_roundtrip(self):
        s = self._scrape()
        with tempfile.TemporaryDirectory() as td:
            self.addCleanup(_patch_dir(s, td))
            rows = [{"repo": "a/b", "url": "u", "stars": 1, "language": "Go",
                     "description": "d", "topics": "t", "created": "2026-01-01",
                     "forks": 0, "license": "MIT"}]
            s.save_json(rows)
            s.save_csv(rows)
            assert json.load(open(Path(td) / "budi-stars.json")) == rows

    def test_fetch_constants_bounded(self):
        s = self._scrape()
        assert s.MAX_ATTEMPTS >= 2 and s.MAX_ATTEMPTS <= 5
        assert s.HTTP_TIMEOUT > 0
        assert s.RETRY_BACKOFF > 0

    def test_detect_changes_repo_root_path(self):
        # P2-10: git show path is resolved from repo root, not cwd
        s = self._scrape()
        with tempfile.TemporaryDirectory() as td:
            self.addCleanup(_patch_dir(s, td))
            # no git repo here -> falls back to .bak file logic, must not crash
            rows = [{"repo": "a/b"}]
            assert s.detect_changes(rows) is True
            # second call with identical rows: .bak now matches -> unchanged
            assert s.detect_changes(rows) is False
