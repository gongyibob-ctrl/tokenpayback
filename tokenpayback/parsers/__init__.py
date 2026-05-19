"""Parser plugins — one file per agent.

To add a new agent:
1. Create `parsers/<agent_name>.py` exporting a subclass of `BaseParser`.
2. Register it in `ALL_PARSERS` below.
3. Run `tokenpayback scan` — sessions from the new agent appear automatically.

Each parser is responsible for:
- Detecting whether the agent's data exists on this machine.
- Reading the agent's local session storage.
- Returning a normalized list of Session dicts.
"""
from __future__ import annotations

from .base import BaseParser, Session
from .claude_code import ClaudeCodeParser
from .codex import CodexParser
from .hermes import HermesParser
from .openclaw import OpenClawParser
from .openhuman import OpenHumanParser
from .cursor import CursorParser


ALL_PARSERS: list[type[BaseParser]] = [
    ClaudeCodeParser,
    CodexParser,
    HermesParser,
    OpenClawParser,
    OpenHumanParser,
    CursorParser,
]


def available_parsers() -> list[BaseParser]:
    """Return instances for parsers whose data directory exists on this machine."""
    out = []
    for cls in ALL_PARSERS:
        p = cls()
        if p.is_available():
            out.append(p)
    return out


def collect_all_sessions() -> list[Session]:
    """Run every available parser. Sessions are tagged with their agent name."""
    sessions: list[Session] = []
    for parser in available_parsers():
        try:
            agent_sessions = parser.parse_sessions()
            for s in agent_sessions:
                s.setdefault("agent", parser.agent_name)
            sessions.extend(agent_sessions)
        except Exception as e:
            import sys
            print(f"  ! parser {parser.agent_name} failed: {e}", file=sys.stderr)
    sessions.sort(key=lambda s: s.get("last_event") or "", reverse=True)
    return sessions


__all__ = ["BaseParser", "Session", "ALL_PARSERS", "available_parsers", "collect_all_sessions"]
