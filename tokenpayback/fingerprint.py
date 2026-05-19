"""Identify which client tool produced each proxy log entry.

Heuristics first (fast, deterministic), LLM-as-judge as a future fallback.

Returns one of:
- claude-code, codex-cli, aider, cursor, cline, continue
- langchain, llamaindex
- anthropic-sdk, openai-sdk
- raw-curl, browser
- unknown
"""
from __future__ import annotations
import re


# Tool sets that uniquely identify a client when declared in `tools`
_TOOL_FINGERPRINTS: list[tuple[str, set[str]]] = [
    ("claude-code", {"Read", "Edit", "Bash"}),                    # Claude Code core trio
    ("claude-code", {"TodoWrite"}),                                # very specific
    ("codex-cli", {"exec_command", "update_plan"}),                # OpenAI Codex CLI
    ("aider", {"replace_in_file"}),                                # Aider's signature
    ("cursor", {"cursor_create_diff"}),                            # speculative
    ("cline", {"execute_command", "read_file", "write_to_file"}),  # Cline's tool set
]


_SYSTEM_PROMPT_FINGERPRINTS: list[tuple[str, list[str]]] = [
    ("claude-code", ["You are Claude Code", "Anthropic's official CLI"]),
    ("codex-cli",   ["You are Codex CLI", "openai/codex", "codex cli"]),
    ("aider",       ["You are aider", "You are an expert software engineer"]),  # second is weak
    ("cursor",      ["You are Cursor", "You are an AI coding assistant in Cursor"]),
    ("cline",       ["You are Cline"]),
    ("continue",    ["You are Continue"]),
    ("langchain",   ["You are a helpful AI assistant"]),  # very weak but common in LC
]


_UA_FINGERPRINTS: list[tuple[str, list[str]]] = [
    ("claude-code",  ["claude-code", "claude_code"]),
    ("codex-cli",    ["codex-cli", "codex_cli", "openai-codex"]),
    ("aider",        ["aider"]),
    ("cursor",       ["cursor"]),
    ("cline",        ["cline"]),
    ("continue",     ["continue.dev", "continuedev"]),
    ("langchain",    ["langchain"]),
    ("llamaindex",   ["llama-index", "llama_index", "llamaindex"]),
    ("anthropic-sdk",["anthropic-python", "anthropic-typescript", "anthropic-sdk", "anthropic/"]),
    ("openai-sdk",   ["openai-python", "openai-node", "openai/"]),
    ("raw-curl",     ["curl/"]),
    ("browser",      ["mozilla", "chrome", "safari"]),
]


def _match_any(needles: list[str], haystack: str) -> bool:
    h = haystack.lower()
    return any(n.lower() in h for n in needles)


def fingerprint(entry: dict) -> str:
    """Best-effort tool identification. Returns 'unknown' if nothing matches."""
    ua = (entry.get("user_agent") or "").lower()
    x_client = (entry.get("x_client") or "").lower()
    system_head = (entry.get("system_prompt_head") or "").lower()
    tools = set(entry.get("tools_declared_names") or [])

    # Highest confidence: declared tool set
    for label, sig in _TOOL_FINGERPRINTS:
        if sig.issubset(tools):
            return label

    # Strong: system prompt prefix
    for label, needles in _SYSTEM_PROMPT_FINGERPRINTS:
        if _match_any(needles, system_head):
            return label

    # User-Agent / x-client headers
    for label, needles in _UA_FINGERPRINTS:
        if _match_any(needles, ua) or _match_any(needles, x_client):
            return label

    return "unknown"


def annotate_all(entries: list[dict]) -> None:
    """Mutate each entry to add `tool_source`."""
    for e in entries:
        e["tool_source"] = fingerprint(e)
