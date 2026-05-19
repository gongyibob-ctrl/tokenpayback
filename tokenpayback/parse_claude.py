"""Legacy entry point — now delegates to the plugin parser registry.

Kept for backwards-compat with any code that imports `parse_claude.collect_all`.
"""
from __future__ import annotations

from .parsers import collect_all_sessions


def collect_all():
    """Run every available agent parser and return a flat list of Session dicts."""
    return collect_all_sessions()


if __name__ == "__main__":
    import json
    sessions = collect_all()
    print(json.dumps(sessions, ensure_ascii=False, indent=2, default=str))
