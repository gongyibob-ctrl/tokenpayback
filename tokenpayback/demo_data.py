"""Synthetic demo dataset for the public marketing dashboard.

`tokenpayback.vercel.app` shows this data — no real user info is ever pushed
to the public repo. Run: `python -m tokenpayback.demo_data > dashboard/data.json`
"""
from __future__ import annotations
import json
import sys
import random
from datetime import datetime, timedelta, timezone


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def iso_week(d):
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def build_demo() -> dict:
    random.seed(42)
    now = datetime.now(timezone.utc)
    monday_this = (now - timedelta(days=now.weekday())).date()
    weeks_data = []
    week_outputs = [
        {"prs_merged": 8, "additions": 1830, "deletions": 720, "commits": 47, "reverts": 1},
        {"prs_merged": 14, "additions": 3120, "deletions": 1480, "commits": 71, "reverts": 0},
        {"prs_merged": 5, "additions": 980, "deletions": 410, "commits": 32, "reverts": 2},
        {"prs_merged": 17, "additions": 4250, "deletions": 1670, "commits": 89, "reverts": 1},
    ]
    week_costs = [
        {"anthropic_usd": 142.30, "openai_usd": 18.40, "fixed_subscriptions_usd": 32.08},
        {"anthropic_usd": 218.75, "openai_usd": 22.10, "fixed_subscriptions_usd": 32.08},
        {"anthropic_usd": 89.50, "openai_usd": 12.30, "fixed_subscriptions_usd": 32.08},
        {"anthropic_usd": 264.20, "openai_usd": 31.50, "fixed_subscriptions_usd": 32.08},
    ]
    value_per_pr = 600
    value_per_line = 0.30
    demo_prs_pool = [
        "feat(auth): add magic-link login flow",
        "fix(billing): handle stripe webhook idempotency",
        "refactor(api): split monolith routes into modules",
        "feat(dashboard): live KPI cards with optimistic updates",
        "fix(db): null pointer in subscription expiry check",
        "feat(notifications): batch digest emails",
    ]
    for i in range(4):
        wd = monday_this - timedelta(weeks=3 - i)
        w = iso_week(wd)
        cost = week_costs[i]
        total_cost = sum(cost.values())
        out = week_outputs[i]
        prs = [{"title": demo_prs_pool[(i * 4 + j) % len(demo_prs_pool)],
                "url": f"https://github.com/your-org/your-app/pull/{(i + 1) * 100 + j}",
                "repo": "your-org/your-app",
                "merged_at": (wd + timedelta(days=j)).isoformat()}
               for j in range(min(5, out["prs_merged"]))]
        out_dict = {**out, "repos_touched": ["your-org/your-app"], "prs": prs, "changed_files": 47}
        pr_value = out["prs_merged"] * value_per_pr
        line_value = out["additions"] * value_per_line * 0.5
        revert_penalty = out["reverts"] * value_per_pr
        gross = pr_value + line_value
        net = max(0.0, gross - revert_penalty)
        weeks_data.append({
            "week": w,
            "cost": {**cost, "total_usd": round(total_cost, 2)},
            "output": out_dict,
            "value_breakdown": {
                "pr_value_usd": round(pr_value, 2),
                "line_value_usd": round(line_value, 2),
                "revert_penalty_usd": round(revert_penalty, 2),
                "gross_value_usd": round(gross, 2),
                "net_value_usd": round(net, 2),
            },
            "cost_usd": round(total_cost, 2),
            "value_usd": round(net, 2),
            "roi": round(net / total_cost, 2) if total_cost else None,
        })

    # synthetic sessions — multi-agent + multi-category + role-based valuation
    fake = [
        # (agent, cat, proj, summary, cost, tools, value_signal, role, mins(low,mid,high), rate(low,mid,high), quality)
        ("claude-code", "new-feature", "your-app",         "Built magic-link auth with email service + cooldown.",                    47.30, 142, "shipped-code",
         "Senior backend engineer", (90, 180, 300), (150, 200, 280), "with-edits"),
        ("claude-code", "extend-feature", "your-app",      "Added typeahead search to nav with debouncer.",                            8.40,  61, "shipped-code",
         "Mid frontend engineer",   (30,  60, 120), (100, 140, 180), "full-replacement"),
        ("claude-code", "bug-fix", "your-app",             "Fixed stripe webhook race that double-charged on retries.",                5.60,  44, "shipped-code",
         "Senior backend engineer", (60, 120, 240), (180, 220, 280), "with-edits"),
        ("claude-code", "refactor", "your-app",            "Split monolith into 5 route modules, kept all tests green.",              23.80, 102, "shipped-code",
         "Staff engineer",          (60, 150, 240), (180, 240, 320), "with-edits"),
        ("codex",       "config-ops", "infra",             "Wired GitHub Actions cron + Vercel preview deploys.",                      3.40,  27, "shipped-code",
         "DevOps engineer",         (20,  45,  90), (140, 180, 240), "full-replacement"),
        ("codex",       "debug", "your-app",               "Tracked down stripe webhook race condition — repro'd in test.",            5.60,  44, "info-gathered",
         "Senior backend engineer", (45,  90, 180), (180, 220, 280), "draft-only"),
        ("hermes",      "research", "competitive-scan",    "Surveyed 5 dashboards in the space, wrote diff matrix.",                   2.10,  14, "researched",
         "Product analyst",         (60, 120, 240), ( 80, 120, 180), "with-edits"),
        ("hermes",      "brainstorm", "v2-roadmap",        "Talked through v2 multi-tenant data model tradeoffs.",                     0.80,   6, "info-gathered",
         "Product / staff eng",     (30,  60, 120), (180, 240, 320), "draft-only"),
        ("openclaw",    "personal-task", "weekly-review",  "Drafted board update from this week's metrics.",                           1.40,  11, "shipped-code",
         "Executive ghostwriter",   (40,  60, 120), ( 80, 150, 250), "with-edits"),
        ("openclaw",    "personal-task", "trip-planning",  "Planned weekend route + booked hotel via tool calls.",                     0.60,   8, "shipped-code",
         "Travel agent",            (30,  45,  90), ( 40,  60, 100), "full-replacement"),
        ("claude-code", "new-feature", "your-app",         "Implemented CSV import pipeline w/ progress events.",                     19.20,  88, "shipped-code",
         "Senior backend engineer", (60, 120, 240), (150, 200, 280), "full-replacement"),
        ("claude-code", "extend-feature", "your-app",      "Added export endpoints (CSV + JSON) with rate limiting.",                  7.10,  53, "shipped-code",
         "Mid backend engineer",    (30,  60, 120), (100, 140, 180), "full-replacement"),
        ("codex",       "config-ops", "infra",             "Set up Sentry + Datadog tracing on the API.",                              4.20,  29, "shipped-code",
         "DevOps engineer",         (40,  90, 180), (140, 180, 240), "with-edits"),
        ("hermes",      "chat-misc", "general",            "Quick question about postgres index strategy.",                            0.20,   3, "info-gathered",
         "Database consultant",     ( 5,  10,  20), (150, 250, 350), "full-replacement"),
        ("openclaw",    "chat-misc", "general",            "Recipe lookup + grocery list.",                                            0.15,   5, "info-gathered",
         "Personal assistant",      ( 5,  10,  20), ( 25,  40,  60), "full-replacement"),
    ]
    base = datetime.now(timezone.utc)
    sessions = []
    for idx, row in enumerate(fake):
        agent, cat, proj, summary, cost, tool_count, value_signal, role, mins, rates, quality = row
        d = base - timedelta(days=idx * 2, hours=random.randint(0, 6))
        sessions.append({
            "agent": agent,
            "session_id": f"demo-{idx:04d}",
            "project": proj,
            "first_prompt": "(demo)",
            "first_event": d.isoformat(),
            "last_event": d.isoformat(),
            "user_messages": random.randint(8, 40),
            "tool_counts": {"Bash": int(tool_count * 0.45), "Edit": int(tool_count * 0.2),
                             "Read": int(tool_count * 0.15), "Write": int(tool_count * 0.1),
                             "TaskCreate": int(tool_count * 0.05), "TaskUpdate": int(tool_count * 0.05)},
            "files_touched": [],
            "bash_sample": [],
            "token_in": int(cost / 0.000003),
            "token_out": int(cost / 0.000015),
            "cache_create": 0, "cache_read": 0,
            "est_cost_usd": round(cost, 2),
            "file_size": 0,
            "file_path": "(demo)",
            "classification": {
                "category": cat,
                "project": proj,
                "summary": summary,
                "value_signal": value_signal,
                "main_artifact": proj,
                "model": "demo",
                "equivalent_role": role,
                "human_minutes_low": mins[0],
                "human_minutes_mid": mins[1],
                "human_minutes_high": mins[2],
                "hourly_rate_usd_low": rates[0],
                "hourly_rate_usd_mid": rates[1],
                "hourly_rate_usd_high": rates[2],
                "replacement_quality": quality,
            },
        })

    from .value_model import summarize_by_category, summarize_by_agent, overall_summary

    return {
        "generatedAt": utc_now(),
        "isDemo": True,
        "config": {
            "github_username": "demo-user",
            "hourly_rate_usd": 150,
            "value_per_pr_usd": 600,
            "value_per_line_committed_usd": 0.30,
        },
        "benchmark": {"region": "us-west", "seniority": "senior", "currency": "USD"},
        "weeks": weeks_data,
        "sessions": sessions,
        "sessionsTotals": {
            "totalCostUsd": round(sum(s["est_cost_usd"] for s in sessions), 2),
            "sessionCount": len(sessions),
        },
        "byCategory": summarize_by_category(sessions),
        "byAgent": summarize_by_agent(sessions),
        "overall": overall_summary(sessions),
    }


def main() -> None:
    data = build_demo()
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
