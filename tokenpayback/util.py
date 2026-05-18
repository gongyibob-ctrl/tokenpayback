"""Shared helpers: config loading + ISO week math."""
from __future__ import annotations
import datetime as dt
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_LOCAL = ROOT / "config.local.yaml"
CONFIG_EXAMPLE = ROOT / "config.example.yaml"


def load_config() -> dict:
    """Prefer config.local.yaml, fall back to config.example.yaml so tests can run."""
    p = CONFIG_LOCAL if CONFIG_LOCAL.exists() else CONFIG_EXAMPLE
    with open(p) as f:
        return yaml.safe_load(f)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_week_of(d: dt.date | dt.datetime) -> str:
    if isinstance(d, dt.datetime):
        d = d.date()
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def week_range(week_str: str) -> tuple[dt.date, dt.date]:
    """e.g. '2026-W20' -> (Monday, Sunday) dates."""
    year, w = week_str.split("-W")
    monday = dt.date.fromisocalendar(int(year), int(w), 1)
    sunday = monday + dt.timedelta(days=6)
    return monday, sunday


def last_n_weeks(n: int = 4, end: dt.date | None = None) -> list[str]:
    end = end or utc_now().date()
    out = []
    monday = end - dt.timedelta(days=end.weekday())
    for i in range(n):
        out.append(iso_week_of(monday - dt.timedelta(weeks=i)))
    return list(reversed(out))


def env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)
