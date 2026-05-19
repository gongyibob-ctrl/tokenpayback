"""Parser for the local LLM proxy log at ~/.tokenpayback/proxy_log.jsonl

Groups consecutive proxy calls within a 30-minute idle window into one Session.
Each session shows: when, upstream, models, token totals, sample prompt, cost.
"""
from __future__ import annotations
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from .base import BaseParser, Session


PROXY_LOG = Path.home() / ".tokenpayback" / "proxy_log.jsonl"
IDLE_GAP_SECONDS = 30 * 60  # 30 min idle = new session


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
        sessions: list[list[dict]] = []
        current: list[dict] = []
        last_ts: datetime | None = None
        for e in entries:
            ts = _parse_ts(e.get("timestamp"))
            if ts and last_ts and (ts - last_ts).total_seconds() > IDLE_GAP_SECONDS:
                if current:
                    sessions.append(current)
                current = []
            current.append(e)
            last_ts = ts or last_ts
        if current:
            sessions.append(current)
        return [self._to_session(s, i) for i, s in enumerate(sessions)]

    def _to_session(self, entries: list[dict], idx: int) -> Session:
        first_ts = entries[0].get("timestamp")
        last_ts = entries[-1].get("timestamp")
        upstreams = Counter(e.get("upstream", "?") for e in entries)
        models = Counter(e.get("model", "?") or "?" for e in entries)
        tool_uses_all: Counter = Counter()
        for e in entries:
            for t in (e.get("tools_used") or []):
                tool_uses_all[t] += 1
        in_tokens = sum(e.get("input_tokens", 0) or 0 for e in entries)
        out_tokens = sum(e.get("output_tokens", 0) or 0 for e in entries)
        cache_c = sum(e.get("cache_create", 0) or 0 for e in entries)
        cache_r = sum(e.get("cache_read", 0) or 0 for e in entries)
        total_cost = sum(e.get("est_cost_usd", 0) or 0 for e in entries)
        # First prompt sample
        first_prompt = ""
        for e in entries:
            ps = e.get("prompt_summary")
            if ps:
                first_prompt = str(ps)[:600]
                break
        # Project = "proxy:<upstream>" so it groups in the dashboard
        primary_upstream = upstreams.most_common(1)[0][0]
        return Session(
            agent="proxy",
            session_id=f"proxy-{first_ts or idx}",
            project=f"proxy:{primary_upstream}",
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
            raw={"upstreams": dict(upstreams), "models": dict(models), "call_count": len(entries)},
        )
