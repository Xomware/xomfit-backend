"""
XOMFIT Reports Aggregator
=========================
Pure functions that turn a list of workout records into the stats payload
stored on a user_report. Kept dependency-free so it can be unit-tested
without DynamoDB or AWS access.
"""

from datetime import datetime, timezone
from typing import Iterable, Optional


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    s = str(value)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _f(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _i(value, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _est_one_rm(weight: float, reps: int) -> float:
    """Epley formula; matches dynamo_helpers.get_user_prs."""
    if reps <= 0:
        return 0.0
    if reps == 1:
        return float(weight)
    return float(weight) * (1.0 + reps / 30.0)


def _exercise_id(ex: dict) -> str:
    return str(ex.get("exercise_id") or ex.get("id") or ex.get("exercise_name") or "unknown")


def _exercise_name(ex: dict) -> str:
    return str(ex.get("exercise_name") or ex.get("name") or "Unknown")


def baseline_one_rm(prior_workouts: Iterable[dict]) -> dict:
    """Best estimated 1RM per exercise across prior workouts (used for PR detection)."""
    best: dict = {}
    for w in prior_workouts:
        for ex in w.get("exercises", []) or []:
            ex_id = _exercise_id(ex)
            for s in ex.get("sets", []) or []:
                weight = _f(s.get("weight"))
                reps = _i(s.get("reps"))
                e1rm = _est_one_rm(weight, reps)
                if e1rm > best.get(ex_id, 0.0):
                    best[ex_id] = e1rm
    return best


def aggregate(
    workouts: list,
    prior_workouts: Optional[list] = None,
) -> dict:
    """Compute the stats_json blob for a report period.

    Parameters
    ----------
    workouts : list[dict]
        Workouts whose started_at falls inside the period.
    prior_workouts : list[dict] | None
        All workouts strictly BEFORE the period — used as the PR baseline.
        If None, no PRs are reported (every set would otherwise be a "PR").
    """
    prior_baseline = baseline_one_rm(prior_workouts) if prior_workouts is not None else None

    total_volume = 0.0
    total_sets = 0
    total_reps = 0
    sessions = 0
    total_session_seconds = 0
    sessions_with_duration = 0

    # exercise_id -> {name, volume, sets}
    by_exercise: dict = {}
    # PRs detected this period (one per exercise — best new e1rm)
    prs: dict = {}

    for w in workouts:
        sessions += 1
        started = _parse_iso(w.get("started_at"))
        ended = _parse_iso(w.get("ended_at"))
        if started and ended and ended >= started:
            total_session_seconds += int((ended - started).total_seconds())
            sessions_with_duration += 1

        for ex in w.get("exercises", []) or []:
            ex_id = _exercise_id(ex)
            ex_name = _exercise_name(ex)
            agg = by_exercise.setdefault(ex_id, {
                "exercise_id": ex_id,
                "exercise_name": ex_name,
                "volume": 0.0,
                "sets": 0,
            })
            for s in ex.get("sets", []) or []:
                weight = _f(s.get("weight"))
                reps = _i(s.get("reps"))
                vol = weight * reps
                total_volume += vol
                total_sets += 1
                total_reps += reps
                agg["volume"] += vol
                agg["sets"] += 1

                if prior_baseline is not None:
                    e1rm = _est_one_rm(weight, reps)
                    prior_best = prior_baseline.get(ex_id, 0.0)
                    if e1rm > prior_best and e1rm > prs.get(ex_id, {}).get("estimated_1rm", 0.0):
                        prs[ex_id] = {
                            "exercise_id": ex_id,
                            "exercise_name": ex_name,
                            "weight": weight,
                            "reps": reps,
                            "estimated_1rm": round(e1rm, 2),
                            "previous_estimated_1rm": round(prior_best, 2),
                            "date": s.get("completed_at") or w.get("started_at"),
                        }

    top_exercises = sorted(
        by_exercise.values(), key=lambda e: e["volume"], reverse=True
    )[:5]
    for e in top_exercises:
        e["volume"] = round(e["volume"], 2)

    avg_session_seconds = (
        int(total_session_seconds / sessions_with_duration)
        if sessions_with_duration > 0 else 0
    )

    return {
        "sessions": sessions,
        "total_volume": round(total_volume, 2),
        "total_sets": total_sets,
        "total_reps": total_reps,
        "avg_session_seconds": avg_session_seconds,
        "top_exercises": top_exercises,
        "prs": list(prs.values()),
    }
