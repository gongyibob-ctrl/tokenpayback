"""Hermes (Nous Research) parser — reads ~/.hermes/ SQLite with FTS5 sessions.

Schema is not yet locked down — Hermes is an actively-evolving project. This
parser uses a defensive approach: look for sqlite db, inspect tables, extract
what we recognize. Falls back gracefully when fields are missing.

Reference: https://github.com/nousresearch/hermes-agent
"""
from __future__ import annotations
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from .base import BaseParser, Session


HERMES_ROOT = Path.home() / ".hermes"


def _find_db() -> Path | None:
    """Look for the main sqlite db. Hermes uses FTS5 — there's at least one .db / .sqlite."""
    if not HERMES_ROOT.exists():
        return None
    for pattern in ("*.db", "*.sqlite", "*.sqlite3"):
        for p in HERMES_ROOT.rglob(pattern):
            if p.is_file() and p.stat().st_size > 0:
                return p
    return None


class HermesParser(BaseParser):
    agent_name = "hermes"
    display_name = "Hermes (Nous Research)"
    data_root = ".hermes"

    def is_available(self) -> bool:
        return HERMES_ROOT.exists() and _find_db() is not None

    def parse_sessions(self) -> list[Session]:
        db = _find_db()
        if not db:
            return []
        try:
            return self._read_db(db)
        except Exception as e:
            print(f"  ! hermes db read failed ({db.name}): {e}", file=sys.stderr)
            return []

    def _read_db(self, db_path: Path) -> list[Session]:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        # Discover tables defensively
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        # Heuristic: look for a table named like sessions / conversations / threads
        candidate = None
        for t in tables:
            if any(kw in t.lower() for kw in ("session", "conversation", "thread", "chat")):
                candidate = t
                break
        if not candidate:
            conn.close()
            return []

        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({candidate})").fetchall()]
        # Try to figure out time / title columns
        time_col = next((c for c in cols if c.lower() in ("updated_at", "created_at", "last_message_at", "timestamp")), None)
        title_col = next((c for c in cols if "title" in c.lower() or "name" in c.lower() or "summary" in c.lower()), None)
        id_col = next((c for c in cols if c.lower() in ("id", "session_id", "thread_id", "uuid")), cols[0])

        sql = f"SELECT * FROM {candidate}"
        if time_col:
            sql += f" ORDER BY {time_col} DESC"
        sql += " LIMIT 200"

        out: list[Session] = []
        for row in conn.execute(sql).fetchall():
            sid = str(row[id_col]) if id_col in row.keys() else ""
            title = (row[title_col] if title_col and title_col in row.keys() else None) or ""
            ts = row[time_col] if time_col and time_col in row.keys() else None
            # Token counts: try common column names
            tok_in = _opt_int(row, "input_tokens", "prompt_tokens", "tokens_in")
            tok_out = _opt_int(row, "output_tokens", "completion_tokens", "tokens_out")
            est_cost = tok_in * 3e-6 + tok_out * 15e-6  # rough; hermes user picks model
            out.append(Session(
                agent="hermes",
                session_id=sid,
                project=str(title)[:60] or "(untitled hermes session)",
                first_prompt="",  # would need a join with messages table
                first_event=str(ts) if ts else None,
                last_event=str(ts) if ts else None,
                user_messages=1,
                tool_counts={},
                files_touched=[],
                bash_sample=[],
                token_in=tok_in,
                token_out=tok_out,
                cache_create=0,
                cache_read=0,
                est_cost_usd=round(est_cost, 4),
                file_size=db_path.stat().st_size,
                file_path=str(db_path),
            ))
        conn.close()
        return out


def _opt_int(row, *names) -> int:
    for n in names:
        try:
            v = row[n]
            if v is not None:
                return int(v)
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return 0
