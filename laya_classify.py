"""laya_classify v1.0.0 — Laya-based re-sorting pass over all repos.

Runs a second, semantic classification over every starred repository using
the laya decision engine (https://github.com/NandhaKishorM/laya): one
`choice` question per repo in a single forward pass, batched through
Router.predict_batch.

Design (agreed plan):
  * rules engine (engine.py) stays the backbone; Laya runs over ALL repos
  * the final category = Laya's answer when its confidence >= threshold,
    otherwise the rules result (ties stay deterministic and auditable)
  * hard decisions survive Laya: own projects (owner namespace) and
    REPO_OVERRIDES always keep engine.py's answer
  * any failure (laya not installed, checkpoint download, inference
    error) degrades gracefully to the rules result — the pipeline never
    breaks because of Laya
  * this module is only imported when scrape.py runs with --laya / USE_LAYA

Every public function is dependency-free to *import*; `laya` is imported
lazily inside _load_router() so tests (and the stdlib-only pipeline) run
without torch installed.

Public API:
  build_state(row)                     -> single state string
  laya_questions()                     -> typed question spec (choice of 14)
  classify_all(rows, min_confidence, router=None)
                                       -> {repo: decision dict}
"""

import os
import sys

import engine

__version__ = "1.0.0"

# English checkpoint: descriptions/topics of starred repos are English and
# ModernBERT-large scores highest on English inputs.  Pinned per request
# (model="english"), so the multilingual checkpoint is never downloaded.
LAYA_REPO = "convaiinnovations/laya"
LAYA_MODEL = "english"
QUESTION_ID = "category"

# Confidence above which Laya's answer wins over the rules result.
DEFAULT_MIN_CONFIDENCE = float(os.environ.get("LAYA_MIN_CONFIDENCE", "0.55"))

# Laya's option budget (head_max_len default 192) means each criterion must
# stay SHORT — engine.CATEGORY_DEFS definitions are far too long to describe
# 14 options in one choice question.  These one-line criteria mirror the
# category definitions instead; keep total size modest when editing.
_MAX_CRITERIA_WORDS = 14

LAYA_CRITERIA = {
    engine.AI: "AI agents, coding assistants, agent infrastructure or skills",
    engine.ML: "machine learning apps, models, local LLM clients, generative AI",
    engine.DESIGN: "design systems, UI components, icons, diagramming, figma",
    engine.MOBILE: "Android or iOS end-user mobile apps",
    engine.TERMINAL: "terminal emulators, TUI apps, CLI tools, neovim or shell",
    engine.DESKTOP: "desktop GUI applications, electron or tauri apps",
    engine.MEDIA: "music or video players, streaming clients, downloaders",
    engine.WEB: "web frameworks, backend servers, JS runtimes, CMS",
    engine.SELFHOST: "self-hosted servers, VPN or cloud storage, privacy tools",
    engine.LISTS: "curated lists, awesome lists, tutorials, resource collections",
    engine.SECURITY: "pentest frameworks, vulnerability scanners, reverse engineering",
    engine.DEVUTILS: "developer productivity tools, converters, scrapers, dashboards",
    engine.MESSAGING: "WhatsApp, Telegram or chat clients, bots, messaging APIs",
    engine.FUN: "games, creative art, fun demos, playful simulators",
}

# Laya never sees the OWN category: owner-namespace membership is metadata,
# not semantics; engine.py decides it and the decision is hard.


def build_state(row):
    """One state per repo: name + language + description + topics.

    Short enough that even the 512-token English checkpoint reads the whole
    state plus the option texts without truncation.
    """
    repo = row.get("repo") or ""
    name = repo.split("/")[-1] if "/" in repo else repo
    fields = [f"repository name: {name}"]
    lang = (row.get("language") or "").strip()
    if lang:
        fields.append(f"language: {lang}")
    desc = (row.get("description") or "").strip()
    if desc:
        fields.append(f"description: {desc}")
    topics = (row.get("topics") or "").strip()
    if topics:
        fields.append(f"topics: {topics}")
    return "\n".join(fields)


def laya_questions():
    """The single choice question Laya answers for every repo."""
    return {
        QUESTION_ID: {
            "type": "choice",
            "instructions": (
                "Which single category describes what this repository is "
                "primarily FOR (its purpose, not its technology stack)?"
            ),
            "criteria": dict(LAYA_CRITERIA),
        }
    }


def _load_router():
    """Import laya and build an English-only Router.  Raises on any failure."""
    from laya import Router

    kwargs = {"models": {LAYA_MODEL: LAYA_REPO}}
    device = os.environ.get("LAYA_DEVICE")  # LAYA_DEVICE=cpu pins CPU in CI
    if device:
        kwargs["device"] = device
    return Router(**kwargs)


def _ask_batch(router, rows):
    """Run one predict_batch over all rows.  Returns list aligned with rows.

    Each entry is (choice_label or None, confidence); None means the answer
    was missing/malformed and the rules result should survive.
    """
    requests = [
        {"state": build_state(r), "questions": laya_questions(),
         "model": LAYA_MODEL}
        for r in rows
    ]
    results = router.predict_batch(requests, sort_by_length=True)
    out = []
    for res in results:
        ans = (res.get("answers") or {}).get(QUESTION_ID) or {}
        label = ans.get("choice")
        if label not in LAYA_CRITERIA:
            label = None
        try:
            conf = float(ans.get("confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        out.append((label, conf))
    return out


def classify_all(rows, min_confidence=None, router=None):
    """Re-sort all repos via Laya.  Returns {repo: decision dict}.

    Decision policy per repo:
      1. rules == Own Projects       -> rules wins (hard decision)
      2. Laya unavailable/failed     -> rules wins (source 'rules-fallback')
      3. Laya label outside criteria -> rules wins (source 'rules-invalid')
      4. confidence >= min_confidence-> Laya's label (source 'laya')
      5. otherwise                   -> rules wins (source 'rules-low-conf')

    Returns {} when Laya could not run at all (not installed, no network),
    in which case the caller keeps rules-only behaviour.  Decision dicts:

        final        category that generate_readme should use
        rules        engine.py's own classification
        laya         Laya's raw choice (None when unavailable)
        confidence   Laya's confidence for that choice
        source       which policy arm decided 'final'
    """
    if min_confidence is None:
        min_confidence = DEFAULT_MIN_CONFIDENCE
    if not rows:
        return {}

    if router is None:
        try:
            router = _load_router()
        except Exception as e:  # ImportError, download failure, OOM, ...
            print(f"  laya unavailable — keeping rules-only categories: {e}",
                  file=sys.stderr)
            return {}

    try:
        answers = _ask_batch(router, rows)
    except Exception as e:
        print(f"  laya inference failed — keeping rules-only categories: {e}",
              file=sys.stderr)
        return {}

    out = {}
    for row, (label, conf) in zip(rows, answers):
        repo = (row.get("repo") or "").strip()
        rules_cat, _ev = engine.classify(row)
        if rules_cat == engine.OWN:
            source = "rules-own"
        elif label is None:
            source = "rules-fallback"
        elif conf >= min_confidence:
            source = "laya"
        else:
            source = "rules-low-conf"
        final = label if source == "laya" else rules_cat
        out[repo] = {
            "final": final,
            "rules": rules_cat,
            "laya": label,
            "confidence": conf,
            "source": source,
        }
    return out


def audit_lines(decisions):
    """Human-readable per-repo summary for the CI log."""
    lines = []
    for repo, d in decisions.items():
        mark = "" if d["source"] == "laya" else "  (rules kept)"
        lines.append(
            f"  {repo}: {d['final']}{mark} — laya={d['laya']} "
            f"conf={d['confidence']:.2f}")
    return lines


def summarize(decisions):
    """(changed, counts-by-source) for the log line scrape.py prints."""
    counts = {}
    changed = 0
    for d in decisions.values():
        counts[d["source"]] = counts.get(d["source"], 0) + 1
        if d["source"] == "laya" and d["final"] != d["rules"]:
            changed += 1
    return changed, counts
