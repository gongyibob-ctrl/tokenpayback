"""Claude Code parser — reads ~/.claude/projects/**/*.jsonl"""
from __future__ import annotations
import json
import sys
from collections import Counter
from pathlib import Path

from .base import BaseParser, Session


def _decode_project_name(encoded: str) -> str:
    """Claude Code encodes cwd by replacing /, . etc. with `-`."""
    home = str(Path.home())
    home_enc = home.replace("/", "-")
    if encoded.startswith(home_enc + "-Documents-"):
        rest = encoded[len(home_enc + "-Documents-"):]
        return f"~/Documents/{rest.replace('-', '/')}"
    if encoded.startswith(home_enc):
        rest = encoded[len(home_enc):] or "/"
        return f"~{rest.replace('-', '/')}"
    return encoded


class ClaudeCodeParser(BaseParser):
    agent_name = "claude-code"
    display_name = "Claude Code"
    data_root = ".claude/projects"

    def parse_sessions(self) -> list[Session]:
        root = Path.home() / ".claude" / "projects"
        if not root.exists():
            return []
        out: list[Session] = []
        for proj_dir in root.iterdir():
            if not proj_dir.is_dir():
                continue
            for f in proj_dir.glob("*.jsonl"):
                try:
                    s = self._parse_one(f, proj_dir.name)
                except Exception as e:
                    print(f"  ! claude-code parse {f.name} failed: {e}", file=sys.stderr)
                    continue
                if s["user_messages"] > 0:
                    out.append(s)
        return out

    def _parse_one(self, path: Path, encoded_proj: str) -> Session:
        project = _decode_project_name(encoded_proj)
        first_prompt = ""
        first_event_time = None
        last_event_time = None
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
                ts = d.get("timestamp")
                if not ts and isinstance(d.get("snapshot"), dict):
                    ts = d["snapshot"].get("timestamp")
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

        est_cost = (token_in * 3e-6 + token_out * 15e-6
                    + cache_create * 3.75e-6 + cache_read * 0.3e-6)
        return Session(
            agent="claude-code",
            session_id=path.stem,
            project=project,
            first_prompt=first_prompt,
            first_event=first_event_time,
            last_event=last_event_time,
            user_messages=user_msgs,
            tool_counts=dict(tool_counts),
            files_touched=sorted(files_touched)[:30],
            bash_sample=bash_cmds[:15],
            token_in=token_in,
            token_out=token_out,
            cache_create=cache_create,
            cache_read=cache_read,
            est_cost_usd=round(est_cost, 4),
            file_size=path.stat().st_size,
            file_path=str(path),
        )
