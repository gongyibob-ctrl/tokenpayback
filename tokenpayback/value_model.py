"""Per-session value model.

Two layers, used together:
1. ROLE-BASED (preferred): if the classifier supplied role + minutes + rate +
   quality, value = (minutes/60) × rate × quality_multiplier — anchored to real
   market labor. Returns low/mid/high range. See role_value.py.
2. CATEGORY-BASELINE (fallback): if the role fields are missing (old data),
   use the user's taxonomy baselines + GitHub PR/line bonuses.

Aggregations always emit BOTH cost and value, and ROI uses the mid estimate.
"""
from __future__ import annotations

from .role_value import session_value_range, session_roi_range


# Fallback table — minimal, only used when neither role-based nor user taxonomy is available
FALLBACK_VALUES: dict[str, dict] = {
    "code-shipped":      {"label": "Code shipped",      "icon": "🚢", "baseline_usd": 60},
    "bug-fixed":         {"label": "Bug fixed",         "icon": "🐛", "baseline_usd": 80},
    "infra-changed":     {"label": "Infra changed",     "icon": "⚙️",  "baseline_usd": 50},
    "info-gathered":     {"label": "Info gathered",     "icon": "📚", "baseline_usd": 25},
    "ideas-explored":    {"label": "Ideas explored",    "icon": "💡", "baseline_usd": 20},
    "life-shipped":      {"label": "Life shipped",      "icon": "🎯", "baseline_usd": 30},
    "question-answered": {"label": "Question answered", "icon": "❓", "baseline_usd": 5},
}


def _category_config(cat_id: str, taxonomy: dict | None) -> dict:
    if taxonomy:
        for c in (taxonomy.get("categories") or []):
            if c.get("id") == cat_id:
                return c
    return FALLBACK_VALUES.get(cat_id) or FALLBACK_VALUES["question-answered"]


def estimate_session_value(session: dict, taxonomy: dict | None = None,
                           github_signal: dict | None = None) -> dict:
    """Returns: { value_usd (mid), value_low, value_high, source, label, icon, category, role?, quality?, breakdown }."""
    classification = session.get("classification") or {}
    cat = classification.get("category", "question-answered")
    cfg = _category_config(cat, taxonomy)
    label = cfg.get("label", cat)
    icon = cfg.get("icon", "•")

    # Path A: role-based (preferred when LLM supplied the fields)
    role_value = session_value_range(classification)
    if role_value:
        return {
            "value_usd": role_value["mid_usd"],
            "value_low": role_value["low_usd"],
            "value_high": role_value["high_usd"],
            "source": "role-based",
            "category": cat,
            "label": label,
            "icon": icon,
            "role": role_value["role"],
            "quality": role_value["quality"],
            "quality_multiplier": role_value["quality_multiplier"],
            "minutes_mid": role_value["minutes_mid"],
            "rate_mid": role_value["rate_mid"],
            "breakdown": {
                "minutes_low": role_value["minutes_low"],
                "minutes_mid": role_value["minutes_mid"],
                "minutes_high": role_value["minutes_high"],
                "rate_low": role_value["rate_low"],
                "rate_mid": role_value["rate_mid"],
                "rate_high": role_value["rate_high"],
                "quality_multiplier": role_value["quality_multiplier"],
            },
        }

    # Path B: category baseline
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
        "value_low": round(value * 0.7, 2),
        "value_high": round(value * 1.4, 2),
        "source": "category-baseline",
        "category": cat,
        "label": label,
        "icon": icon,
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
            "value_low_usd": 0,
            "value_usd": 0,
            "value_high_usd": 0,
            "human_minutes_total": 0,
        })
        d["count"] += 1
        d["cost_usd"] += cost
        d["value_low_usd"] += v.get("value_low") or 0
        d["value_usd"] += v["value_usd"]
        d["value_high_usd"] += v.get("value_high") or 0
        d["human_minutes_total"] += v.get("minutes_mid") or 0
    for d in by_cat.values():
        d["cost_usd"] = round(d["cost_usd"], 2)
        d["value_low_usd"] = round(d["value_low_usd"], 2)
        d["value_usd"] = round(d["value_usd"], 2)
        d["value_high_usd"] = round(d["value_high_usd"], 2)
        d["human_minutes_total"] = round(d["human_minutes_total"], 1)
        # Treat <$0.01 cost as effectively zero — ROI would be meaningless
        if d["cost_usd"] >= 0.01:
            d["roi"] = round(d["value_usd"] / d["cost_usd"], 2)
            d["roi_low"] = round(d["value_low_usd"] / d["cost_usd"], 2)
            d["roi_high"] = round(d["value_high_usd"] / d["cost_usd"], 2)
        else:
            d["roi"] = d["roi_low"] = d["roi_high"] = None
    return sorted(by_cat.values(), key=lambda x: x["cost_usd"], reverse=True)


def summarize_by_agent(sessions: list[dict], taxonomy: dict | None = None) -> list[dict]:
    by_agent: dict[str, dict] = {}
    for s in sessions:
        agent = s.get("agent", "unknown")
        cost = float(s.get("est_cost_usd", 0))
        v = estimate_session_value(s, taxonomy)
        d = by_agent.setdefault(agent, {"agent": agent, "count": 0, "cost_usd": 0,
                                         "value_low_usd": 0, "value_usd": 0, "value_high_usd": 0,
                                         "human_minutes_total": 0})
        d["count"] += 1
        d["cost_usd"] += cost
        d["value_low_usd"] += v.get("value_low") or 0
        d["value_usd"] += v["value_usd"]
        d["value_high_usd"] += v.get("value_high") or 0
        d["human_minutes_total"] += v.get("minutes_mid") or 0
    for d in by_agent.values():
        d["cost_usd"] = round(d["cost_usd"], 2)
        d["value_low_usd"] = round(d["value_low_usd"], 2)
        d["value_usd"] = round(d["value_usd"], 2)
        d["value_high_usd"] = round(d["value_high_usd"], 2)
        d["human_minutes_total"] = round(d["human_minutes_total"], 1)
        if d["cost_usd"] >= 0.01:
            d["roi"] = round(d["value_usd"] / d["cost_usd"], 2)
            d["roi_low"] = round(d["value_low_usd"] / d["cost_usd"], 2)
            d["roi_high"] = round(d["value_high_usd"] / d["cost_usd"], 2)
        else:
            d["roi"] = d["roi_low"] = d["roi_high"] = None
    return sorted(by_agent.values(), key=lambda x: x["cost_usd"], reverse=True)


def overall_summary(sessions: list[dict], taxonomy: dict | None = None) -> dict:
    total_cost = 0.0
    total_val_low = total_val_mid = total_val_high = 0.0
    total_minutes = 0.0
    role_counter: dict[str, int] = {}
    quality_counter: dict[str, int] = {}
    for s in sessions:
        cost = float(s.get("est_cost_usd", 0))
        v = estimate_session_value(s, taxonomy)
        total_cost += cost
        total_val_low += v.get("value_low") or 0
        total_val_mid += v["value_usd"]
        total_val_high += v.get("value_high") or 0
        total_minutes += v.get("minutes_mid") or 0
        role = v.get("role")
        if role:
            role_counter[role] = role_counter.get(role, 0) + 1
        q = v.get("quality")
        if q:
            quality_counter[q] = quality_counter.get(q, 0) + 1
    return {
        "totalCostUsd": round(total_cost, 2),
        "totalValueLowUsd": round(total_val_low, 2),
        "totalValueUsd": round(total_val_mid, 2),
        "totalValueHighUsd": round(total_val_high, 2),
        "humanHoursSaved": round(total_minutes / 60, 1),
        "humanDaysSaved": round(total_minutes / 60 / 8, 1),  # 8h work day
        "roiMid": round(total_val_mid / total_cost, 2) if total_cost > 0 else None,
        "roiLow": round(total_val_low / total_cost, 2) if total_cost > 0 else None,
        "roiHigh": round(total_val_high / total_cost, 2) if total_cost > 0 else None,
        "topRoles": sorted(role_counter.items(), key=lambda x: x[1], reverse=True)[:5],
        "qualityMix": quality_counter,
    }
