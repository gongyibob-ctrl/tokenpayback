"""Codex CLI parser — reads ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl

Notes on Codex CLI's format (as of OpenAI Codex CLI 0.x — verified May 2026):
- Events: {timestamp, type, payload}
- type = "session_meta" (once) — payload has cwd, model_provider, cli_version
- type = "response_item" with payload.type in:
    - "message" (role: user|developer|assistant)
    - "function_call" / "function_call_output" — tool invocations
    - "reasoning" — model reasoning chunks
- type = "event_msg" with payload.type "task_started" / "task_complete" / "token_count" / ...
- token_count events only report rate-limit percent, NOT raw tokens — we estimate cost
  from message content length (rough but useful for relative attribution).
- Session names live in ~/.codex/session_index.jsonl (`thread_name` field)
"""
from __future__ import annotations
import json
import sys
from collections import Counter
from pathlib import Path

from .base import BaseParser, Session


CODEX_ROOT = Path.home() / ".codex"
SESSIONS_DIR = CODEX_ROOT / "sessions"
SESSION_INDEX = CODEX_ROOT / "session_index.jsonl"


def _load_thread_names() -> dict[str, str]:
    """Map session id → thread_name."""
    out: dict[str, str] = {}
    if not SESSION_INDEX.exists():
        return out
    try:
        for line in SESSION_INDEX.read_text().splitlines():
            try:
                d = json.loads(line)
                sid = d.get("id")
                name = d.get("thread_name")
                if sid and name:
                    out[sid] = name
            except json.JSONDecodeError:
                continue
    except Exception:
        pass
    return out


class CodexParser(BaseParser):
    agent_name = "codex"
    display_name = "Codex CLI"
    data_root = ".codex/sessions"

    def parse_sessions(self) -> list[Session]:
        if not SESSIONS_DIR.exists():
            return []
        thread_names = _load_thread_names()
        out: list[Session] = []
        for f in SESSIONS_DIR.rglob("rollout-*.jsonl"):
            try:
                s = self._parse_one(f, thread_names)
            except Exception as e:
                print(f"  ! codex parse {f.name} failed: {e}", file=sys.stderr)
                continue
            if s["user_messages"] > 0:
                out.append(s)
        return out

    def _parse_one(self, path: Path, thread_names: dict[str, str]) -> Session:
        session_id = ""
        first_prompt = ""
        first_event_time = None
        last_event_time = None
        cwd = ""
        tool_counts: Counter = Counter()
        files_touched: set[str] = set()
        bash_cmds: list[str] = []
        user_msgs = 0
        char_in = char_out = 0  # for cost estimate
        model_provider = "unknown"

        with open(path) as f:
            for line in f:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = d.get("timestamp")
                if ts and not first_event_time:
                    first_event_time = ts
                if ts:
                    last_event_time = ts
                pl = d.get("payload") or {}
                top_type = d.get("type")
                pt = pl.get("type", "")

                if top_type == "session_meta":
                    session_id = pl.get("id") or path.stem
                    cwd = pl.get("cwd") or ""
                    model_provider = pl.get("model_provider") or model_provider

                if pt == "message":
                    role = pl.get("role", "")
                    content = pl.get("content", [])
                    text = ""
                    if isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict):
                                text += c.get("text", "") or c.get("content", "") or ""
                    elif isinstance(content, str):
                        text = content
                    if role == "user":
                        user_msgs += 1
                        if not first_prompt:
                            first_prompt = text.strip()[:600]
                        char_in += len(text)
                    elif role == "assistant":
                        char_out += len(text)

                if pt == "function_call":
                    name = pl.get("name", "?")
                    tool_counts[name] += 1
                    if name == "exec_command":
                        try:
                            args = json.loads(pl.get("arguments", "") or "{}")
                            cmd = (args.get("cmd") or "")[:120]
                            if cmd:
                                bash_cmds.append(cmd)
                        except Exception:
                            pass

                if pt == "agent_message":
                    msg = pl.get("message", "")
                    if isinstance(msg, str):
                        char_out += len(msg)

                # Reasoning chunks — sometimes huge, billed as output tokens
                if pt == "reasoning":
                    text = pl.get("text") or pl.get("content") or ""
                    if isinstance(text, str):
                        char_out += len(text)

                # Function call outputs — billed as input on the NEXT turn (cached or not)
                if pt == "function_call_output":
                    output = pl.get("output") or ""
                    if isinstance(output, dict):
                        output = output.get("content") or output.get("text") or ""
                    if isinstance(output, str):
                        char_in += len(output)

                # function_call args — billed as input
                if pt == "function_call":
                    args = pl.get("arguments") or ""
                    if isinstance(args, str):
                        char_in += len(args)

        # Conversion: ~3 chars/token for English+code (more conservative than 4)
        # GPT-5 pricing: $1.25/M input, $10/M output (Sept 2025 rates)
        # Add a floor so tiny sessions still show some cost (the JSONL never
        # captures system prompts or model-side cache reads — easily 5-10× the
        # raw char count we see).
        tokens_in = max(char_in / 3, 0)
        tokens_out = max(char_out / 3, 0)
        # Empirical correction factor — observed JSONL undercount vs OpenAI bill
        ESTIMATE_CORRECTION = 4.0
        est_cost = (tokens_in * 1.25e-6 + tokens_out * 10e-6) * ESTIMATE_CORRECTION

        thread_name = thread_names.get(session_id, "")
        project = thread_name or (cwd or path.parent.name)

        return Session(
            agent="codex",
            session_id=session_id or path.stem,
            project=project,
            first_prompt=first_prompt,
            first_event=first_event_time,
            last_event=last_event_time,
            user_messages=user_msgs,
            tool_counts=dict(tool_counts),
            files_touched=sorted(files_touched)[:30],
            bash_sample=bash_cmds[:15],
            token_in=int(tokens_in),
            token_out=int(tokens_out),
            cache_create=0,
            cache_read=0,
            est_cost_usd=round(est_cost, 4),
            file_size=path.stat().st_size,
            file_path=str(path),
        )
