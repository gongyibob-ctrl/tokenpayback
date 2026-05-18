"""Parse ~/.claude/projects/**/*.jsonl session files.

Extract per-session: project (cwd), time span, tool call counts, token usage,
first user prompt, list of files touched. Output: list[dict].
"""
from __future__ import annotations
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterator


CLAUDE_ROOT = Path.home() / ".claude" / "projects"


def decode_project_name(encoded: str) -> str:
    """Claude Code encodes cwd by replacing /, . etc. with `-`. Imperfect but useful."""
    if encoded.startswith("-Users-yibo-Documents-"):
        rest = encoded.replace("-Users-yibo-Documents-", "")
        return f"~/Documents/{rest.replace('-', '/')}"
    if encoded.startswith("-Users-yibo"):
        rest = encoded.replace("-Users-yibo", "") or "/"
        return f"~{rest.replace('-', '/')}"
    return encoded


def iter_session_files() -> Iterator[Path]:
    if not CLAUDE_ROOT.exists():
        return
    for proj in CLAUDE_ROOT.iterdir():
        if not proj.is_dir():
            continue
        for f in proj.glob("*.jsonl"):
            yield f


def parse_session(path: Path) -> dict:
    project = decode_project_name(path.parent.name)
    session_id = path.stem
    first_prompt = ""
    last_event_time = None
    first_event_time = None
    tool_counts: Counter = Counter()
    files_touched: set[str] = set()
    bash_cmds: list[str] = []
    token_in = token_out = cache_create = cache_read = 0
    user_msgs = 0

    with open(path) as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = d.get("timestamp") or d.get("snapshot", {}).get("timestamp") if isinstance(d.get("snapshot"), dict) else None
            if ts and not first_event_time:
                first_event_time = ts
            if ts:
                last_event_time = ts
            t = d.get("type")
            msg = d.get("message") or {}
            if t == "user" and isinstance(msg, dict):
                content = msg.get("content")
                if isinstance(content, str) and not first_prompt:
                    first_prompt = content.strip()[:600]
                    user_msgs += 1
                elif isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text" and not first_prompt:
                            first_prompt = (c.get("text") or "").strip()[:600]
                            user_msgs += 1
            if t == "assistant" and isinstance(msg, dict):
                usage = msg.get("usage") or {}
                token_in += usage.get("input_tokens", 0)
                token_out += usage.get("output_tokens", 0)
                cache_create += usage.get("cache_creation_input_tokens", 0)
                cache_read += usage.get("cache_read_input_tokens", 0)
                content = msg.get("content") or []
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "tool_use":
                            name = c.get("name", "?")
                            tool_counts[name] += 1
                            inp = c.get("input") or {}
                            if name in ("Read", "Edit", "Write", "NotebookEdit"):
                                fp = inp.get("file_path")
                                if fp:
                                    files_touched.add(fp)
                            elif name == "Bash":
                                cmd = (inp.get("command") or "")[:120]
                                bash_cmds.append(cmd)

    return {
        "session_id": session_id,
        "project": project,
        "first_prompt": first_prompt,
        "first_event": first_event_time,
        "last_event": last_event_time,
        "user_messages": user_msgs,
        "tool_counts": dict(tool_counts),
        "files_touched": sorted(files_touched)[:30],
        "bash_sample": bash_cmds[:15],
        "token_in": token_in,
        "token_out": token_out,
        "cache_create": cache_create,
        "cache_read": cache_read,
        "est_cost_usd": round(
            token_in * 3e-6 + token_out * 15e-6 + cache_create * 3.75e-6 + cache_read * 0.3e-6, 4
        ),
        "file_size": path.stat().st_size,
        "file_path": str(path),
    }


def collect_all() -> list[dict]:
    out = []
    for f in iter_session_files():
        try:
            s = parse_session(f)
        except Exception as e:
            print(f"! parse {f.name} failed: {e}", file=sys.stderr)
            continue
        if s["user_messages"] == 0:
            continue
        out.append(s)
    out.sort(key=lambda x: x.get("last_event") or "", reverse=True)
    return out


if __name__ == "__main__":
    sessions = collect_all()
    print(f"# {len(sessions)} sessions found", file=sys.stderr)
    print(json.dumps(sessions, ensure_ascii=False, indent=2, default=str))
