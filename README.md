<h1 align="center">tokenpayback</h1>

<p align="center">
  <strong>Your AI activity ledger — every agent, every activity, 100% local.</strong><br/>
  <em>One CLI. Reads every coding agent on your machine. Tells you what your tokens did.</em>
</p>

<p align="center">
  <a href="https://github.com/gongyibob-ctrl/tokenpayback/blob/main/LICENSE"><img src="https://img.shields.io/github/license/gongyibob-ctrl/tokenpayback?style=flat-square" alt="MIT"></a>
  <a href="https://pypi.org/project/tokenpayback/"><img src="https://img.shields.io/pypi/v/tokenpayback?style=flat-square&color=blue" alt="PyPI"></a>
  <a href="https://github.com/gongyibob-ctrl/tokenpayback"><img src="https://img.shields.io/github/stars/gongyibob-ctrl/tokenpayback?style=flat-square" alt="stars"></a>
  <a href="#"><img src="https://img.shields.io/badge/runs-locally-green?style=flat-square" alt="local"></a>
  <a href="#"><img src="https://img.shields.io/badge/data-never_leaves_your_mac-success?style=flat-square" alt="private"></a>
</p>

<p align="center">
  <a href="https://tokenpayback.vercel.app">🌐 Live demo</a>
  ·
  <a href="#install">📦 Install</a>
  ·
  <a href="#supported-agents">🤖 Supported agents</a>
  ·
  <a href="#privacy">🔒 Privacy</a>
</p>

---

## The problem

You're paying for Claude Code + Codex + maybe Cursor, Hermes, OpenClaw, OpenHuman. Each
agent keeps its own session log on your disk. **No tool tells you what those tokens did
across all of them.**

Cost dashboards show you how many tokens you burned. None of them tell you:

- Was this a *new feature* or a *brainstorm*?
- Did the agent finally fix the bug or just dance around it?
- How much of the spend went into shipping code vs. answering questions vs. organizing your life?

`tokenpayback` reads every agent's local data, classifies every session via LLM, and
shows you the answer. **It runs on your machine. Data never leaves.**

```
This week — what your $264 of AI tokens did
─────────────────────────────────────────────
🚢 Code shipped         14 PRs · 3,120 lines
🐛 Bug fixed             3 sessions
🧹 Code cleaned          2 sessions
⚙️  Infra changed         5 sessions
📚 Info gathered         6 sessions
💡 Ideas explored        4 sessions
🎯 Life shipped          2 sessions (resumes, video drafts)
❓ Question answered     11 sessions
```

Every category gets credit. Asking a question and getting an answer **is** value.
Sketching out an idea **is** value. Code is just one shape of value.

---

## Supported agents

`tokenpayback` auto-detects which of these you have installed and reads each one:

| Agent | Local path | Status |
|---|---|---|
| **Claude Code** | `~/.claude/projects/` | ✅ Full support |
| **Codex CLI** | `~/.codex/sessions/` | ✅ Full support |
| **Hermes** (Nous Research) | `~/.hermes/` | 🟡 Beta — SQLite reader |
| **OpenClaw** 🦞 | `~/.openclaw/` or `~/Library/Application Support/OpenClaw/` | 🟡 Beta — auto-detect |
| **OpenHuman** (tinyhumans.ai) | `~/.openhuman/` | 🟡 Beta — SQLite reader |
| **Cursor** | `~/Library/Application Support/Cursor/User/` | 🟡 Beta — composer data |

Each agent has its own parser file in `tokenpayback/parsers/`. **Adding a new agent =
one file.** PRs welcome.

---

## Install

Requires Python 3.9+.

```bash
pipx install tokenpayback     # recommended (isolated env)
# or
pip install --user tokenpayback
```

You'll need an LLM API key for session classification — set ONE:

```bash
export ANTHROPIC_API_KEY=sk-ant-...        # recommended — you probably already have one
export OPENAI_API_KEY=sk-...
export LITELLM_API_KEY=...
export LITELLM_BASE_URL=https://your-proxy/v1
export LITELLM_MODEL=gpt-4o-mini
```

Skip classification entirely with `tokenpayback --no-classify` (still shows cost & agent activity).

## Run

```bash
tokenpayback                  # scan all agents + classify + open dashboard in browser
tokenpayback scan             # just scan & write data
tokenpayback serve            # serve existing data on local port
```

First run takes ~60 seconds (LLM classifies each session). Subsequent runs use cache.

---

## Categories are personalized — not hardcoded

The first time you run `tokenpayback`, the LLM looks at a sample of your real sessions
and **induces categories that fit how YOU use AI**. An engineer's taxonomy will look
very different from a creator's, a founder's, or a data scientist's.

```bash
tokenpayback                    # first run auto-generates ~/.tokenpayback/taxonomy.yaml
tokenpayback taxonomy show      # see what it came up with
tokenpayback taxonomy edit      # rename categories, change baselines, add new ones
tokenpayback taxonomy regen     # re-discover from scratch
```

Example: an engineer might end up with something like:

```yaml
categories:
  - id: ship-feature
    icon: 🚢
    label: Ship feature
    description: Completing a new product feature end-to-end with commits
    baseline_usd: 80
    per_pr_usd: 700
    per_line_usd: 0.30
  - id: cf-worker-debug
    icon: 🛠
    label: CF Worker debugging
    description: Diagnosing issues in Cloudflare Worker deploys
    baseline_usd: 60
  ...
```

A content creator might end up with `tiktok-edit`, `research`, `voiceover-prep`, etc.
Everyone's dashboard speaks their own language.

**No baseline is $0 by default.** Asking a question and getting an answer IS value.
The point is to make the assumptions **visible**, not to hide them behind a SaaS pricing model.

---

## Privacy

- ❌ No tracking, no analytics, no phone-home
- ❌ No account, no email, no sign-up
- ❌ Your session data NEVER leaves your machine
- ✅ The only outbound calls: (1) your chosen LLM for classification, (2) Anthropic/OpenAI usage APIs *only if you opt in*, (3) GitHub API *only if you opt in*
- ✅ Open source. Read every line.

The LLM classification step sends a one-paragraph summary of each session (first prompt,
tool call counts, sample bash commands) — not full prompts or code.
Skip it entirely with `--no-classify`.

---

## How it works

```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ ~/.claude/      │  │ ~/.codex/       │  │ ~/.hermes/      │  │ ~/Library/.../  │
│ projects/       │  │ sessions/       │  │ *.db (SQLite)   │  │ Cursor/User/    │
│ *.jsonl         │  │ *.jsonl         │  │                 │  │ state.vscdb     │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                    │                    │                    │
         └────────────────────┴─────┬──────────────┴────────────────────┘
                                    │
                            tokenpayback/parsers
                                    │
                                    ▼
                       ┌─────────────────────────┐
                       │  normalized Session[]   │
                       │   agent, project,       │
                       │   tokens, tool_counts,  │
                       │   est_cost_usd...       │
                       └────────────┬────────────┘
                                    │
                                    ▼  LLM classifier
                       ┌─────────────────────────┐
                       │   + category, summary,  │
                       │     value_signal        │
                       └────────────┬────────────┘
                                    │
                       ┌────────────┴───────────┐
                       │                         │
                       ▼                         ▼
              activity ledger            engineering ROI
              (every category)           (GitHub PR/commits)
                       │                         │
                       └────────────┬────────────┘
                                    ▼
                       local dashboard (localhost)
```

---

## What it's not

- **Not a SaaS.** No cloud, no signup, nothing to sell you.
- **Not a tracker.** It cares about *your* spend, not your activity in aggregate.
- **Not an attribution oracle.** Value heuristics are estimates. We're transparent about it.
- **Not a replacement for evals.** Use Braintrust / Langfuse / Inspect for output quality.

---

## Roadmap

For v0.3:
- [ ] Sankey diagram: from agent → category → outcome
- [ ] Time-series of how your category mix shifts week-over-week
- [ ] Per-tool cost breakdown (which Bash patterns cost you the most?)
- [ ] Native Mac app via Tauri or pywebview (no more "open browser" feel)
- [ ] LLM-graded value (replace flat baselines with case-by-case judgment)

PRs welcome. Open an issue first for anything non-trivial.

---

## Contributing

Add support for a new agent:

```bash
git clone https://github.com/gongyibob-ctrl/tokenpayback.git
cd tokenpayback
python3 -m venv .venv && .venv/bin/pip install -e .
# Create tokenpayback/parsers/<your_agent>.py — subclass BaseParser
# Register in tokenpayback/parsers/__init__.py ALL_PARSERS
# Test: .venv/bin/tokenpayback scan
```

Each parser is ~50 lines. See `parsers/claude_code.py` as the reference.

Code style: small modules, no premature abstraction, transparent heuristics.

---

## Why "tokenpayback"?

Because the question isn't *"how many tokens did I burn?"* — every tool answers that.
The question is *"did those tokens come back as something?"* — and "something" doesn't
have to be code. A clear answer, a written note, a fixed bug, a planned weekend —
those count too.

Built by [@gongyibob-ctrl](https://github.com/gongyibob-ctrl). Made in a weekend, open
sourced because it shouldn't have to be a startup.

---

## License

MIT. Use it, fork it, sell improvements built on it.
