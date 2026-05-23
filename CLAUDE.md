# tokenpayback — for Claude Code sessions

Self-hosted, open-source coding-AI ROI dashboard. Purpose: tell a developer or
engineering manager whether the $$$ they spend on AI tools is actually shipping code
that matters — and where the waste hides when it isn't.

## Architecture

```
config.local.yaml         # user-tunable: hourly rate, value/PR, subscriptions, GH user
tokenpayback/
  cli.py                  # `tokenpayback` entry point — scan + classify + serve
  parsers/                # one file per agent (claude_code, codex, cursor, ...)
    base.py               # Session TypedDict spec
  classify_sessions.py    # LLM single-session classifier (dual-axis: category + value_class)
  taxonomy.py             # personalized category taxonomy (LLM-induced, user-editable)
  cost.py                 # weekly cost from Anthropic + OpenAI admin APIs + fixed subs
  output.py               # weekly GitHub output via REST search API (gh CLI)
  roi.py                  # cost × output → ROI, emit reports/*.md + data.json
  value_model.py          # per-session value: role-based primary, category fallback
  role_value.py           # role × minutes × rate × quality_multiplier
  value_class.py          # ABM second axis: VA / NVA / BVA derivation
  analytics.py            # cost-accounting KPIs (NVA share, variance, cost split, ...)
  demo_data.py            # synthetic dataset for the public Vercel demo
  proxy.py                # local LLM proxy → universal capture
  dashboard/              # bundled static dashboard (mirrored to root /dashboard for Vercel)
    index.html app.js styles.css
dashboard/                # root copy — what tokenpayback.vercel.app serves
reports/                  # weekly markdown reports
.github/workflows/        # Sunday cron
```

## Two-axis session classification

Every session gets two labels from the LLM classifier (or derived back-compat):

- **`category`** — what was it (taxonomy-defined, personalized per user)
- **`value_class`** — was it worth it (VA / NVA / BVA, per Cooper & Kaplan's ABM):
  - **VA** value-added: produced something the user would pay for if itemized
  - **NVA** non-value-added: burned tokens with no usable output (retry, harmful, failed)
  - **BVA** business-value-added: necessary overhead (research, scaffolding the user rewrote)

`value_class.py` provides `derive_value_class(classification)` — a transparent
mapping from `replacement_quality` + `value_signal` + category-id heuristic. Used
both as classifier fallback and as migration path for already-classified sessions.

## ROI formula (legacy weekly path, in roi.py)

```
value = prs_merged * value_per_pr
      + lines_added * value_per_line * 0.5
      - reverts * value_per_pr
roi   = value / cost
```

Per-session valuation runs through `value_model.estimate_session_value`:
role-based when LLM supplied minutes+rate+quality; category-baseline otherwise.

## Analytics layer (analytics.py)

All cost-accounting KPIs live in `analytics.py`, every formula commented next to
the code. Built on the dual-axis classification + the existing role-based valuation.

| KPI | Framework source | What it answers |
|---|---|---|
| `nva_summary` | ABM (Cooper & Kaplan 1991) | how much of your $ was waste |
| `weekly_variance` | Standard costing (ACCA/CIMA) | yield/rate/efficiency drift WoW |
| `cost_split` | RCA / GPK | proportional vs fixed; sub utilization |
| `causality_score` | RCA principle of causality | how much of spend is traceable |
| `value_stream` | Lean / Maskell | cost per project (one VSC per workflow) |
| `cross_tool_redundancy` | Ledger original | which subs overlap on the same work |
| `attended_unattended` | Ledger original | % sessions fully autonomous |
| `cost_parity_highlight` | Human ↔ AI parity | the hero "$X saved vs hiring it out" |

Output is attached to `data["analytics"]` and rendered by `app.js`. Adding a new
KPI: write the function in `analytics.py`, wire it into `cli._build_analytics`
and `roi.render_dashboard_json` (both branches), add a render function in `app.js`,
add a section to `index.html`. Update `demo_data.build_demo` so the public demo
exercises it.

## Common queries

```bash
# rerun pipeline (full: scan + classify + serve)
.venv/bin/tokenpayback

# just scan + classify (no browser)
.venv/bin/tokenpayback scan

# regenerate demo data for the Vercel deploy
.venv/bin/python -m tokenpayback.demo_data > dashboard/data.json
cp dashboard/data.json tokenpayback/dashboard/data.json   # keep both in sync

# preview dashboard locally
python3 -m http.server --directory dashboard
```

## Editing rules

- **Keep heuristics transparent** — every formula in the dashboard must trace to a
  short comment in the source. The moment any number feels "magic" the whole tool
  loses trust. Show derivations in the UI when reasonable.
- **No telemetry, no tracking, no "phone home"** — this product's positioning is
  anti-SaaS. Don't break it.
- **The dashboard's hero must answer ONE question** — "is this paying off?" Every
  UI change should be tested against that. New cards land below the hero.
- **Two dashboards in sync** — `dashboard/` (root, served by Vercel) and
  `tokenpayback/dashboard/` (bundled, served by `tokenpayback serve`) must be
  identical. Always `cp` after any change.
- **Self-host first** — never assume the user has Vercel / cloud access in
  scripts. Local Python venv must work.
- **Prefer adding to roadmap (README) over implementing speculative features.**

## Style hints for new features

- New parsers: subclass `BaseParser`, set `agent_name` + `data_root` + implement
  `parse_sessions`. Register in `parsers/__init__.py`.
- New value_class signals: extend `_QUALITY_MAP` / `_SIGNAL_MAP` /
  `_VA_KEYWORDS` / `_BVA_KEYWORDS` in `value_class.py`. Document the why in the
  module docstring.
- New analytics KPIs: function in `analytics.py` with formula-in-comment.
  Wire into both pipeline paths. Add a render function + section.
- Anything that could feel like "extracting" the user's data → put it behind
  explicit opt-in env vars.
