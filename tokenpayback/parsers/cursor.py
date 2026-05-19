"""Cursor parser — reads ~/Library/Application Support/Cursor/User/ (macOS).

Cursor stores chat history in VS Code's state.vscdb (SQLite). Schema lives
in the `cursorDiskKV` table with JSON values keyed by 'composer'/'aiService'.

This is a best-effort parser — Cursor's schema isn't documented and changes.
Open an issue if your data isn't being picked up.
"""
from __future__ import annotations
import json
import sqlite3
import sys
from pathlib import Path

from .base import BaseParser, Session


def _cursor_root() -> Path | None:
    candidates = [
        Path.home() / "Library" / "Application Support" / "Cursor" / "User",
        Path.home() / ".config" / "Cursor" / "User",
        Path.home() / "AppData" / "Roaming" / "Cursor" / "User",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


class CursorParser(BaseParser):
    agent_name = "cursor"
    display_name = "Cursor"

    def is_available(self) -> bool:
        return _cursor_root() is not None

    def parse_sessions(self) -> list[Session]:
        root = _cursor_root()
        if not root:
            return []
        # globalStorage/state.vscdb is the file we want
        db = root / "globalStorage" / "state.vscdb"
        if not db.exists():
            # try alternate locations
            found = list(root.rglob("state.vscdb"))
            db = found[0] if found else None
        if not db or not db.exists():
            return []
        try:
            return _read_cursor_db(db)
        except Exception as e:
            print(f"  ! cursor read failed: {e}", file=sys.stderr)
            return []


def _read_cursor_db(db_path: Path) -> list[Session]:
    out: list[Session] = []
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT key, value FROM cursorDiskKV WHERE key LIKE 'composerData:%' LIMIT 500"
        ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return []

    for key, value in rows:
        try:
            d = json.loads(value) if isinstance(value, (str, bytes)) else {}
        except Exception:
            continue
        sid = key.split(":", 1)[1] if ":" in key else key
        title = d.get("name") or d.get("title") or "(cursor composer)"
        last_msg_time = d.get("lastUpdatedAt") or d.get("createdAt")
        msgs = d.get("conversation") or d.get("messages") or []
        first_prompt = ""
        for m in msgs:
            if isinstance(m, dict) and (m.get("type") in (1, "user", "human") or m.get("role") == "user"):
                t = m.get("text") or m.get("content") or ""
                if isinstance(t, str) and t.strip():
                    first_prompt = t.strip()[:600]
                    break
        out.append(Session(
            agent="cursor",
            session_id=sid,
            project=str(title)[:80],
            first_prompt=first_prompt,
            first_event=str(last_msg_time) if last_msg_time else None,
            last_event=str(last_msg_time) if last_msg_time else None,
            user_messages=sum(1 for m in msgs if isinstance(m, dict)),
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
