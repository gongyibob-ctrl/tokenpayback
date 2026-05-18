# tokenpayback — for Claude Code sessions

Self-hosted, open-source coding-AI ROI dashboard. Purpose: tell a developer or
engineering manager whether the $$$ they spend on AI tools is actually shipping code
that matters.

## Architecture

```
config.local.yaml         # user-tunable: hourly rate, value/PR, subscriptions, GH user
scripts/
  cost.py                 # weekly cost from Anthropic + OpenAI admin APIs + fixed subs
  output.py               # weekly GitHub output via REST search API (gh CLI)
  roi.py                  # cost × output → ROI, emit reports/*.md + dashboard/data.json
  util.py                 # config loading, ISO week math
dashboard/                # static HTML/CSS/JS, reads data.json at fetch time
  index.html app.js styles.css data.json
reports/                  # weekly markdown reports
.github/workflows/        # Sunday cron
```

## ROI formula (live in roi.py)

```
value = prs_merged * value_per_pr
      + lines_added * value_per_line * 0.5
      - reverts * value_per_pr
roi   = value / cost
```

## Common queries

```bash
# rerun pipeline
.venv/bin/python scripts/roi.py

# only fetch costs
.venv/bin/python scripts/cost.py

# only fetch GitHub output
.venv/bin/python scripts/output.py

# preview dashboard locally
python3 -m http.server --directory dashboard
```

## Editing rules

- **Keep heuristics transparent** — the moment any number is "magic", users distrust the whole tool. New estimators must explain their factors in `config.local.yaml` AND show in the dashboard's "heuristics" panel
- **No telemetry, no tracking, no "phone home"** — this product's positioning is anti-SaaS. Don't break it
- **The dashboard's hero must answer ONE question** — "is this paying off?" — every UI change should be tested against that
- **Prefer adding to roadmap (README) over implementing speculative features**
- **Self-host first** — never assume the user has Vercel / cloud access in scripts. Local Python venv must work

## Style hints for new features

- Cost sources: add a function in `cost.py`, wire it into `collect()`. Always return None on failure (so missing data shows as `·` not `$0`)
- Output sources: add a function in `output.py` returning per-week dicts
- New value estimators: add to `estimate_value_usd()` with a config-tunable factor
- Anything that could feel like "extracting" the user's data → put it behind explicit opt-in env vars
