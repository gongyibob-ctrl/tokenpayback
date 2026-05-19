"""Parser for the local LLM proxy log at ~/.tokenpayback/proxy_log.jsonl

Groups proxy calls into sessions by **(tool_source, time_window)**:
- Each call is fingerprinted to identify which client tool sent it (Claude Code,
  Aider, Cursor, raw script via openai-sdk, etc.) using fingerprint.py.
- Within a tool, calls separated by more than 30 minutes start a new session.
- Different tools never share a session, even in overlapping time windows.
"""
from __future__ import annotations
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from .base import BaseParser, Session
from ..fingerprint import fingerprint as fp_fingerprint


PROXY_LOG = Path.home() / ".tokenpayback" / "proxy_log.jsonl"
IDLE_GAP_SECONDS = 30 * 60


def _read_log() -> list[dict]:
    if not PROXY_LOG.exists():
        return []
    out = []
    with open(PROXY_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    # tag each entry with its detected source
    for e in out:
        e["tool_source"] = fp_fingerprint(e)
    out.sort(key=lambda e: e.get("timestamp", ""))
    return out


def _parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


class ProxyLogParser(BaseParser):
    agent_name = "proxy"
    display_name = "Local Proxy (any tool routed through it)"

    def is_available(self) -> bool:
        return PROXY_LOG.exists()

    def parse_sessions(self) -> list[Session]:
        entries = _read_log()
        if not entries:
            return []
        # Group by tool_source first
        by_tool: dict[str, list[dict]] = {}
        for e in entries:
            by_tool.setdefault(e["tool_source"], []).append(e)

        all_sessions: list[Session] = []
        for tool, tool_entries in by_tool.items():
            tool_entries.sort(key=lambda e: e.get("timestamp", ""))
            # then split by idle window
            sessions: list[list[dict]] = []
            current: list[dict] = []
            last_ts = None
            for e in tool_entries:
                ts = _parse_ts(e.get("timestamp"))
                if ts and last_ts and (ts - last_ts).total_seconds() > IDLE_GAP_SECONDS:
                    if current:
                        sessions.append(current)
                    current = []
                current.append(e)
                last_ts = ts or last_ts
            if current:
                sessions.append(current)
            for i, s in enumerate(sessions):
                all_sessions.append(self._to_session(s, tool, i))
        return all_sessions

    def _to_session(self, entries: list[dict], tool_source: str, idx: int) -> Session:
        first_ts = entries[0].get("timestamp")
        last_ts = entries[-1].get("timestamp")
        upstreams = Counter(e.get("upstream", "?") for e in entries)
        models = Counter(e.get("model") or "?" for e in entries)
        tool_uses_all: Counter = Counter()
        for e in entries:
            for t in (e.get("tools_used") or []):
                tool_uses_all[t] += 1
        in_tokens = sum(e.get("input_tokens", 0) or 0 for e in entries)
        out_tokens = sum(e.get("output_tokens", 0) or 0 for e in entries)
        cache_c = sum(e.get("cache_create", 0) or 0 for e in entries)
        cache_r = sum(e.get("cache_read", 0) or 0 for e in entries)
        total_cost = sum(e.get("est_cost_usd", 0) or 0 for e in entries)
        first_prompt = ""
        for e in entries:
            ps = e.get("prompt_summary")
            if ps:
                first_prompt = str(ps)[:600]
                break
        primary_upstream = upstreams.most_common(1)[0][0]
        # Project includes both tool and upstream so it groups meaningfully
        project = f"proxy:{tool_source}→{primary_upstream}"
        return Session(
            agent=f"proxy:{tool_source}",
            session_id=f"proxy-{tool_source}-{first_ts or idx}",
            project=project,
            first_prompt=first_prompt,
            first_event=first_ts,
            last_event=last_ts,
            user_messages=len(entries),
            tool_counts=dict(tool_uses_all),
            files_touched=[],
            bash_sample=[],
            token_in=in_tokens,
            token_out=out_tokens,
            cache_create=cache_c,
            cache_read=cache_r,
            est_cost_usd=round(total_cost, 4),
            file_size=PROXY_LOG.stat().st_size,
            file_path=str(PROXY_LOG),
            raw={
                "tool_source": tool_source,
                "upstreams": dict(upstreams),
                "models": dict(models),
                "call_count": len(entries),
            },
        )
