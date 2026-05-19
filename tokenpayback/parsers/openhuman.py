"""OpenHuman (tinyhumansai) parser.

OpenHuman stores its 'memory tree' in SQLite plus an Obsidian-compatible
markdown vault. This parser does a best-effort read; the schema is still
evolving so feel free to send a PR with refinements once you've run it
against your install.

Reference: https://github.com/tinyhumansai/openhuman
"""
from __future__ import annotations
import sys
from pathlib import Path

from .base import BaseParser, Session
from .openclaw import _read_sqlite  # reuse the heuristic sqlite reader


CANDIDATE_ROOTS = [
    Path.home() / ".openhuman",
    Path.home() / "Library" / "Application Support" / "OpenHuman",
    Path.home() / "Library" / "Application Support" / "openhuman",
    Path.home() / ".config" / "openhuman",
]


def _find_root() -> Path | None:
    for p in CANDIDATE_ROOTS:
        if p.exists():
            return p
    return None


class OpenHumanParser(BaseParser):
    agent_name = "openhuman"
    display_name = "OpenHuman (tinyhumans.ai)"

    def is_available(self) -> bool:
        return _find_root() is not None

    def parse_sessions(self) -> list[Session]:
        root = _find_root()
        if not root:
            return []
        out: list[Session] = []
        for db in list(root.rglob("*.db")) + list(root.rglob("*.sqlite")) + list(root.rglob("*.sqlite3")):
            try:
                rows = _read_sqlite(db)
                for r in rows:
                    r["agent"] = "openhuman"
                out.extend(rows)
            except Exception as e:
                print(f"  ! openhuman read {db.name} failed: {e}", file=sys.stderr)
        return out
