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


def _build_system_prompt(taxonomy: dict) -> str:
    """Compose the SYSTEM prompt from a user-specific taxonomy."""
    cats = taxonomy.get("categories") or []
    lines = ['You categorize ONE session of AI agent activity using THIS user\'s personal taxonomy.']
    lines.append('')
    lines.append('Available categories (pick exactly one):')
    for c in cats:
        lines.append(f"  - {c['id']:<22} {c.get('icon','•')}  {c.get('label','?')} — {c.get('description','')}")
    lines.append('')
    lines.append('Return JSON exactly:')
    lines.append('{')
    lines.append('  "category": "<one of the ids above>",')
    lines.append('  "project": "<short phrase, prefer the user\'s naming, <=30 chars>",')
    lines.append('  "summary": "<one sentence, <=120 chars, what actually happened>",')
    lines.append('  "value_signal": "<shipped-code|shipped-artifact|info-gathered|decided|answered|no-progress>",')
    lines.append('  "main_artifact": "<short phrase describing the most concrete output, or (none)>"')
    lines.append('}')
    lines.append('')
    lines.append('Be decisive. Even ambiguous sessions get a closest-fit category — never invent new ids.')
    return '\n'.join(lines)


# Kept for back-compat — generic fallback if no taxonomy supplied
SYSTEM = """You categorize one AI agent session. Return JSON: {category, project, summary, value_signal, main_artifact}.
Use these category ids: code-shipped, bug-fixed, infra-changed, info-gathered, ideas-explored, life-shipped, question-answered.
Pick the closest fit."""


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


def classify_session(s: dict, taxonomy: dict | None = None) -> dict:
    provider, base_url, api_key, model = _detect_provider()
    system_prompt = _build_system_prompt(taxonomy) if taxonomy else SYSTEM
    blob = (
        f"Agent: {s.get('agent','?')}\n"
        f"Project path: {s.get('project','')}\n"
        f"First user prompt: {s.get('first_prompt','')[:600]}\n"
        f"User messages in session: {s.get('user_messages',0)}\n"
        f"Tool calls: {s.get('tool_counts',{})}\n"
        f"Files touched (sample): {(s.get('files_touched') or [])[:10]}\n"
        f"Bash commands (sample): {(s.get('bash_sample') or [])[:8]}\n"
        f"Estimated cost: ${s.get('est_cost_usd', 0)}"
    )
    valid_ids = {c["id"] for c in (taxonomy.get("categories") or [])} if taxonomy else set()
    fallback_id = next(iter(valid_ids), "chat-misc")
    try:
        if provider == "anthropic":
            result = _classify_anthropic(system_prompt, blob, base_url, api_key, model)
        else:
            result = _classify_openai_compatible(system_prompt, blob, base_url, api_key, model)
    except Exception as e:
        print(f"  ! classify {s.get('session_id','')[:8]} failed: {e}", file=sys.stderr)
        return {"category": fallback_id, "project": (s.get("project") or "")[:30],
                "summary": "(failed to classify)",
                "value_signal": "no-progress", "main_artifact": "(none)"}
    category = result.get("category", "")
    # Coerce to a valid id if taxonomy is provided and the LLM made one up
    if valid_ids and category not in valid_ids:
        category = fallback_id
    return {
        "category": category or fallback_id,
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
