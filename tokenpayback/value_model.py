"""Per-category value model — backed by a user-specific taxonomy.

The taxonomy itself is generated/edited by the user (see `taxonomy.py`). This
module just looks up baselines for each category and aggregates sessions.

Old behavior (hardcoded 10 categories) is retained as a fallback when no
taxonomy is supplied.
"""
from __future__ import annotations


# Fallback (hardcoded) — used only when no taxonomy is passed.
FALLBACK_VALUES: dict[str, dict] = {
    "code-shipped":      {"label": "Code shipped",       "icon": "🚢", "baseline_usd": 60, "per_pr_usd": 600, "per_line_usd": 0.30},
    "bug-fixed":         {"label": "Bug fixed",          "icon": "🐛", "baseline_usd": 80, "per_pr_usd": 700, "per_line_usd": 0.40},
    "infra-changed":     {"label": "Infra changed",      "icon": "⚙️",  "baseline_usd": 50, "per_pr_usd": 200, "per_line_usd": 0.10},
    "info-gathered":     {"label": "Info gathered",      "icon": "📚", "baseline_usd": 25, "per_pr_usd": 0,   "per_line_usd": 0.05},
    "ideas-explored":    {"label": "Ideas explored",     "icon": "💡", "baseline_usd": 20, "per_pr_usd": 0,   "per_line_usd": 0},
    "life-shipped":      {"label": "Life shipped",       "icon": "🎯", "baseline_usd": 30, "per_pr_usd": 0,   "per_line_usd": 0.20},
    "question-answered": {"label": "Question answered",  "icon": "❓", "baseline_usd": 5,  "per_pr_usd": 0,   "per_line_usd": 0},
}


def _category_config(cat_id: str, taxonomy: dict | None) -> dict:
    if taxonomy:
        for c in taxonomy.get("categories") or []:
            if c.get("id") == cat_id:
                return c
    return FALLBACK_VALUES.get(cat_id) or FALLBACK_VALUES.get("question-answered")


def estimate_session_value(session: dict, taxonomy: dict | None = None,
                           github_signal: dict | None = None) -> dict:
    cat = (session.get("classification") or {}).get("category", "question-answered")
    cfg = _category_config(cat, taxonomy)
    value = float(cfg.get("baseline_usd", 0))
    breakdown = {"baseline_usd": cfg.get("baseline_usd", 0)}

    if github_signal:
        pr_v = float(cfg.get("per_pr_usd", 0))
        line_v = float(cfg.get("per_line_usd", 0))
        if github_signal.get("pr_merged") and pr_v > 0:
            value += pr_v
            breakdown["pr_value_usd"] = pr_v
            if github_signal.get("reverted"):
                value = max(0, value - pr_v)
                breakdown["revert_penalty_usd"] = -pr_v
        lines = github_signal.get("lines", 0)
        if lines > 0 and line_v > 0:
            lv = lines * line_v * 0.5
            value += lv
            breakdown["line_value_usd"] = round(lv, 2)

    tool_total = sum((session.get("tool_counts") or {}).values())
    if tool_total > 50:
        bump = min(50, tool_total * 0.5)
        value += bump
        breakdown["tool_intensity_usd"] = round(bump, 2)

    return {
        "value_usd": round(value, 2),
        "category": cat,
        "label": cfg.get("label", cat),
        "icon": cfg.get("icon", "•"),
        "breakdown": breakdown,
    }


def summarize_by_category(sessions: list[dict], taxonomy: dict | None = None) -> list[dict]:
    by_cat: dict[str, dict] = {}
    for s in sessions:
        cat = (s.get("classification") or {}).get("category", "question-answered")
        cost = float(s.get("est_cost_usd", 0))
        v = estimate_session_value(s, taxonomy)
        d = by_cat.setdefault(cat, {
            "category": cat,
            "label": v["label"],
            "icon": v["icon"],
            "count": 0,
            "cost_usd": 0,
            "value_usd": 0,
        })
        d["count"] += 1
        d["cost_usd"] += cost
        d["value_usd"] += v["value_usd"]
    for d in by_cat.values():
        d["cost_usd"] = round(d["cost_usd"], 2)
        d["value_usd"] = round(d["value_usd"], 2)
        d["roi"] = round(d["value_usd"] / d["cost_usd"], 2) if d["cost_usd"] > 0 else None
    return sorted(by_cat.values(), key=lambda x: x["cost_usd"], reverse=True)


def summarize_by_agent(sessions: list[dict], taxonomy: dict | None = None) -> list[dict]:
    by_agent: dict[str, dict] = {}
    for s in sessions:
        agent = s.get("agent", "unknown")
        cost = float(s.get("est_cost_usd", 0))
        v = estimate_session_value(s, taxonomy)
        d = by_agent.setdefault(agent, {"agent": agent, "count": 0, "cost_usd": 0, "value_usd": 0})
        d["count"] += 1
        d["cost_usd"] += cost
        d["value_usd"] += v["value_usd"]
    for d in by_agent.values():
        d["cost_usd"] = round(d["cost_usd"], 2)
        d["value_usd"] = round(d["value_usd"], 2)
        d["roi"] = round(d["value_usd"] / d["cost_usd"], 2) if d["cost_usd"] > 0 else None
    return sorted(by_agent.values(), key=lambda x: x["cost_usd"], reverse=True)
