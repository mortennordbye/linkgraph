"""Warmth score and path ranking."""

from __future__ import annotations

import math
from datetime import datetime


def _days_since(iso: str | None, now: datetime) -> float | None:
    if not iso:
        return None
    try:
        d = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=now.tzinfo)
    except ValueError:
        return None
    return max(0.0, (now - d).total_seconds() / 86400)


def warmth(p: dict, now: datetime) -> tuple[int, dict]:
    """0-100 score for how warm the relationship is. Returns (score, parts)."""
    parts: dict[str, float] = {}
    total = p.get("msg_total", 0)
    if total:
        parts["messages"] = min(30.0, 10 * math.log2(1 + total))
    if p.get("msg_from_me") and p.get("msg_from_them"):
        parts["two_way"] = 10.0
    days = _days_since(p.get("last_msg"), now)
    if days is not None:
        parts["recent_contact"] = 25.0 * math.exp(-days / 365)
    inv = p.get("invitation")
    if inv:
        parts["invitation"] = 2.0 + (8.0 if inv.get("has_message") else 0.0)
    endorse = 4 * p.get("endorse_given", 0) + 4 * p.get("endorse_received", 0)
    if endorse:
        parts["endorsements"] = min(12.0, float(endorse))
    recs = 10 * (p.get("recs_given", 0) + p.get("recs_received", 0))
    if recs:
        parts["recommendations"] = min(15.0, float(recs))
    tenure = _days_since(p.get("connected_on"), now)
    if tenure is not None:
        parts["tenure"] = min(5.0, tenure / 365)
    score = int(round(min(100.0, sum(parts.values()))))
    return score, {k: round(v, 1) for k, v in parts.items()}


TIER_WEIGHT = 20


def base_rank(p: dict) -> float:
    """Seniority first, then warmth. The UI adds lead-status adjustments."""
    return round(p.get("tier", 1) * TIER_WEIGHT + 0.8 * p.get("warmth", 0), 1)
