"""Per-category value model.

Old model: only PRs merged count as value → research/brainstorm/chat-misc = $0.
That's wrong. Asking the agent a question and getting an answer IS value. Writing
a draft IS value. Sketching out an idea IS value.

New model: every category has its own value signal. None of them are "$0 wasted"
by default — they all produce *something*. Whether that *something* is worth the
token cost is your judgment, not ours.

Each entry below maps a category → (signal_name, baseline_value_usd, multiplier_factor).
- signal_name describes what came out
- baseline_value_usd is the floor (just doing this had some value)
- multiplier_factor amplifies based on session intensity (tool calls, file outputs)
"""
from __future__ import annotations

CATEGORY_VALUE: dict[str, dict] = {
    "new-feature": {
        "label": "Code shipped",
        "icon": "🚢",
        "baseline_usd": 50,           # even an unfinished new-feature session has scaffolding value
        "per_pr_usd": 600,
        "per_line_usd": 0.30,
    },
    "extend-feature": {
        "label": "Code extended",
        "icon": "➕",
        "baseline_usd": 30,
        "per_pr_usd": 400,
        "per_line_usd": 0.25,
    },
    "bug-fix": {
        "label": "Bug fixed",
        "icon": "🐛",
        "baseline_usd": 80,           # bugs have outsized value when fixed
        "per_pr_usd": 700,
        "per_line_usd": 0.40,
    },
    "debug": {
        "label": "Bug understood",
        "icon": "🔍",
        "baseline_usd": 40,           # even non-fixed debugging usually surfaces the root cause
        "per_pr_usd": 0,
        "per_line_usd": 0,
    },
    "refactor": {
        "label": "Code cleaned",
        "icon": "🧹",
        "baseline_usd": 30,
        "per_pr_usd": 300,
        "per_line_usd": 0.15,
    },
    "config-ops": {
        "label": "Infra changed",
        "icon": "⚙️",
        "baseline_usd": 60,           # "the deploy works now" is concrete value
        "per_pr_usd": 200,
        "per_line_usd": 0.10,
    },
    "research": {
        "label": "Info gathered",
        "icon": "📚",
        "baseline_usd": 25,           # an answered question is value, even if no artifact
        "per_pr_usd": 0,
        "per_line_usd": 0.05,         # if research wrote markdown, count that
    },
    "brainstorm": {
        "label": "Ideas explored",
        "icon": "💡",
        "baseline_usd": 20,
        "per_pr_usd": 0,
        "per_line_usd": 0,
    },
    "personal-task": {
        "label": "Life shipped",
        "icon": "🎯",
        "baseline_usd": 30,           # editing a resume, making a video, organizing files all have value
        "per_pr_usd": 0,
        "per_line_usd": 0.20,         # if produced files counts
    },
    "chat-misc": {
        "label": "Question answered",
        "icon": "❓",
        "baseline_usd": 5,            # even a quick lookup got you something
        "per_pr_usd": 0,
        "per_line_usd": 0,
    },
}


def estimate_session_value(session: dict, github_signal: dict | None = None) -> dict:
    """Estimate $ value for one session based on its category.

    `github_signal` is optional: {"pr_merged": True, "lines": 234, "reverted": False}
    """
    cat = (session.get("classification", {}) or {}).get("category", "chat-misc")
    cfg = CATEGORY_VALUE.get(cat, CATEGORY_VALUE["chat-misc"])
    value = float(cfg["baseline_usd"])
    breakdown = {"baseline_usd": cfg["baseline_usd"]}

    if github_signal:
        if github_signal.get("pr_merged"):
            pv = cfg["per_pr_usd"]
            if pv > 0:
                value += pv
                breakdown["pr_value_usd"] = pv
            if github_signal.get("reverted"):
                value = max(0, value - cfg["per_pr_usd"])
                breakdown["revert_penalty_usd"] = -cfg["per_pr_usd"]
        lines = github_signal.get("lines", 0)
        if lines > 0 and cfg["per_line_usd"] > 0:
            lv = lines * cfg["per_line_usd"] * 0.5
            value += lv
            breakdown["line_value_usd"] = round(lv, 2)

    # Tool-intensity bump: heavy session probably did more
    tool_total = sum((session.get("tool_counts") or {}).values())
    if tool_total > 50:
        bump = min(50, tool_total * 0.5)
        value += bump
        breakdown["tool_intensity_usd"] = round(bump, 2)

    return {
        "value_usd": round(value, 2),
        "category": cat,
        "label": cfg["label"],
        "icon": cfg["icon"],
        "breakdown": breakdown,
    }


def summarize_by_category(sessions: list[dict]) -> list[dict]:
    """Per-category aggregation: count, total cost, total value, ROI."""
    by_cat: dict[str, dict] = {}
    for s in sessions:
        cat = (s.get("classification", {}) or {}).get("category", "chat-misc")
        cost = float(s.get("est_cost_usd", 0))
        v = estimate_session_value(s)
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


def summarize_by_agent(sessions: list[dict]) -> list[dict]:
    by_agent: dict[str, dict] = {}
    for s in sessions:
        agent = s.get("agent", "unknown")
        cost = float(s.get("est_cost_usd", 0))
        v = estimate_session_value(s)
        d = by_agent.setdefault(agent, {"agent": agent, "count": 0, "cost_usd": 0, "value_usd": 0})
        d["count"] += 1
        d["cost_usd"] += cost
        d["value_usd"] += v["value_usd"]
    for d in by_agent.values():
        d["cost_usd"] = round(d["cost_usd"], 2)
        d["value_usd"] = round(d["value_usd"], 2)
        d["roi"] = round(d["value_usd"] / d["cost_usd"], 2) if d["cost_usd"] > 0 else None
    return sorted(by_agent.values(), key=lambda x: x["cost_usd"], reverse=True)
