"""Role-based valuation — compare AI output to human professional labor market.

For each session, the LLM classifier supplies:
  equivalent_role:           "senior backend engineer" / "UX designer" / ...
  human_minutes_{low,mid,high}: how long a pro would take
  hourly_rate_usd_{low,mid,high}: market rate for that role (region+seniority-adjusted)
  replacement_quality:       full-replacement | with-edits | draft-only | failed

This module turns those into a value estimate.

  value = (minutes / 60) × hourly_rate × quality_multiplier

Returned as a low / mid / high range so the user sees uncertainty instead of
false precision.
"""
from __future__ import annotations


QUALITY_MULTIPLIER = {
    "full-replacement": 1.0,    # AI output directly usable as-is
    "with-edits": 0.7,          # mostly right, user touched it up
    "draft-only": 0.4,          # AI gave a starting point, user wrote most of it
    "failed": 0.0,              # AI produced nothing usable; cost wasted
    "harmful": -0.5,            # AI made things worse — introduced bugs, took user
                                # MORE time to clean up than original task would've
}


def session_value_range(classification: dict) -> dict | None:
    """Return {low, mid, high, role, quality, multiplier, ...} or None if data insufficient."""
    if not classification:
        return None
    quality = classification.get("replacement_quality", "with-edits")
    mult = QUALITY_MULTIPLIER.get(quality, 0.5)

    mlow = classification.get("human_minutes_low")
    mmid = classification.get("human_minutes_mid")
    mhigh = classification.get("human_minutes_high")
    rlow = classification.get("hourly_rate_usd_low")
    rmid = classification.get("hourly_rate_usd_mid")
    rhigh = classification.get("hourly_rate_usd_high")

    if None in (mlow, mmid, mhigh, rlow, rmid, rhigh):
        return None

    # Pair the worst-case minutes with worst-case rate for the low bound
    # and best-case minutes with best-case rate for the high bound, so the
    # spread reflects genuine uncertainty rather than artificially narrow.
    low_v = (float(mlow) / 60) * float(rlow) * mult
    mid_v = (float(mmid) / 60) * float(rmid) * mult
    high_v = (float(mhigh) / 60) * float(rhigh) * mult
    return {
        "low_usd": round(low_v, 2),
        "mid_usd": round(mid_v, 2),
        "high_usd": round(high_v, 2),
        "role": classification.get("equivalent_role"),
        "quality": quality,
        "quality_multiplier": mult,
        "minutes_low": float(mlow),
        "minutes_mid": float(mmid),
        "minutes_high": float(mhigh),
        "rate_low": float(rlow),
        "rate_mid": float(rmid),
        "rate_high": float(rhigh),
    }


def session_roi_range(value: dict, cost_usd: float) -> dict:
    """Compute ROI range from value range / cost. Cost ≤ 0 → None ROI."""
    if cost_usd <= 0:
        return {"low": None, "mid": None, "high": None}
    return {
        "low": round(value["low_usd"] / cost_usd, 2),
        "mid": round(value["mid_usd"] / cost_usd, 2),
        "high": round(value["high_usd"] / cost_usd, 2),
    }
