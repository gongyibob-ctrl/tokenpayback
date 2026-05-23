"""Cross-session analytics — KPIs borrowed from cost-accounting frameworks.

Every function here is a transparent heuristic. The formulas live next to the code
so users can read exactly what the dashboard is claiming. Per project CLAUDE.md:
no magic numbers, no hidden assumptions.

Frameworks referenced (see README.md):
  - Activity-Based Management (Cooper & Kaplan, 1991) — VA/NVA/BVA split
  - Variance Analysis (ACCA / CIMA) — yield / rate / efficiency variance
  - Resource Consumption Accounting (GPK, 1950s) — proportional vs fixed split
  - Lean Value Stream Costing (Maskell) — per-project rollup
  - Cost of Quality / PAF model (Juran, 1962) — internal failure cost
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable

from .value_class import (
    VA, NVA, BVA, ALL_CLASSES,
    derive_value_class, session_value_class, is_internal_failure,
)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # Tolerate both with and without timezone
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _iso_week(d: datetime | None) -> str | None:
    if d is None:
        return None
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _session_cost(s: dict) -> float:
    return float(s.get("est_cost_usd") or 0)


def _session_tokens(s: dict) -> int:
    return int(s.get("token_in") or 0) + int(s.get("token_out") or 0)


# -----------------------------------------------------------------------------
# 1. NVA Summary — Activity-Based Management
#    Formula: %_class = $_class / $_total for each class in {VA, NVA, BVA}
#    Internal Failure Cost = $ on sessions with replacement_quality in (failed, harmful)
# -----------------------------------------------------------------------------

def nva_summary(sessions: list[dict]) -> dict:
    """Return VA/NVA/BVA $ totals, percentages, and an Internal Failure breakdown.

    Healthy mature ops target NVA < 20% (per Ledger KPI framework §11).
    Greenfield AI usage commonly sits at 30-50%. Above that = most of the easy
    money to save lives in cutting retry / hallucination cost.
    """
    by_class_cost: dict[str, float] = defaultdict(float)
    by_class_count: dict[str, int] = defaultdict(int)
    internal_failure_cost = 0.0
    internal_failure_count = 0
    harmful_cost = 0.0
    harmful_count = 0
    examples: dict[str, list[dict]] = {VA: [], NVA: [], BVA: []}
    for s in sessions:
        cost = _session_cost(s)
        vc = session_value_class(s)
        by_class_cost[vc] += cost
        by_class_count[vc] += 1
        # Per Juran's PAF model: internal failure = caught before customer.
        if is_internal_failure(s):
            internal_failure_cost += cost
            internal_failure_count += 1
            q = (s.get("classification") or {}).get("replacement_quality")
            if q == "harmful":
                harmful_cost += cost
                harmful_count += 1
        # Keep a few examples per class for the dashboard drill-down
        if len(examples[vc]) < 5 and cost > 0:
            c = s.get("classification") or {}
            examples[vc].append({
                "date": (s.get("last_event") or "")[:10],
                "agent": s.get("agent"),
                "project": c.get("project") or s.get("project") or "?",
                "summary": (c.get("summary") or "")[:120],
                "cost_usd": round(cost, 2),
                "quality": c.get("replacement_quality"),
                "category": c.get("category"),
            })
    total_cost = sum(by_class_cost.values())
    out = {
        "totalCostUsd": round(total_cost, 2),
        "byClass": [],
        "internalFailure": {
            "costUsd": round(internal_failure_cost, 2),
            "sessionCount": internal_failure_count,
            "pct": round(100 * internal_failure_cost / total_cost, 1) if total_cost > 0 else 0,
            "harmfulCostUsd": round(harmful_cost, 2),
            "harmfulCount": harmful_count,
        },
        "examples": examples,
        # Health hint for the UI
        "nvaHealthHint": _nva_health_hint(by_class_cost.get(NVA, 0), total_cost),
    }
    for cls in (VA, NVA, BVA):
        cost = by_class_cost.get(cls, 0)
        out["byClass"].append({
            "class": cls,
            "label": {VA: "Value-Added", NVA: "Non-Value-Added", BVA: "Business-Value-Added"}[cls],
            "costUsd": round(cost, 2),
            "sessionCount": by_class_count.get(cls, 0),
            "pct": round(100 * cost / total_cost, 1) if total_cost > 0 else 0,
        })
    return out


def _nva_health_hint(nva_cost: float, total: float) -> dict:
    if total <= 0:
        return {"band": "unknown", "label": "no data yet"}
    pct = 100 * nva_cost / total
    if pct < 15:
        return {"band": "mature", "label": f"{pct:.0f}% NVA — mature usage"}
    if pct < 25:
        return {"band": "healthy", "label": f"{pct:.0f}% NVA — within healthy range"}
    if pct < 40:
        return {"band": "greenfield", "label": f"{pct:.0f}% NVA — typical greenfield, room to cut"}
    return {"band": "high", "label": f"{pct:.0f}% NVA — high; most savings hide here"}


# -----------------------------------------------------------------------------
# 2. Weekly Variance — ACCA / CIMA Standard Costing & Variance Analysis
#    yield  = $_VA / $_total per week.    Drop = silent quality regression.
#    rate   = $_total / VA-output per week. Spike = model drift or price hike.
#    eff    = tokens / VA-output per week. Spike = verbosity / retry bloat.
# -----------------------------------------------------------------------------

def weekly_buckets(sessions: list[dict]) -> dict[str, list[dict]]:
    """Group sessions by ISO week (key 'YYYY-WNN'). Sessions with no date are skipped."""
    out: dict[str, list[dict]] = defaultdict(list)
    for s in sessions:
        d = _parse_iso(s.get("last_event")) or _parse_iso(s.get("first_event"))
        wk = _iso_week(d)
        if wk:
            out[wk].append(s)
    return dict(out)


def weekly_metrics(weekly: dict[str, list[dict]]) -> list[dict]:
    """Per-week summary: total $, VA $, NVA $, BVA $, VA-session count, tokens."""
    out = []
    for wk in sorted(weekly):
        sess = weekly[wk]
        total_cost = sum(_session_cost(s) for s in sess)
        va_cost = nva_cost = bva_cost = 0.0
        va_count = 0
        tokens = 0
        for s in sess:
            cost = _session_cost(s)
            vc = session_value_class(s)
            if vc == VA:
                va_cost += cost
                va_count += 1
            elif vc == NVA:
                nva_cost += cost
            else:
                bva_cost += cost
            tokens += _session_tokens(s)
        out.append({
            "week": wk,
            "sessionCount": len(sess),
            "totalCostUsd": round(total_cost, 2),
            "vaCostUsd": round(va_cost, 2),
            "nvaCostUsd": round(nva_cost, 2),
            "bvaCostUsd": round(bva_cost, 2),
            "vaSessionCount": va_count,
            "tokens": tokens,
            # Derived ratios
            "yield": round(va_cost / total_cost, 4) if total_cost > 0 else None,  # share of $ that was value-added
            "costPerVaSession": round(total_cost / va_count, 2) if va_count > 0 else None,
            "tokensPerVaSession": round(tokens / va_count, 0) if va_count > 0 else None,
        })
    return out


def weekly_variance(sessions: list[dict]) -> dict:
    """Compute week-over-week variance signals — the "drift detector."

    Compares the most recent week against the trailing-3-week baseline (matches the
    pitch's "5-quarter rolling forecast" idea, downsized to weeks for an indie loop).

    Each signal includes:
      latest:    current week's value
      baseline:  mean of prior 3 weeks (with data)
      delta_pct: (latest - baseline) / baseline × 100
      verdict:   ok / warn / alert based on threshold direction
    """
    weekly = weekly_buckets(sessions)
    metrics = weekly_metrics(weekly)
    if len(metrics) < 2:
        return {"weeks": metrics, "signals": [], "note": "need at least 2 weeks of data"}
    latest = metrics[-1]
    baseline_window = metrics[-4:-1] if len(metrics) >= 4 else metrics[:-1]

    def _mean(key: str) -> float | None:
        vals = [m[key] for m in baseline_window if m.get(key) is not None]
        return sum(vals) / len(vals) if vals else None

    def _signal(label: str, key: str, *, alert_direction: str,
                warn_pct: float, alert_pct: float, why: str) -> dict:
        cur = latest.get(key)
        base = _mean(key)
        if cur is None or base is None or base == 0:
            return {"label": label, "verdict": "insufficient", "why": why}
        delta_pct = (cur - base) / base * 100
        if alert_direction == "down":  # bad when value DROPS (e.g. yield)
            if delta_pct <= -alert_pct:
                verdict = "alert"
            elif delta_pct <= -warn_pct:
                verdict = "warn"
            else:
                verdict = "ok"
        else:  # bad when value RISES (e.g. cost-per-output, tokens-per-output)
            if delta_pct >= alert_pct:
                verdict = "alert"
            elif delta_pct >= warn_pct:
                verdict = "warn"
            else:
                verdict = "ok"
        return {
            "label": label,
            "latest": cur,
            "baseline": round(base, 2),
            "deltaPct": round(delta_pct, 1),
            "verdict": verdict,
            "why": why,
        }

    signals = [
        _signal(
            "Yield Variance",
            "yield",
            alert_direction="down",
            warn_pct=10, alert_pct=20,
            why="Share of $ going to value-added work. Drop = silent quality regression (model swap, prompt rot, retrieval drift).",
        ),
        _signal(
            "Rate Variance",
            "costPerVaSession",
            alert_direction="up",
            warn_pct=15, alert_pct=30,
            why="$ per value-added session. Spike = model-mix drift (Haiku → Sonnet → Opus) or vendor price hike.",
        ),
        _signal(
            "Efficiency Variance",
            "tokensPerVaSession",
            alert_direction="up",
            warn_pct=20, alert_pct=40,
            why="Tokens per value-added session. Spike = verbosity, over-long CoT, retry bloat.",
        ),
    ]
    return {"weeks": metrics, "signals": signals}


# -----------------------------------------------------------------------------
# 3. Cost Split — Resource Consumption Accounting (GPK)
#    Proportional cost varies with use (per-call API spend, session-level estimates).
#    Fixed cost stays whether or not you use the tool (subscriptions).
#    Pricing decisions belong to proportional. Cancel/keep decisions to fixed.
# -----------------------------------------------------------------------------

def cost_split(sessions: list[dict], config: dict, weekly_subs_usd: float) -> dict:
    """Split total spend into proportional (per-call) vs fixed (subscriptions).

    Also computes per-subscription utilization: how many of the last 30 calendar
    days had at least one session via the agent that subscription maps to. A sub
    you didn't touch for 21/30 days is a cancel candidate.
    """
    proportional = sum(_session_cost(s) for s in sessions)
    subs_monthly = dict(config.get("fixed_monthly_subscriptions_usd") or {})
    fixed_monthly = sum(float(v or 0) for v in subs_monthly.values())
    fixed_weekly = weekly_subs_usd if weekly_subs_usd else fixed_monthly * 12.0 / 52.0
    total = proportional + fixed_weekly

    # Sub → agent mapping. Keep transparent — users can override in config later.
    sub_to_agent = {
        "claude_max": "claude-code",
        "claude_pro": "claude-code",
        "cursor": "cursor",
        "github_copilot": None,         # no local data exposed by Copilot
        "chatgpt_plus": None,           # no parser yet
        "codex_cli": "codex",
    }
    # Compute active-day count per agent over the last 30 calendar days
    now = datetime.now(timezone.utc)
    days_by_agent: dict[str, set[str]] = defaultdict(set)
    for s in sessions:
        d = _parse_iso(s.get("last_event"))
        if not d:
            continue
        delta_days = (now - d.replace(tzinfo=timezone.utc) if d.tzinfo is None else now - d).days
        if 0 <= delta_days <= 30:
            days_by_agent[s.get("agent") or ""].add(d.date().isoformat())

    sub_utilization = []
    for sub_name, monthly_cost in subs_monthly.items():
        agent = sub_to_agent.get(sub_name)
        if agent:
            active_days = len(days_by_agent.get(agent, set()))
            util_pct = round(100 * active_days / 30, 0)
            verdict = "ok" if util_pct >= 50 else ("warn" if util_pct >= 20 else "cancel-candidate")
            sub_utilization.append({
                "name": sub_name,
                "monthlyUsd": float(monthly_cost or 0),
                "agent": agent,
                "activeDays30d": active_days,
                "utilizationPct": util_pct,
                "verdict": verdict,
                "hint": _utilization_hint(verdict, sub_name, monthly_cost),
            })
        else:
            sub_utilization.append({
                "name": sub_name,
                "monthlyUsd": float(monthly_cost or 0),
                "agent": None,
                "activeDays30d": None,
                "utilizationPct": None,
                "verdict": "no-data",
                "hint": "no parser for this sub yet — utilization unknown",
            })

    return {
        "proportionalUsd": round(proportional, 2),
        "fixedWeeklyUsd": round(fixed_weekly, 2),
        "fixedMonthlyUsd": round(fixed_monthly, 2),
        "totalUsd": round(total, 2),
        "proportionalPct": round(100 * proportional / total, 1) if total > 0 else 0,
        "fixedPct": round(100 * fixed_weekly / total, 1) if total > 0 else 0,
        "subscriptions": sub_utilization,
    }


def _utilization_hint(verdict: str, name: str, monthly: float) -> str:
    if verdict == "cancel-candidate":
        return f"used on fewer than 6 of last 30 days — ~${monthly:.0f}/mo possibly recoverable"
    if verdict == "warn":
        return "low utilization — worth re-evaluating next renewal"
    if verdict == "ok":
        return "well utilized"
    return ""


# -----------------------------------------------------------------------------
# 4. Causality Score — RCA principle of causality
#    Formula: $ traced to specific sessions / total $
#    Below 70% on the Ledger framework = "estimate-only, not audit-grade"
#    For an individual: how much of your spend is attributable to a specific
#    thing you did vs sitting in a flat subscription you might be wasting.
# -----------------------------------------------------------------------------

def causality_score(proportional_usd: float, fixed_usd: float) -> dict:
    total = proportional_usd + fixed_usd
    if total <= 0:
        return {"score": None, "verdict": "no-data", "label": "no spend yet"}
    score = round(100 * proportional_usd / total, 1)
    if score >= 85:
        verdict, label = "high", "audit-grade traceability"
    elif score >= 70:
        verdict, label = "ok", "decent traceability"
    elif score >= 50:
        verdict, label = "low", "half your spend is just sitting in subs"
    else:
        verdict, label = "very-low", "most of your spend is flat — cancel candidates likely"
    return {"score": score, "verdict": verdict, "label": label,
            "tracedUsd": round(proportional_usd, 2), "untracedUsd": round(fixed_usd, 2)}


# -----------------------------------------------------------------------------
# 5. Value Stream Cost — Lean / Maskell
#    Per-project rollup: total $ spent, total estimated value, session count, ROI.
#    A "project" here is whatever the parser identified (cwd / workspace name).
# -----------------------------------------------------------------------------

def value_stream(sessions: list[dict], taxonomy: dict | None = None) -> list[dict]:
    """Roll up cost + value per project (the indie equivalent of a value stream)."""
    from .value_model import estimate_session_value
    by_proj: dict[str, dict] = {}
    for s in sessions:
        c = s.get("classification") or {}
        proj = c.get("project") or s.get("project") or "(unknown)"
        cost = _session_cost(s)
        val = estimate_session_value(s, taxonomy)
        agent = s.get("agent") or "?"
        d = by_proj.setdefault(proj, {
            "project": proj,
            "sessionCount": 0,
            "costUsd": 0.0,
            "valueLowUsd": 0.0,
            "valueUsd": 0.0,
            "valueHighUsd": 0.0,
            "agents": set(),
            "nvaCostUsd": 0.0,
        })
        d["sessionCount"] += 1
        d["costUsd"] += cost
        d["valueLowUsd"] += val.get("value_low") or 0
        d["valueUsd"] += val.get("value_usd") or 0
        d["valueHighUsd"] += val.get("value_high") or 0
        d["agents"].add(agent)
        if session_value_class(s) == NVA:
            d["nvaCostUsd"] += cost
    out = []
    for d in by_proj.values():
        cost = round(d["costUsd"], 2)
        value = round(d["valueUsd"], 2)
        out.append({
            "project": d["project"],
            "sessionCount": d["sessionCount"],
            "costUsd": cost,
            "valueLowUsd": round(d["valueLowUsd"], 2),
            "valueUsd": value,
            "valueHighUsd": round(d["valueHighUsd"], 2),
            "roi": round(value / cost, 2) if cost >= 0.01 else None,
            "agents": sorted(d["agents"]),
            "agentCount": len(d["agents"]),
            "nvaCostUsd": round(d["nvaCostUsd"], 2),
            "nvaPct": round(100 * d["nvaCostUsd"] / cost, 1) if cost >= 0.01 else None,
        })
    out.sort(key=lambda x: x["costUsd"], reverse=True)
    return out


# -----------------------------------------------------------------------------
# 6. Cross-Tool Redundancy — Ledger original
#    Projects where >1 agent ran. Indicates you're paying for overlapping tools
#    on the same work. The smaller spend bucket is the cancel candidate.
# -----------------------------------------------------------------------------

def cross_tool_redundancy(sessions: list[dict]) -> dict:
    """Find projects touched by multiple agents — likely tool overlap."""
    by_proj_agent: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    by_proj_count: dict[str, int] = defaultdict(int)
    for s in sessions:
        c = s.get("classification") or {}
        proj = c.get("project") or s.get("project") or "(unknown)"
        agent = s.get("agent") or "?"
        by_proj_agent[proj][agent] += _session_cost(s)
        by_proj_count[proj] += 1
    overlapping = []
    for proj, agent_costs in by_proj_agent.items():
        if len(agent_costs) < 2:
            continue
        total = sum(agent_costs.values())
        # The smaller spend bucket(s) are the cancel candidates
        ranked = sorted(agent_costs.items(), key=lambda x: x[1], reverse=True)
        primary = ranked[0]
        secondaries = ranked[1:]
        recoverable = sum(c for _, c in secondaries)
        overlapping.append({
            "project": proj,
            "totalUsd": round(total, 2),
            "sessionCount": by_proj_count[proj],
            "primaryAgent": primary[0],
            "primaryCostUsd": round(primary[1], 2),
            "secondaryAgents": [{"agent": a, "costUsd": round(c, 2)} for a, c in secondaries],
            "recoverableUsd": round(recoverable, 2),
        })
    overlapping.sort(key=lambda x: x["recoverableUsd"], reverse=True)
    total_recoverable = sum(o["recoverableUsd"] for o in overlapping)
    return {
        "projects": overlapping,
        "totalRecoverableUsd": round(total_recoverable, 2),
        "overlappingProjectCount": len(overlapping),
    }


# -----------------------------------------------------------------------------
# 7. Attended / Unattended — Ledger original (autonomy rate)
#    Heuristic: sessions with ≤ 2 user messages are "unattended" — user prompted
#    once or twice and the agent ran. > 2 = "attended" (back-and-forth).
#    Trend toward 1.0 = real digital workforce; flat-low = glorified macro.
# -----------------------------------------------------------------------------

def attended_unattended(sessions: list[dict]) -> dict:
    if not sessions:
        return {"attendedCount": 0, "unattendedCount": 0, "autonomyRate": None,
                "attendedCostUsd": 0, "unattendedCostUsd": 0}
    att_n = unatt_n = 0
    att_c = unatt_c = 0.0
    for s in sessions:
        msgs = int(s.get("user_messages") or 0)
        cost = _session_cost(s)
        if msgs <= 2:
            unatt_n += 1
            unatt_c += cost
        else:
            att_n += 1
            att_c += cost
    total_n = att_n + unatt_n
    total_c = att_c + unatt_c
    return {
        "attendedCount": att_n,
        "unattendedCount": unatt_n,
        "autonomyRate": round(unatt_n / total_n, 3) if total_n > 0 else None,
        "attendedCostUsd": round(att_c, 2),
        "unattendedCostUsd": round(unatt_c, 2),
        "unattendedCostPct": round(100 * unatt_c / total_c, 1) if total_c > 0 else None,
    }


# -----------------------------------------------------------------------------
# 8. Cost Parity Highlight — Ledger original (Human ↔ AI Cost Parity Index)
#    The hero number: $ that AI saved by doing work that would have cost real
#    human-labor-market dollars. Uses the existing role_value engine.
# -----------------------------------------------------------------------------

def cost_parity_highlight(sessions: list[dict], taxonomy: dict | None,
                          config: dict) -> dict:
    """Single-number framing: 'AI cost you $X; same work hired out would have been $Y'.

    parity_ratio = AI_cost / human_equivalent_cost — values < 1 mean AI is cheaper.
    For individuals, the more relatable number is the $ saved.
    """
    from .value_model import overall_summary
    summary = overall_summary(sessions, taxonomy)
    ai_cost = summary.get("totalCostUsd") or 0
    human_equiv = summary.get("totalValueUsd") or 0
    saved = max(0, human_equiv - ai_cost)
    parity = (ai_cost / human_equiv) if human_equiv > 0 else None
    hourly_rate = float(config.get("hourly_rate_usd") or 150)
    return {
        "aiCostUsd": round(ai_cost, 2),
        "humanEquivUsd": round(human_equiv, 2),
        "savedUsd": round(saved, 2),
        "parityRatio": round(parity, 3) if parity is not None else None,
        "hourlyRateAssumed": hourly_rate,
        "hoursSaved": summary.get("humanHoursSaved"),
    }
