"""Collect weekly LLM/agent costs from multiple sources.

Strategy: try APIs first, gracefully fall back to user-provided manual numbers.
For V1 we don't try to be perfect — a believable number beats no number.
"""
from __future__ import annotations
import datetime as dt
import sys
from pathlib import Path

import requests

from .util import load_config, env, week_range, iso_week_of


def fixed_subscriptions_per_week_usd(config: dict) -> float:
    monthly_total = sum((config.get("fixed_monthly_subscriptions_usd") or {}).values())
    return monthly_total * 12.0 / 52.0  # average weekly


def anthropic_usage_for_week(week_str: str, config: dict) -> float | None:
    """Pull spend from Anthropic Admin API for given ISO week. Returns USD or None."""
    api_key = env("ANTHROPIC_ADMIN_KEY")
    if not api_key:
        return None
    monday, sunday = week_range(week_str)
    start_iso = monday.isoformat() + "T00:00:00Z"
    end_iso = (sunday + dt.timedelta(days=1)).isoformat() + "T00:00:00Z"
    try:
        resp = requests.get(
            "https://api.anthropic.com/v1/organizations/cost_report",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            params={"starting_at": start_iso, "ending_at": end_iso, "bucket_width": "1d"},
            timeout=30,
        )
        if not resp.ok:
            print(f"  ! anthropic usage HTTP {resp.status_code}: {resp.text[:160]}", file=sys.stderr)
            return None
        data = resp.json()
    except requests.RequestException as e:
        print(f"  ! anthropic usage failed: {e}", file=sys.stderr)
        return None
    total = 0.0
    for bucket in data.get("data", []):
        for result in bucket.get("results", []):
            amt = result.get("amount", {})
            total += float(amt.get("value", 0))
    return total


def openai_usage_for_week(week_str: str, config: dict) -> float | None:
    api_key = env("OPENAI_ADMIN_KEY")
    if not api_key:
        return None
    monday, sunday = week_range(week_str)
    try:
        resp = requests.get(
            "https://api.openai.com/v1/organization/costs",
            headers={"Authorization": f"Bearer {api_key}"},
            params={
                "start_time": int(dt.datetime.combine(monday, dt.time.min).timestamp()),
                "end_time": int(dt.datetime.combine(sunday + dt.timedelta(days=1), dt.time.min).timestamp()),
                "bucket_width": "1d",
            },
            timeout=30,
        )
        if not resp.ok:
            print(f"  ! openai usage HTTP {resp.status_code}: {resp.text[:160]}", file=sys.stderr)
            return None
        data = resp.json()
    except requests.RequestException as e:
        print(f"  ! openai usage failed: {e}", file=sys.stderr)
        return None
    total = 0.0
    for bucket in data.get("data", []):
        for r in bucket.get("results", []):
            total += float((r.get("amount") or {}).get("value", 0))
    return total


def collect(weeks: list[str], config: dict) -> dict[str, dict]:
    sub_per_week = fixed_subscriptions_per_week_usd(config)
    out: dict[str, dict] = {}
    for w in weeks:
        anth = anthropic_usage_for_week(w, config) if config["providers"]["anthropic"].get("enabled") else None
        op = openai_usage_for_week(w, config) if config["providers"]["openai"].get("enabled") else None
        total = (anth or 0) + (op or 0) + sub_per_week
        out[w] = {
            "anthropic_usd": round(anth, 2) if anth is not None else None,
            "openai_usd": round(op, 2) if op is not None else None,
            "fixed_subscriptions_usd": round(sub_per_week, 2),
            "total_usd": round(total, 2),
        }
    return out


if __name__ == "__main__":
    from .util import last_n_weeks
    import json
    cfg = load_config()
    weeks = last_n_weeks(4)
    print(json.dumps(collect(weeks, cfg), indent=2, ensure_ascii=False))
