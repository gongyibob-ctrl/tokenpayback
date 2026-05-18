<h1 align="center">tokenpayback</h1>

<p align="center">
  <strong>Are your AI tokens paying off?</strong><br/>
  <em>A 100% local CLI that turns your Claude Code sessions into a ROI dashboard — in 60 seconds.</em>
</p>

<p align="center">
  <a href="https://github.com/gongyibob-ctrl/tokenpayback/blob/main/LICENSE"><img src="https://img.shields.io/github/license/gongyibob-ctrl/tokenpayback?style=flat-square" alt="MIT"></a>
  <a href="https://pypi.org/project/tokenpayback/"><img src="https://img.shields.io/pypi/v/tokenpayback?style=flat-square&color=blue" alt="PyPI"></a>
  <a href="https://github.com/gongyibob-ctrl/tokenpayback"><img src="https://img.shields.io/github/stars/gongyibob-ctrl/tokenpayback?style=flat-square" alt="stars"></a>
  <a href="#"><img src="https://img.shields.io/badge/runs-locally-green?style=flat-square" alt="local"></a>
  <a href="#"><img src="https://img.shields.io/badge/data-stays_on_your_mac-success?style=flat-square" alt="private"></a>
</p>

<p align="center">
  <a href="https://tokenpayback.vercel.app">🌐 Live demo</a>
  ·
  <a href="#install">📦 Install</a>
  ·
  <a href="#how-it-works">🔧 How it works</a>
  ·
  <a href="#privacy">🔒 Privacy</a>
</p>

---

## The problem

You're paying for Cursor (~$20/mo) + Copilot (~$19/mo) + Claude API (variable) + maybe a Claude Max plan ($100/mo) — and you have **no idea** if it's actually shipping more code.

Your CFO / your boss / your inner skeptic keeps asking *"is this AI spend paying off?"* and you've been answering with vibes.

`tokenpayback` reads the session logs Claude Code already keeps in `~/.claude/projects/` and gives you a real number:

```
This week:  spent $264 → estimated $10,830 value → ROI 41×
Tokens went to:   new-feature 47%   refactor 23%   bug-fix 18%   research 12%
Top project:      your-app                $182  (8 PRs, +3,120 lines)
```

It's a heuristic — but it's a heuristic **you can see and tune**. Everything is transparent (`config.local.yaml`). Everything stays on your Mac.

---

## What it actually does

For every session in `~/.claude/projects/**/*.jsonl`:

1. **Parses** — extracts prompts, tool calls, files touched, exact token usage
2. **Classifies via LLM** — what was this session actually doing? Picks one of:
   `new-feature` / `extend-feature` / `bug-fix` / `debug` / `refactor` / `config-ops` / `research` / `brainstorm` / `personal-task` / `chat-misc`
3. **Computes ROI per week** — combines token spend with your GitHub output (PRs merged, lines added/deleted, reverts) via a transparent formula
4. **Serves a local dashboard** — opens in your browser at `http://localhost:PORT/`, no cloud

All data persists in `~/.tokenpayback/`. **Nothing leaves your machine.**

---

## Install

Requires Python 3.9+.

```bash
pipx install tokenpayback     # recommended (isolated)
# or
pip install --user tokenpayback
```

You'll need an LLM API key for session classification — set ONE of these:

```bash
export ANTHROPIC_API_KEY=sk-ant-...        # recommended — you probably already have one
export OPENAI_API_KEY=sk-...
# or any OpenAI-compatible endpoint:
export LITELLM_API_KEY=...
export LITELLM_BASE_URL=https://your-proxy/v1
export LITELLM_MODEL=gpt-4o-mini
```

Or skip classification entirely:

```bash
tokenpayback --no-classify   # faster, no API key needed, still shows cost & GitHub output
```

## Run

```bash
tokenpayback                  # scan + classify + serve + open browser
tokenpayback scan             # just scan & write data
tokenpayback serve            # serve existing data on local port
```

First run takes ~60 seconds (LLM call per session). Subsequent runs are instant for cached sessions.

---

## Optional: real cost numbers from your API providers

By default we approximate weekly cost from your fixed monthly subscriptions. For exact API spend, drop in an admin key:

```bash
export ANTHROPIC_ADMIN_KEY=sk-ant-admin-...  # console.anthropic.com/settings/admin-keys
export OPENAI_ADMIN_KEY=sk-admin-...         # platform.openai.com/settings/organization
```

These are read-only keys — they only fetch usage reports, never modify anything.

---

## How it works

```
┌─────────────────────────┐
│ ~/.claude/projects/     │   parse JSONL → extract:
│   *.jsonl               │   ─ prompts, tool calls, tokens, files touched
└────────────┬────────────┘
             │
             ▼
   ┌──────────────────────┐    LLM classifier   ┌──────────────────────┐
   │  raw session data    │ ─────────────────▶  │  classified sessions │
   └──────────────────────┘  (category, project,│  + per-session ROI   │
                              summary, value)    └──────────┬───────────┘
                                                            │
   ┌──────────────────────┐                                 │
   │  Anthropic / OpenAI  │  weekly $$$ ───┐                │
   │  admin APIs          │                │                │
   └──────────────────────┘                ▼                ▼
   ┌──────────────────────┐         ┌────────────────────────────┐
   │  GitHub search API   │ ──────▶ │  ROI dashboard (localhost) │
   │  (PRs / commits)     │  weekly │  data.json in ~/.tokenpayback│
   └──────────────────────┘  output └────────────────────────────┘
```

The ROI formula is intentionally simple and visible. Tune to your reality:

```python
value_usd  =  prs_merged × value_per_pr             # default $600
            + lines_added × value_per_line × 0.5    # default $0.30
            − reverts × value_per_pr                # penalty
roi        =  value_usd / total_weekly_cost
```

Edit `~/.tokenpayback/config.yaml` (or `./config.local.yaml`) to change the multipliers.

---

## Privacy

This is a privacy-first tool. The whole point is to NOT do what other observability tools do.

- ❌ No tracking, no analytics, no phone-home
- ❌ No account, no email, no sign-up
- ❌ Your session data NEVER leaves your machine
- ✅ The only outbound calls are: (1) your chosen LLM for classification, (2) Anthropic/OpenAI usage APIs if you opt in, (3) GitHub API if you opt in
- ✅ Open source. Read every line.

The LLM classification step sends a one-paragraph summary of each session (first prompt, tool call counts, sample bash commands) — not full prompts or code. Skip it entirely with `--no-classify`.

---

## What it's not

- **Not a SaaS.** No cloud. We have nothing to sell you.
- **Not a tracker.** It cares about *your* spend, not your activity in aggregate.
- **Not an attribution oracle.** Linking "AI did X" → "$ saved Y" is an estimate, not a measurement. We're transparent about that.
- **Not a replacement for evals.** Use Braintrust / Langfuse / DSPy / Inspect for output quality. This is the spend layer.

---

## Roadmap

Things on the table for v0.2 — file issues for what you want:

- [ ] Cursor & Codex CLI session ingestion (today: Claude Code only)
- [ ] Per-task-type ROI ("you spend $X on testing PRs and they always merge — keep doing that")
- [ ] Bash subcommand profiler (`tokenpayback bash` — find the most expensive Bash patterns)
- [ ] LLM-graded PR value (replace flat $600/PR with case-by-case)
- [ ] Native macOS app via Tauri or pywebview (no more "open the browser" feel)
- [ ] Team mode — opt-in shared aggregation
- [ ] Sankey / time-series charts

PRs welcome. Open an issue first for anything non-trivial.

---

## Contributing

```bash
git clone https://github.com/gongyibob-ctrl/tokenpayback.git
cd tokenpayback
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/tokenpayback --no-classify    # smoke test on your own ~/.claude/
```

Code style: small modules, no premature abstraction, transparent heuristics. If you find yourself hiding numbers behind clever code, stop and write a comment about *why* the number is what it is.

---

## Why "tokenpayback"?

Because the question isn't *"how many tokens did I burn?"* — every tool answers that. The question is *"did those tokens come back as something?"*

Made by [@gongyibob-ctrl](https://github.com/gongyibob-ctrl) — built in a weekend, shipped because it shouldn't have to be a startup.

---

## License

MIT. Use it, fork it, sell improvements built on it. Just don't blame me when the ROI number is uncomfortable.
