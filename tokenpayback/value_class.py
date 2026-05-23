"""Second classification axis — Activity-Based Management's VA / NVA / BVA.

Borrowed from Cooper & Kaplan (1991) and the FinOps Foundation's 2025 AI working
group paper. Every session falls into one of three economic buckets:

  VA  (Value-Added)            — produced something the user would pay for if itemized:
                                 shipped code, fixed bug, answered a question, made a
                                 decision, drafted a usable artifact.
  NVA (Non-Value-Added)        — burned tokens with no usable output: retry loops,
                                 hallucinated answers later thrown away, repaired
                                 mistakes the agent itself introduced. Pure waste.
  BVA (Business-Value-Added)   — required overhead that didn't directly ship anything
                                 but was necessary: reading docs, exploring options,
                                 setting up context. Investment, not waste.

The LLM classifier *should* return value_class directly. This module derives it from
existing fields as a back-compat fallback so old sessions don't need re-classification.

Heuristic table (ordered priority):

  1. explicit classification["value_class"] if present
  2. replacement_quality:
        full-replacement → VA   (output was directly usable)
        with-edits       → VA   (mostly right, light touch-up)
        draft-only       → BVA  (starting point, real work still required)
        failed           → NVA  (cost burned, no progress)
        harmful          → NVA  (worse — created cleanup work)
  3. value_signal:
        shipped-code     → VA
        shipped-artifact → VA
        decided          → VA
        answered         → VA
        info-gathered    → BVA
        no-progress      → NVA
  4. category id substring fallback:
        contains "ship", "fix", "bug", "deploy", "answered"  → VA
        contains "research", "explore", "ideas", "investig"  → BVA
        else                                                  → BVA

Caveats: this is a 1-bit heuristic on a continuous reality. "draft-only" maps to BVA
because the user did the real work — the AI provided scaffolding. If you disagree
with the call for a specific session, edit ~/.tokenpayback/sessions.json directly.
"""
from __future__ import annotations

VA = "VA"
NVA = "NVA"
BVA = "BVA"

ALL_CLASSES = (VA, NVA, BVA)


# Quality → value_class
_QUALITY_MAP = {
    "full-replacement": VA,
    "with-edits": VA,
    "draft-only": BVA,
    "failed": NVA,
    "harmful": NVA,
}

# value_signal → value_class
_SIGNAL_MAP = {
    "shipped-code": VA,
    "shipped-artifact": VA,
    "decided": VA,
    "answered": VA,
    "info-gathered": BVA,
    "no-progress": NVA,
}

# Category-id keyword fallbacks
_VA_KEYWORDS = ("ship", "fix", "bug", "deploy", "answer", "life", "build", "send")
_BVA_KEYWORDS = ("research", "explore", "idea", "investig", "lookup", "scan",
                 "brainstorm", "strategy", "discover")


def derive_value_class(classification: dict | None) -> str:
    """Map an existing classification dict to a VA/NVA/BVA label.

    Always returns one of VA, NVA, BVA. Never raises.
    """
    if not classification:
        return BVA

    # 1. Honor explicit value_class if the LLM (or user) supplied one.
    explicit = (classification.get("value_class") or "").strip().upper()
    if explicit in ALL_CLASSES:
        return explicit

    # 2. replacement_quality is the most reliable existing signal.
    q = classification.get("replacement_quality")
    if q in _QUALITY_MAP:
        return _QUALITY_MAP[q]

    # 3. value_signal next.
    sig = classification.get("value_signal")
    if sig in _SIGNAL_MAP:
        return _SIGNAL_MAP[sig]

    # 4. Last resort: keyword-match the category id.
    cat = (classification.get("category") or "").lower()
    if any(k in cat for k in _VA_KEYWORDS):
        return VA
    if any(k in cat for k in _BVA_KEYWORDS):
        return BVA
    return BVA  # safest default — counts as overhead, not waste


def session_value_class(session: dict) -> str:
    """Convenience: pull classification out of a session and derive."""
    return derive_value_class(session.get("classification"))


def is_internal_failure(session: dict) -> bool:
    """ABM-style Internal Failure: the cost was burned but no usable output.

    Per Juran's PAF model: failure caught before customer (here: before commit /
    before shipping). Maps to replacement_quality in (failed, harmful).
    """
    q = (session.get("classification") or {}).get("replacement_quality")
    return q in ("failed", "harmful")
