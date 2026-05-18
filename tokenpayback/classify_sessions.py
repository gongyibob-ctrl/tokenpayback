"""Classify Claude Code sessions — what was actually being done.

Supports multiple LLM providers (auto-detected by env vars):
- ANTHROPIC_API_KEY → Anthropic Messages API (default)
- OPENAI_API_KEY → OpenAI chat completions
- PAIGOD_API_KEY → Novita paigod proxy (private use)
- LITELLM_BASE_URL + LITELLM_API_KEY → any OpenAI-compatible endpoint
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

import requests

from .parse_claude import collect_all


SYSTEM = """You categorize a developer's Claude Code coding session based on its content.

Return JSON with these fields:
- category: ONE of [
    "new-feature",         // building something new from scratch
    "extend-feature",      // adding to an existing feature
    "bug-fix",             // fixing a known bug
    "debug",               // investigating / figuring out a problem (not yet fixing)
    "refactor",            // reorganizing existing code without changing behavior
    "config-ops",          // deploy/cron/git/CI/auth/env/install — configuration, no real code
    "research",            // exploring a topic, reading docs, market scan, competitor analysis
    "brainstorm",          // product/strategy/idea discussion, no code change
    "personal-task",       // non-engineering: organize files, write docs, video drafts, etc.
    "chat-misc"            // small talk, status check, or unclassifiable
  ]
- project: ONE-PHRASE name of the project / topic (<=30 chars, prefer the user's own naming)
- summary: ONE SENTENCE (<=120 chars) of what actually happened
- value_signal: ONE of ["shipped-code", "researched", "no-progress", "info-gathered"]
- main_artifact: ONE phrase describing the most concrete output (e.g. "lark-radar-bot CF Worker", "weekly digest script", "(none)")

Be decisive — pick the closest category even if imperfect. Look at the first user prompt + tool usage pattern + project path."""


def _load_paigod_credentials_file() -> None:
    """If user has ~/.config/paigod/credentials, lift it into the env (don't override existing)."""
    cred = Path.home() / ".config" / "paigod" / "credentials"
    if not cred.exists():
        return
    try:
        for line in cred.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    except Exception:
        pass


def _detect_provider() -> tuple[str, str, str, str | None]:
    """Returns (provider_name, base_url, api_key, model)."""
    _load_paigod_credentials_file()
    if os.environ.get("ANTHROPIC_API_KEY"):
        return ("anthropic", "https://api.anthropic.com/v1", os.environ["ANTHROPIC_API_KEY"], "claude-haiku-4-5-20251001")
    if os.environ.get("PAIGOD_API_KEY"):
        return ("paigod", os.environ.get("PAIGOD_BASE_URL", "https://apiproxy.paigod.work/v1"),
                os.environ["PAIGOD_API_KEY"], os.environ.get("PAIGOD_DEFAULT_MODEL", "pa/gpt-5.5"))
    if os.environ.get("OPENAI_API_KEY"):
        return ("openai", "https://api.openai.com/v1", os.environ["OPENAI_API_KEY"], "gpt-4o-mini")
    if os.environ.get("LITELLM_API_KEY"):
        return ("litellm", os.environ.get("LITELLM_BASE_URL", ""), os.environ["LITELLM_API_KEY"],
                os.environ.get("LITELLM_MODEL", "gpt-4o-mini"))
    raise RuntimeError(
        "No LLM provider configured. Set one of: ANTHROPIC_API_KEY, OPENAI_API_KEY, PAIGOD_API_KEY, or LITELLM_API_KEY."
    )


def _classify_anthropic(system: str, user: str, base_url: str, api_key: str, model: str) -> dict:
    resp = requests.post(
        f"{base_url}/messages",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
        json={
            "model": model,
            "max_tokens": 400,
            "system": system,
            "messages": [{"role": "user", "content": user + "\n\nReturn ONLY a JSON object, no markdown fence."}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    text = resp.json()["content"][0]["text"]
    return _extract_json(text)


def _classify_openai_compatible(system: str, user: str, base_url: str, api_key: str, model: str) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_tokens": 400,
    }
    if "gpt-5" not in model and "o1" not in model and "o3" not in model:
        payload["temperature"] = 0.1
        payload["response_format"] = {"type": "json_object"}
    resp = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"]
    return _extract_json(text)


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        s, e = text.find("{"), text.rfind("}")
        if s >= 0 and e > s:
            return json.loads(text[s : e + 1])
        raise


def classify_session(s: dict) -> dict:
    provider, base_url, api_key, model = _detect_provider()
    blob = (
        f"Project path: {s['project']}\n"
        f"First user prompt: {s['first_prompt']}\n"
        f"User messages in session: {s['user_messages']}\n"
        f"Tool calls: {s['tool_counts']}\n"
        f"Files touched (sample): {s['files_touched'][:10]}\n"
        f"Bash commands (sample): {s['bash_sample'][:8]}\n"
        f"Estimated cost: ${s['est_cost_usd']}"
    )
    try:
        if provider == "anthropic":
            result = _classify_anthropic(SYSTEM, blob, base_url, api_key, model)
        else:
            result = _classify_openai_compatible(SYSTEM, blob, base_url, api_key, model)
    except Exception as e:
        print(f"  ! classify {s['session_id'][:8]} failed: {e}", file=sys.stderr)
        return {"category": "chat-misc", "project": s["project"][:30], "summary": "(failed to classify)",
                "value_signal": "no-progress", "main_artifact": "(none)"}
    return {
        "category": result.get("category", "chat-misc"),
        "project": (result.get("project") or "")[:30],
        "summary": (result.get("summary") or "")[:140],
        "value_signal": result.get("value_signal", "info-gathered"),
        "main_artifact": (result.get("main_artifact") or "")[:60],
    }


def main(output_path: Path | None = None) -> Path:
    sessions = collect_all()
    print(f"# {len(sessions)} sessions to classify", file=sys.stderr)
    enriched = []
    for s in sessions:
        c = classify_session(s)
        s["classification"] = c
        enriched.append(s)
        print(
            f"  [{c['category']:<14}] {c['project']:<25} | ${s['est_cost_usd']:>6.2f} | {c['summary']}",
            file=sys.stderr,
        )
    out = output_path or (Path.cwd() / "sessions.json")
    out.write_text(json.dumps(enriched, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"wrote {out}", file=sys.stderr)
    return out


if __name__ == "__main__":
    main()
