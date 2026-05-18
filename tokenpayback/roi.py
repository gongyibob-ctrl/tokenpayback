"""Combine cost + output → ROI estimate. Generate markdown report + dashboard JSON."""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import cost as cost_mod
from . import output as output_mod
from .util import load_config, last_n_weeks, week_range

ROOT = Path.cwd()  # caller's working directory — runs in user's project


def estimate_value_usd(week_data: dict, config: dict) -> tuple[float, dict]:
    """Heuristic: PRs merged × value_per_pr + lines added × value_per_line / 2,
    with revert penalty. The /2 avoids double-counting additions in PRs."""
    value_per_pr = float(config.get("value_per_pr_usd", 600))
    value_per_line = float(config.get("value_per_line_committed_usd", 0.30))
    prs = week_data.get("prs_merged", 0)
    additions = week_data.get("additions", 0)
    reverts = week_data.get("reverts", 0)

    pr_value = prs * value_per_pr
    line_value = additions * value_per_line * 0.5
    revert_penalty = reverts * value_per_pr  # each revert wipes ~one PR's value

    gross = pr_value + line_value
    net = max(0.0, gross - revert_penalty)
    return net, {
        "pr_value_usd": round(pr_value, 2),
        "line_value_usd": round(line_value, 2),
        "revert_penalty_usd": round(revert_penalty, 2),
        "gross_value_usd": round(gross, 2),
        "net_value_usd": round(net, 2),
    }


def build_weeks(weeks: list[str], config: dict) -> dict[str, dict]:
    cost_by_week = cost_mod.collect(weeks, config)
    output_by_week = output_mod.collect(weeks, config)
    out: dict[str, dict] = {}
    for w in weeks:
        c = cost_by_week.get(w, {})
        o = output_by_week.get(w, {})
        cost_usd = float(c.get("total_usd") or 0)
        value_usd, breakdown = estimate_value_usd(o, config)
        roi = (value_usd / cost_usd) if cost_usd > 0 else None
        out[w] = {
            "week": w,
            "cost": c,
            "output": o,
            "value_breakdown": breakdown,
            "cost_usd": round(cost_usd, 2),
            "value_usd": round(value_usd, 2),
            "roi": round(roi, 2) if roi is not None else None,
        }
    return out


def fmt_money(v: float | None) -> str:
    if v is None:
        return "·"
    return f"${v:,.2f}"


def fmt_roi(r: float | None) -> str:
    if r is None:
        return "·"
    if r >= 1:
        return f"{r:.1f}×"
    return f"{r:.2f}×"


def render_markdown(weeks_data: dict[str, dict], config: dict) -> str:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = ["# tokenpayback — Coding AI ROI", "",
             f"_Generated {now}_  ",
             f"_GitHub user: `{config['github_username']}` · hourly rate assumed: ${config['hourly_rate_usd']}/hr_", ""]
    lines.append("## At a glance\n")
    lines.append("| Week | Cost | Est. Value | ROI | PRs | Commits | +lines | reverts |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for w in sorted(weeks_data):
        d = weeks_data[w]
        o = d["output"]
        lines.append(
            f"| {w} | {fmt_money(d['cost_usd'])} | {fmt_money(d['value_usd'])} | "
            f"**{fmt_roi(d['roi'])}** | {o['prs_merged']} | {o['commits']} | "
            f"+{o['additions']:,} | {o['reverts']} |"
        )
    lines.append("")
    # Latest week deep dive
    latest = sorted(weeks_data)[-1]
    d = weeks_data[latest]
    o = d["output"]
    b = d["value_breakdown"]
    c = d["cost"]
    lines += [
        f"## Latest week: {latest}", "",
        f"**ROI: {fmt_roi(d['roi'])}** — spent {fmt_money(d['cost_usd'])}, generated estimated {fmt_money(d['value_usd'])}",
        "",
        "### Cost breakdown",
        f"- Anthropic API: {fmt_money(c.get('anthropic_usd'))}",
        f"- OpenAI API: {fmt_money(c.get('openai_usd'))}",
        f"- Fixed subscriptions (weekly avg): {fmt_money(c.get('fixed_subscriptions_usd'))}",
        "",
        "### Value breakdown",
        f"- {o['prs_merged']} PRs merged × ${config['value_per_pr_usd']} = {fmt_money(b['pr_value_usd'])}",
        f"- {o['additions']:,} lines added × ${config['value_per_line_committed_usd']:.2f} × 0.5 = {fmt_money(b['line_value_usd'])}",
        f"- {o['reverts']} reverts × penalty = -{fmt_money(b['revert_penalty_usd'])}",
        f"- **Net: {fmt_money(b['net_value_usd'])}**",
        "",
        "### PRs this week",
    ]
    for p in o.get("prs", [])[:15]:
        lines.append(f"- [{p['repo']}#{p['url'].split('/')[-1]}]({p['url']}) — {p['title']}")
    lines += ["", "---", ""]
    lines.append("_Numbers are estimates. Value heuristics in `config.local.yaml` — tune for your context._")
    lines.append("_The 'right' number is the one that prompts the right next question, not perfect precision._")
    return "\n".join(lines)


def render_dashboard_json(weeks_data: dict[str, dict], config: dict) -> dict:
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "config": {
            "github_username": config["github_username"],
            "hourly_rate_usd": config["hourly_rate_usd"],
            "value_per_pr_usd": config["value_per_pr_usd"],
            "value_per_line_committed_usd": config["value_per_line_committed_usd"],
        },
        "weeks": [weeks_data[w] for w in sorted(weeks_data)],
    }
    # Pull in sessions classification if present (generated by scripts/classify_sessions.py)
    sessions_path = ROOT / "dashboard" / "sessions.json"
    if sessions_path.exists():
        try:
            import json as _json
            sessions = _json.loads(sessions_path.read_text())
            payload["sessions"] = sessions
            payload["sessionsTotals"] = _summarize_sessions(sessions)
        except Exception as e:
            print(f"  ! could not include sessions: {e}", file=sys.stderr)
    return payload


def _summarize_sessions(sessions: list[dict]) -> dict:
    from collections import Counter
    by_cat_cost: dict[str, float] = {}
    by_cat_count: dict[str, int] = {}
    by_proj_cost: dict[str, float] = {}
    by_proj_count: dict[str, int] = {}
    by_value_cost: dict[str, float] = {}
    total_cost = 0.0
    for s in sessions:
        c = s.get("classification", {})
        cost = float(s.get("est_cost_usd", 0))
        total_cost += cost
        cat = c.get("category", "?")
        proj = c.get("project", "?") or "?"
        val = c.get("value_signal", "?")
        by_cat_cost[cat] = by_cat_cost.get(cat, 0) + cost
        by_cat_count[cat] = by_cat_count.get(cat, 0) + 1
        by_proj_cost[proj] = by_proj_cost.get(proj, 0) + cost
        by_proj_count[proj] = by_proj_count.get(proj, 0) + 1
        by_value_cost[val] = by_value_cost.get(val, 0) + cost
    return {
        "totalCostUsd": round(total_cost, 2),
        "sessionCount": len(sessions),
        "byCategory": [{"key": k, "cost": round(by_cat_cost[k], 2), "count": by_cat_count[k]} for k in sorted(by_cat_cost, key=by_cat_cost.get, reverse=True)],
        "byProject": [{"key": k, "cost": round(by_proj_cost[k], 2), "count": by_proj_count[k]} for k in sorted(by_proj_cost, key=by_proj_cost.get, reverse=True)],
        "byValueSignal": [{"key": k, "cost": round(by_value_cost[k], 2)} for k in sorted(by_value_cost, key=by_value_cost.get, reverse=True)],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", type=int, default=4)
    args = ap.parse_args()

    cfg = load_config()
    weeks = last_n_weeks(args.weeks)
    print(f"[roi] processing weeks: {weeks}", file=sys.stderr)
    weeks_data = build_weeks(weeks, cfg)

    md = render_markdown(weeks_data, cfg)
    latest = sorted(weeks_data)[-1]
    report_path = ROOT / cfg["report_dir"] / f"{latest}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(md, encoding="utf-8")
    print(f"[roi] wrote {report_path}")

    dashboard = render_dashboard_json(weeks_data, cfg)
    dpath = ROOT / cfg["dashboard_data"]
    dpath.parent.mkdir(parents=True, exist_ok=True)
    dpath.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[roi] wrote {dpath}")


if __name__ == "__main__":
    main()
