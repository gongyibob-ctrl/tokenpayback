"""OpenClaw parser — reads ~/.openclaw / OpenClaw data directory.

OpenClaw (https://github.com/openclaw/openclaw) is a personal AI assistant
with a local-first gateway. Its session schema is still evolving — this parser
detects the data root and provides a best-effort read for SQLite/JSON files.

Contributions welcome to refine this once your OpenClaw install path is verified.
"""
from __future__ import annotations
import json
import sqlite3
import sys
from pathlib import Path

from .base import BaseParser, Session


CANDIDATE_ROOTS = [
    Path.home() / ".openclaw",
    Path.home() / "Library" / "Application Support" / "OpenClaw",
    Path.home() / "Library" / "Application Support" / "openclaw",
    Path.home() / ".config" / "openclaw",
]


def _find_root() -> Path | None:
    for p in CANDIDATE_ROOTS:
        if p.exists():
            return p
    return None


class OpenClawParser(BaseParser):
    agent_name = "openclaw"
    display_name = "OpenClaw 🦞"

    def is_available(self) -> bool:
        return _find_root() is not None

    def parse_sessions(self) -> list[Session]:
        root = _find_root()
        if not root:
            return []
        out: list[Session] = []
        # Strategy 1: SQLite
        for db in list(root.rglob("*.db")) + list(root.rglob("*.sqlite")):
            try:
                out.extend(_read_sqlite(db))
            except Exception as e:
                print(f"  ! openclaw sqlite read {db.name} failed: {e}", file=sys.stderr)
        # Strategy 2: JSONL session logs
        for js in root.rglob("*.jsonl"):
            try:
                out.extend(_read_jsonl(js))
            except Exception as e:
                print(f"  ! openclaw jsonl read {js.name} failed: {e}", file=sys.stderr)
        return out


def _read_sqlite(db_path: Path) -> list[Session]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    candidate = next((t for t in tables if any(
        kw in t.lower() for kw in ("session", "conversation", "thread", "chat"))), None)
    if not candidate:
        conn.close()
        return []
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({candidate})").fetchall()]
    id_col = next((c for c in cols if c.lower() in ("id", "session_id", "thread_id", "uuid")), cols[0])
    time_col = next((c for c in cols if c.lower() in ("updated_at", "created_at", "last_message_at")), None)
    title_col = next((c for c in cols if "title" in c.lower() or "name" in c.lower()), None)
    sql = f"SELECT * FROM {candidate}" + (f" ORDER BY {time_col} DESC" if time_col else "") + " LIMIT 200"
    out = []
    for row in conn.execute(sql).fetchall():
        sid = str(row[id_col])
        title = (row[title_col] if title_col else None) or ""
        ts = row[time_col] if time_col else None
        out.append(Session(
            agent="openclaw",
            session_id=sid,
            project=str(title)[:60] or "(openclaw session)",
            first_prompt="",
            first_event=str(ts) if ts else None,
            last_event=str(ts) if ts else None,
            user_messages=1,
            tool_counts={},
            files_touched=[],
            bash_sample=[],
            token_in=0, token_out=0, cache_create=0, cache_read=0,
            est_cost_usd=0.0,
            file_size=db_path.stat().st_size,
            file_path=str(db_path),
        ))
    conn.close()
    return out


def _read_jsonl(path: Path) -> list[Session]:
    """Naive JSONL reader — collapses each file into one session record."""
    first_prompt = ""
    first_ts = last_ts = None
    user_msgs = 0
    with open(path) as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = d.get("timestamp") or d.get("time") or d.get("created_at")
            if ts and not first_ts:
                first_ts = ts
            if ts:
                last_ts = ts
            # Try to capture user content
            for key in ("user", "user_message", "prompt"):
                if not first_prompt and key in d:
                    v = d[key]
                    if isinstance(v, str):
                        first_prompt = v[:600]
                        user_msgs += 1
    if user_msgs == 0:
        return []
    return [Session(
        agent="openclaw",
        session_id=path.stem,
        project=path.parent.name,
        first_prompt=first_prompt,
        first_event=first_ts,
        last_event=last_ts,
        user_messages=user_msgs,
        tool_counts={},
        files_touched=[],
        bash_sample=[],
        token_in=0, token_out=0, cache_create=0, cache_read=0,
        est_cost_usd=0.0,
        file_size=path.stat().st_size,
        file_path=str(path),
    )]
