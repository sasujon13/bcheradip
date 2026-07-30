"""Build structured practice score JSON for users.score."""

from __future__ import annotations

import json
from typing import Any


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, float(v)))


def _split_triple(avgs: list[float | None]) -> dict[str, Any]:
    """Map practiced averages into success/failure wedges that sum to 100.

    None = never practiced → excluded from accuracy and wedge math.
    """
    present = [a for a in avgs if a is not None]
    keys = ("a", "b", "c")
    empty_seg = {"success": 0.0, "failure": 0.0, "practiced": False}
    empty = {
        "a": dict(empty_seg),
        "b": dict(empty_seg),
        "c": dict(empty_seg),
        "accuracy": 0.0,
    }
    if not present:
        return empty
    accuracy = sum(present) / len(present)
    fail_total = max(0.0, 100.0 - accuracy)
    success_sum = sum(present)
    fail_sum = sum((100.0 - a) for a in present) or 0.0001

    out: dict[str, Any] = {"accuracy": round(accuracy, 2)}
    for key, avg in zip(keys, avgs, strict=True):
        if avg is None:
            out[key] = dict(empty_seg)
            continue
        success = (avg / success_sum) * accuracy if success_sum > 0 else 0.0
        failure = ((100.0 - avg) / fail_sum) * fail_total if fail_total > 0 else 0.0
        out[key] = {
            "success": round(success, 2),
            "failure": round(failure, 2),
            "practiced": True,
        }
    return out


def _avg_for(rows: list[Any], attr: str, value: str) -> float | None:
    vals = [
        float(getattr(r, "utterance_percent") or 0)
        for r in rows
        if (getattr(r, attr, "") or "").lower() == value.lower()
    ]
    if not vals:
        return None
    return sum(vals) / len(vals)


def build_score_payload(
    rows: list[Any],
    *,
    current: float | None = None,
) -> dict[str, Any]:
    """Compute Current / Mode / Level / Overall breakdown from practice rows."""
    if not rows:
        overall = 0.0
        current_v = _clamp(current or 0.0)
    else:
        overall = sum(float(r.utterance_percent or 0) for r in rows) / len(rows)
        current_v = _clamp(current if current is not None else float(rows[-1].utterance_percent or 0))
    overall = _clamp(overall)

    mode_raw = _split_triple(
        [
            _avg_for(rows, "mode", "talk"),
            _avg_for(rows, "mode", "listen"),
            _avg_for(rows, "mode", "read"),
        ]
    )
    level_raw = _split_triple(
        [
            _avg_for(rows, "difficulty", "easy"),
            _avg_for(rows, "difficulty", "medium"),
            _avg_for(rows, "difficulty", "hard"),
        ]
    )

    def rename(trip: dict[str, Any], names: tuple[str, str, str]) -> dict[str, Any]:
        return {
            names[0]: trip["a"],
            names[1]: trip["b"],
            names[2]: trip["c"],
            "accuracy": trip["accuracy"],
        }

    return {
        "current": round(current_v, 2),
        "overall": round(overall, 2),
        "mode": rename(mode_raw, ("talk", "listen", "read")),
        "level": rename(level_raw, ("easy", "medium", "hard")),
    }


def score_to_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"))


def parse_user_score(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (int, float)):
        return build_score_payload([], current=float(raw))
    text = str(raw).strip()
    if not text:
        return None
    if not text.startswith("{"):
        try:
            return {"overall": _clamp(float(text)), "current": 0.0}
        except ValueError:
            return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def overall_from_score(raw: Any) -> float:
    parsed = parse_user_score(raw)
    if not parsed:
        return 0.0
    try:
        return _clamp(float(parsed.get("overall", 0) or 0))
    except (TypeError, ValueError):
        return 0.0
