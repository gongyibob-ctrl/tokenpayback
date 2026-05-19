"""Abstract base class + Session dict spec for all parsers."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TypedDict


class Session(TypedDict, total=False):
    """Normalized session record. Every parser emits these."""
    agent: str                   # "claude-code" / "codex" / "hermes" / ...
    session_id: str
    project: str                 # cwd or workspace name (decoded)
    first_prompt: str            # first user message, max ~600 chars
    first_event: str             # ISO timestamp
    last_event: str              # ISO timestamp
    user_messages: int
    tool_counts: dict[str, int]  # name → count (Bash, Read, Edit, ...)
    files_touched: list[str]     # absolute paths
    bash_sample: list[str]
    token_in: int
    token_out: int
    cache_create: int
    cache_read: int
    est_cost_usd: float
    file_size: int
    file_path: str               # source file or db path
    raw: dict                    # parser-specific extras (optional)
    classification: dict         # added later by classifier (optional)


class BaseParser(ABC):
    """Implement once per agent.

    The simplest parser only needs `agent_name`, `data_root`, and `parse_sessions`.
    `is_available` checks data_root by default; override if detection is tricky.
    """

    agent_name: str = ""           # short slug, e.g. "claude-code"
    display_name: str = ""         # pretty name, e.g. "Claude Code"
    data_root: str = ""            # path glob hint relative to $HOME — for is_available

    def is_available(self) -> bool:
        """Default: check if data_root exists. Subclasses can override for detection."""
        from pathlib import Path
        if not self.data_root:
            return False
        path = Path.home() / self.data_root.lstrip("/").lstrip("~/")
        return path.exists()

    @abstractmethod
    def parse_sessions(self) -> list[Session]:
        """Read agent's local data, return normalized Session list."""
        raise NotImplementedError
