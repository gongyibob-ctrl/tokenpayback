"""Synthetic demo dataset for the public marketing dashboard.

`tokenpayback.vercel.app` shows this data — no real user info is ever pushed
to the public repo. Demo is deliberately DIVERSE to show the tool isn't just
for coding — it covers code, decks, video, copy, research, personal tasks,
ops, and life logistics, all with role-based valuation.
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


# A diverse synthetic taxonomy that mirrors how a real person — founder type —
# actually uses AI: not just code.
DEMO_TAXONOMY = {
    "discovered": True,
    "rationale": "Synthetic founder/maker taxonomy showcasing tokenpayback's full range.",
    "categories": [
        {"id": "ship-feature",        "icon": "🚢", "label": "Ship feature",
         "description": "Building or completing a product feature end-to-end.",
         "baseline_usd": 100, "per_pr_usd": 600, "per_line_usd": 0.30},
        {"id": "bug-investigation",   "icon": "🐛", "label": "Bug fix",
         "description": "Diagnosing and fixing a defect.",
         "baseline_usd": 80, "per_pr_usd": 700, "per_line_usd": 0.40},
        {"id": "ops-and-deploy",      "icon": "⚙️",  "label": "Infra & deploy",
         "description": "CI/CD, env, auth, scripts, deploy work.",
         "baseline_usd": 60, "per_pr_usd": 200, "per_line_usd": 0.10},
        {"id": "design-and-deck",     "icon": "🎨", "label": "Design & decks",
         "description": "PPT/Keynote, pitch deck, slide rework, visual mockups.",
         "baseline_usd": 50},
        {"id": "video-and-clip",      "icon": "🎬", "label": "Video & clip",
         "description": "Short-form video edit, captions, TikTok/Reels prep.",
         "baseline_usd": 40},
        {"id": "copy-and-content",    "icon": "✍️",  "label": "Copy & content",
         "description": "Blog post, landing copy, email sequence, tweet thread.",
         "baseline_usd": 35},
        {"id": "market-research",     "icon": "🔍", "label": "Market research",
         "description": "Competitor scan, user research synthesis, market sizing.",
         "baseline_usd": 30},
        {"id": "strategy-talk",       "icon": "💡", "label": "Strategy talk",
         "description": "Brainstorming, roadmap thinking, pricing, GTM.",
         "baseline_usd": 25},
        {"id": "resume-and-comms",    "icon": "📄", "label": "Comms & docs",
         "description": "Resume edit, cover letter, board update, exec ghostwriting.",
         "baseline_usd": 40},
        {"id": "life-logistics",      "icon": "🎯", "label": "Life logistics",
         "description": "Trip planning, food, finance, household, personal admin.",
         "baseline_usd": 20},
        {"id": "quick-lookup",        "icon": "❓", "label": "Quick lookup",
         "description": "One-shot Q&A, definition, syntax check.",
         "baseline_usd": 5},
    ],
}


def build_demo() -> dict:
    random.seed(42)
    now = datetime.now(timezone.utc)
    monday_this = (now - timedelta(days=now.weekday())).date()
    weeks_data = []
    week_outputs = [
        {"prs_merged": 8,  "additions": 1830, "deletions":  720, "commits": 47, "reverts": 1},
        {"prs_merged": 14, "additions": 3120, "deletions": 1480, "commits": 71, "reverts": 0},
        {"prs_merged": 5,  "additions":  980, "deletions":  410, "commits": 32, "reverts": 2},
        {"prs_merged": 17, "additions": 4250, "deletions": 1670, "commits": 89, "reverts": 1},
    ]
    week_costs = [
        {"anthropic_usd": 142.30, "openai_usd": 18.40, "fixed_subscriptions_usd": 32.08},
        {"anthropic_usd": 218.75, "openai_usd": 22.10, "fixed_subscriptions_usd": 32.08},
        {"anthropic_usd":  89.50, "openai_usd": 12.30, "fixed_subscriptions_usd": 32.08},
        {"anthropic_usd": 264.20, "openai_usd": 31.50, "fixed_subscriptions_usd": 32.08},
    ]
    for i in range(4):
        wd = monday_this - timedelta(weeks=3 - i)
        w = iso_week(wd)
        cost = week_costs[i]
        total_cost = sum(cost.values())
        out = week_outputs[i]
        prs = [{"title": "feat: example PR " + str(j),
                "url": f"https://github.com/your-org/your-app/pull/{(i + 1) * 100 + j}",
                "repo": "your-org/your-app",
                "merged_at": (wd + timedelta(days=j)).isoformat()}
               for j in range(min(5, out["prs_merged"]))]
        out_dict = {**out, "repos_touched": ["your-org/your-app"], "prs": prs, "changed_files": 47}
        value_per_pr, value_per_line = 600, 0.30
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

    # Diverse synthetic sessions — every category gets at least one example.
    # Tuple: (agent, category_id, project, summary, cost, tools, role, mins(l,m,h), rates(l,m,h), quality)
    fake = [
        ("claude-code", "ship-feature",     "Pitchstack",
         "Built magic-link auth + email cooldown for the new pricing page.",   47.30, 142,
         "Senior backend engineer", (90, 180, 300), (150, 200, 280), "with-edits"),
        ("claude-code", "ship-feature",     "Pitchstack",
         "Implemented CSV import pipeline with progress events.",              19.20,  88,
         "Senior backend engineer", (60, 120, 240), (150, 200, 280), "full-replacement"),
        ("claude-code", "bug-investigation","Pitchstack",
         "Fixed Stripe webhook race that double-charged on retries.",          5.60,  44,
         "Senior backend engineer", (60, 120, 240), (180, 220, 280), "with-edits"),
        ("codex",       "ops-and-deploy",   "Pitchstack",
         "Wired GitHub Actions cron + Vercel preview deploys.",                3.40,  27,
         "DevOps engineer",         (20,  45,  90), (140, 180, 240), "full-replacement"),
        ("codex",       "ops-and-deploy",   "Pitchstack",
         "Set up Sentry + Datadog tracing on the API.",                        4.20,  29,
         "DevOps engineer",         (40,  90, 180), (140, 180, 240), "with-edits"),
        ("hermes",      "market-research",  "Competitive scan",
         "Surveyed 6 dashboards in the AI ROI space, wrote diff matrix.",      2.10,  14,
         "Product analyst",         (60, 120, 240), ( 80, 120, 180), "with-edits"),
        ("hermes",      "strategy-talk",    "v2 roadmap",
         "Talked through v2 multi-tenant data model tradeoffs.",               0.80,   6,
         "Product / staff eng",     (30,  60, 120), (180, 240, 320), "draft-only"),
        ("openclaw",    "design-and-deck",  "Investor deck v3",
         "Redrew 12 slides for Series A pitch — narrative + charts.",          3.80,  18,
         "Pitch design consultant", (90, 180, 360), (120, 180, 280), "with-edits"),
        ("openclaw",    "design-and-deck",  "Board update slides",
         "Built 5 board update slides with metric callouts.",                  1.20,  10,
         "Executive comms designer",(45,  90, 180), (100, 150, 220), "with-edits"),
        ("claude-code", "video-and-clip",   "TikTok founder vlog",
         "Cut a 60-second founder vlog with captions and B-roll.",             2.40,  22,
         "Short-form video editor", (60, 120, 180), ( 35,  55,  90), "with-edits"),
        ("claude-code", "video-and-clip",   "Demo screencap",
         "Trimmed a product demo, added subtitles + intro card.",              1.10,  12,
         "Video editor",            (30,  60, 120), ( 35,  55,  90), "full-replacement"),
        ("hermes",      "copy-and-content", "Launch email",
         "Drafted a launch announcement email — 3 variants A/B.",              0.90,   8,
         "Marketing copywriter",    (45,  90, 180), ( 60, 120, 200), "with-edits"),
        ("hermes",      "copy-and-content", "Landing page hero",
         "Rewrote landing hero copy + sub-headline against ICP feedback.",     0.60,   7,
         "Conversion copywriter",   (30,  60, 120), ( 80, 140, 220), "with-edits"),
        ("openclaw",    "resume-and-comms", "Resume tailor for Series A pitch",
         "Tailored resume for Stripe-adjacent role + cover letter.",           1.40,  11,
         "Career coach + writer",   (60,  90, 180), ( 80, 150, 250), "with-edits"),
        ("openclaw",    "resume-and-comms", "Board email",
         "Drafted weekly board update from KPI dashboard.",                    0.50,   6,
         "Executive ghostwriter",   (30,  60, 120), ( 80, 150, 250), "full-replacement"),
        ("openclaw",    "life-logistics",   "Tokyo trip planning",
         "Planned 5-day Tokyo itinerary + booked 3 restaurants via tool calls.",0.70,  12,
         "Travel agent",            (60, 120, 180), ( 40,  60, 100), "full-replacement"),
        ("openclaw",    "life-logistics",   "Weekly meal prep",
         "Recipe lookup, grocery list, ordered via tool call.",                0.15,   5,
         "Personal assistant",      ( 5,  15,  30), ( 25,  40,  60), "full-replacement"),
        ("hermes",      "quick-lookup",     "General",
         "Quick question on Postgres index strategy.",                         0.20,   3,
         "Database consultant",     ( 5,  10,  20), (150, 250, 350), "full-replacement"),
        ("hermes",      "quick-lookup",     "General",
         "What's the typo3 release cadence?",                                  0.05,   2,
         "Technical writer",        ( 3,   5,  10), ( 60,  90, 140), "full-replacement"),
        ("claude-code", "ship-feature",     "Pitchstack",
         "Added typeahead search to nav with debouncer.",                       8.40,  61,
         "Mid frontend engineer",   (30,  60, 120), (100, 140, 180), "full-replacement"),
        # --- loss-makers: real-life negative ROI examples ---
        ("claude-code", "bug-investigation","Pitchstack",
         "Asked agent to refactor auth — it broke session expiry, took 3h to revert.", 12.40, 87,
         "Senior backend engineer", (90, 180, 360), (180, 220, 280), "harmful"),
        ("codex",       "ship-feature",     "Pitchstack",
         "Spent 40 min in loops trying to fix a flaky test; gave up, fixed manually.",   8.20, 54,
         "Mid backend engineer",    (10,  20,  40), (100, 140, 180), "failed"),
        ("hermes",      "market-research",  "Funding tracker",
         "Asked for VC list — got hallucinated names, had to redo by hand.",      3.10, 12,
         "Research analyst",        (30,  60, 120), ( 80, 120, 180), "failed"),
        ("claude-code", "design-and-deck",  "Investor deck v3",
         "Tried 5 prompts for chart redesign; output worse than original each time.",1.80, 24,
         "Pitch design consultant", (45,  90, 180), (120, 180, 280), "draft-only"),
    ]
    base = datetime.now(timezone.utc)
    sessions = []
    for idx, row in enumerate(fake):
        agent, cat, proj, summary, cost, tool_count, role, mins, rates, quality = row
        d = base - timedelta(days=idx, hours=random.randint(0, 6))
        sessions.append({
            "agent": agent,
            "session_id": f"demo-{idx:04d}",
            "project": proj,
            "first_prompt": "(demo)",
            "first_event": d.isoformat(),
            "last_event": d.isoformat(),
            "user_messages": random.randint(5, 30),
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
                "value_signal": "shipped-code" if cat in ("ship-feature", "bug-investigation", "ops-and-deploy") else "shipped-artifact",
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
        "config": {"github_username": "demo-user", "hourly_rate_usd": 150,
                   "value_per_pr_usd": 600, "value_per_line_committed_usd": 0.30},
        "benchmark": {"region": "us-west", "seniority": "senior", "currency": "USD"},
        "taxonomy": DEMO_TAXONOMY,
        "weeks": weeks_data,
        "sessions": sessions,
        "sessionsTotals": {
            "totalCostUsd": round(sum(s["est_cost_usd"] for s in sessions), 2),
            "sessionCount": len(sessions),
        },
        "byCategory": summarize_by_category(sessions, DEMO_TAXONOMY),
        "byAgent": summarize_by_agent(sessions, DEMO_TAXONOMY),
        "overall": overall_summary(sessions, DEMO_TAXONOMY),
    }


def main() -> None:
    data = build_demo()
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
