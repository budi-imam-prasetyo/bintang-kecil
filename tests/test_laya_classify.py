"""Tests for laya_classify.py — Laya re-sorting pass over all repos.

All tests use a FakeRouter: no torch, no laya, no model download, so the
suite stays stdlib-only and CI-cheap (untargeted by the plan: real inference
is verified on GitHub Actions, never on a laptop).

Run: python3 -m unittest discover tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import engine  # noqa: E402
import laya_classify as lc  # noqa: E402


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

def row(repo, lang="", desc="", topics=""):
    return {"repo": repo, "language": lang, "description": desc,
            "topics": topics}


class FakeRouter:
    """Replays a canned (choice, confidence) per repository name.

    Records every (request, kwargs) pair so tests can assert the state
    format, the pinned model and the question spec Laya actually receives.
    """

    def __init__(self, answers):
        # answers: {repo_last_name: (label, confidence)}
        self.answers = answers
        self.calls = []

    def predict_batch(self, requests, **kwargs):
        self.calls.append((requests, kwargs))
        results = []
        for req in requests:
            name = req["state"].split("repository name: ", 1)[1] \
                .split("\n", 1)[0]
            label, conf = self.answers.get(name, (None, 0.0))
            results.append({
                "answers": {lc.QUESTION_ID: {"choice": label,
                                             "confidence": conf}},
            })
        return results


class BoomRouter(FakeRouter):
    def predict_batch(self, requests, **kwargs):
        raise RuntimeError("checkpoint inference exploded")


# ---------------------------------------------------------------------------
# Question spec / state builder
# ---------------------------------------------------------------------------

class TestSpec(unittest.TestCase):
    def test_state_includes_name_lang_desc_topics(self):
        r = row("owner/some-tool", "Go", "A CLI that sorts things",
                "cli, sorting")
        s = lc.build_state(r)
        self.assertIn("repository name: some-tool", s)
        self.assertIn("language: Go", s)
        self.assertIn("description: A CLI that sorts things", s)
        self.assertIn("topics: cli, sorting", s)

    def test_state_skips_empty_fields(self):
        s = lc.build_state(row("owner/bare", "", "", ""))
        self.assertEqual("repository name: bare", s)

    def test_questions_are_a_choice_of_14_real_categories(self):
        qs = lc.laya_questions()
        q = qs[lc.QUESTION_ID]
        self.assertEqual(q["type"], "choice")
        self.assertEqual(set(q["criteria"]),
                         set(engine.CATEGORIES) - {engine.OWN})
        # option-budget guard: every criterion must stay short so 14 labels
        # fit inside laya's default head budget
        for crit in q["criteria"].values():
            self.assertLessEqual(len(crit.split()), lc._MAX_CRITERIA_WORDS)


# ---------------------------------------------------------------------------
# Decision policy
# ---------------------------------------------------------------------------

class TestDecisionPolicy(unittest.TestCase):
    def _run(self, answers, min_confidence=0.55):
        router = FakeRouter(answers)
        rows = [row("DesignKit/design-ui", "TypeScript",
                    "design system with icons", "design-system, icons")]
        out = lc.classify_all(rows, min_confidence=min_confidence,
                              router=router)
        return rows[0], out["DesignKit/design-ui"], router

    def test_high_confidence_laya_wins(self):
        _row, d, _r = self._run({"design-ui": (engine.DESIGN, 0.90)}, 0.55)
        self.assertEqual(d["final"], engine.DESIGN)
        self.assertEqual(d["source"], "laya")
        self.assertAlmostEqual(d["confidence"], 0.90)

    def test_low_confidence_keeps_rules(self):
        _row, d, _r = self._run({"design-ui": (engine.DESIGN, 0.30)}, 0.55)
        self.assertEqual(d["source"], "rules-low-conf")
        self.assertEqual(d["final"], d["rules"])
        # rules sees "design system" -> DESIGN; whatever it is, final==rules
        self.assertTrue(d["final"])

    def test_invalid_laya_label_falls_back_to_rules(self):
        _row, d, _r = self._run({"design-ui": ("Not A Category", 0.99)})
        self.assertEqual(d["source"], "rules-fallback")
        self.assertEqual(d["laya"], None)

    def test_own_repo_is_a_hard_decision(self):
        router = FakeRouter({"my-tool": (engine.FUN, 0.99)})
        rows = [row("budi-imam-prasetyo/my-tool", "Python", "a tool", "")]
        out = lc.classify_all(rows, router=router)
        d = out["budi-imam-prasetyo/my-tool"]
        self.assertEqual(d["final"], engine.OWN)
        self.assertEqual(d["source"], "rules-own")
        self.assertEqual(d["rules"], engine.OWN)

    def test_batch_requests_pin_model_and_share_spec(self):
        _row, _d, router = self._run({"design-ui": (engine.DESIGN, 0.9)})
        requests, kwargs = router.calls[0]
        self.assertEqual(len(requests), 1)
        req = requests[0]
        self.assertEqual(req["model"], lc.LAYA_MODEL)
        self.assertEqual(req["questions"], lc.laya_questions())
        self.assertEqual(kwargs.get("sort_by_length"), True)


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------

class TestDegradation(unittest.TestCase):
    def test_router_load_failure_returns_empty_map(self):
        original = lc._load_router

        def broken():
            raise ImportError("No module named 'laya'")

        lc._load_router = broken
        try:
            out = lc.classify_all([row("a/b", "", "desc", "")])
        finally:
            lc._load_router = original
        self.assertEqual(out, {})

    def test_inference_failure_returns_empty_map(self):
        router = BoomRouter({})
        out = lc.classify_all([row("a/b", "", "desc", "")], router=router)
        self.assertEqual(out, {})

    def test_empty_rows_returns_empty_map(self):
        self.assertEqual(lc.classify_all([], router=FakeRouter({})), {})


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------

class TestSummaries(unittest.TestCase):
    def test_summarize_counts_sources_and_changes(self):
        decisions = {
            "a/x": {"final": engine.ML, "rules": engine.TERMINAL,
                    "laya": engine.ML, "confidence": 0.9, "source": "laya"},
            "a/y": {"final": engine.MEDIA, "rules": engine.MEDIA,
                    "laya": engine.MEDIA, "confidence": 0.6,
                    "source": "laya"},
            "a/z": {"final": engine.ML, "rules": engine.ML,
                    "laya": engine.ML, "confidence": 0.2,
                    "source": "rules-low-conf"},
        }
        changed, counts = lc.summarize(decisions)
        self.assertEqual(changed, 1)  # only a/x moved category
        self.assertEqual(counts, {"laya": 2, "rules-low-conf": 1})


if __name__ == "__main__":
    unittest.main()
