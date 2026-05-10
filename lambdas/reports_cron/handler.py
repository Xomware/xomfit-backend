"""
EventBridge-triggered cron that generates weekly + monthly user reports.

Trigger
-------
Two EventBridge schedules in xomfit-infrastructure invoke this Lambda hourly
on the hour. The handler determines, per user (using their stored timezone),
whether the local clock is currently:

  * Monday 08:00 (local)              -> generate a weekly report
  * Day-1 of month 08:00 (local)      -> generate a monthly report

Running hourly + filtering inside the handler keeps the rule simple and
respects each user's timezone without a per-user schedule.

Event payload (optional, useful for backfills / manual runs):
    {
        "kind": "weekly" | "monthly" | "auto",   # default "auto"
        "force_user_id": "u-...",                # bypass timezone check
        "now": "2026-05-04T13:00:00Z"            # override "now" for tests
    }
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from lambdas.common.logger import get_logger
from lambdas.common.errors import handle_errors
from lambdas.common.utility_helpers import now_iso
from lambdas.common.dynamo_helpers import (
    scan_all_users,
    get_user_workouts_in_range,
    get_user_workouts_before,
    put_report,
)
from lambdas.common.reports_aggregator import aggregate
from lambdas.common.anthropic_client import generate_recommendation
from lambdas.common.apns_client import send_report_notification

log = get_logger(__file__)
HANDLER = "reports_cron"


# ----------------------------------------------------------------------------
# Time helpers
# ----------------------------------------------------------------------------

def _user_tz(user: dict) -> timezone:
    """Resolve a user's tz. We only support fixed UTC offsets without zoneinfo,
    so accept either a numeric offset (minutes) or fall back to UTC.
    """
    offset_minutes = user.get("tz_offset_minutes")
    if isinstance(offset_minutes, (int, float)):
        try:
            return timezone(timedelta(minutes=int(offset_minutes)))
        except (OverflowError, ValueError):
            pass
    # Try IANA name via zoneinfo if available.
    tz_name = user.get("timezone")
    if tz_name:
        try:
            from zoneinfo import ZoneInfo  # py3.9+
            return ZoneInfo(tz_name)  # type: ignore[return-value]
        except Exception:
            pass
    return timezone.utc


def _local_now(now_utc: datetime, user: dict) -> datetime:
    return now_utc.astimezone(_user_tz(user))


def _weekly_window(local_now: datetime) -> Tuple[datetime, datetime]:
    """Last completed Mon..Sun period in user's local time."""
    today = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    # weekday(): Monday=0, Sunday=6. We want last Monday inclusive, then +7d.
    days_since_monday = today.weekday()
    this_monday = today - timedelta(days=days_since_monday)
    last_monday = this_monday - timedelta(days=7)
    end = this_monday  # exclusive
    return last_monday, end


def _monthly_window(local_now: datetime) -> Tuple[datetime, datetime]:
    """Last completed calendar month in user's local time."""
    this_first = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Subtract one day -> in previous month, then snap to its 1st.
    last_month_any = this_first - timedelta(days=1)
    last_first = last_month_any.replace(day=1)
    return last_first, this_first


def _is_due(local_now: datetime, kind: str) -> bool:
    """Trigger window: matches when local hour == 8 and the day matches."""
    if local_now.hour != 8:
        return False
    if kind == "weekly":
        return local_now.weekday() == 0  # Monday
    if kind == "monthly":
        return local_now.day == 1
    return False


def _to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# ----------------------------------------------------------------------------
# Per-user generation
# ----------------------------------------------------------------------------

def _generate_for_user(user: dict, kind: str, period_start: datetime, period_end: datetime) -> Optional[dict]:
    user_id = user.get("user_id")
    if not user_id:
        return None

    start_iso = _to_iso(period_start)
    end_iso = _to_iso(period_end)

    workouts = get_user_workouts_in_range(user_id, start_iso, end_iso)
    if not workouts:
        log.info(f"reports_cron: user={user_id} kind={kind} no workouts in window; skipping")
        return None

    prior = get_user_workouts_before(user_id, start_iso)
    stats = aggregate(workouts, prior_workouts=prior)

    # Pull the recent rec feedback off the user record (set by reports_feedback).
    prior_feedback = user.get("report_feedback") or []
    recommendation = generate_recommendation(
        kind=kind,
        profile=user,
        stats=stats,
        prior_feedback=prior_feedback,
    )

    report = {
        "report_id": f"r-{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "kind": kind,
        "period_start": start_iso,
        "period_end": end_iso,
        "stats_json": stats,
        "recommendation_text": recommendation,
        "created_at": now_iso(),
        "read_at": None,
        "feedback_rating": None,
        "feedback_text": None,
    }
    put_report(report)
    log.info(
        f"reports_cron: created report={report['report_id']} user={user_id} "
        f"kind={kind} sessions={stats['sessions']} prs={len(stats['prs'])}"
    )

    # Push notification — best-effort, never fails the cron.
    try:
        device_token = user.get("apns_device_token")
        if device_token:
            title = "Weekly summary" if kind == "weekly" else "Monthly summary"
            body = (
                "Your weekly summary is ready"
                if kind == "weekly"
                else "Your monthly summary is ready"
            )
            send_report_notification(
                device_token=device_token,
                title=title,
                body=body,
                report_id=report["report_id"],
            )
    except Exception as e:
        log.error(f"reports_cron: APNs error for user={user_id}: {e}")

    return report


# ----------------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------------

@handle_errors(HANDLER)
def handler(event, context):
    event = event or {}

    # Parse "now"
    if event.get("now"):
        now_utc = datetime.fromisoformat(str(event["now"]).replace("Z", "+00:00"))
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)
    else:
        now_utc = datetime.now(timezone.utc)

    requested_kind = event.get("kind", "auto")
    force_user_id = event.get("force_user_id")
    dry_run = bool(event.get("dry_run"))

    users = scan_all_users()
    if force_user_id:
        users = [u for u in users if u.get("user_id") == force_user_id]

    created: list = []
    for user in users:
        local_now = _local_now(now_utc, user)

        kinds_to_run: list = []
        if requested_kind in ("weekly", "monthly"):
            kinds_to_run.append(requested_kind)
        else:  # auto
            if _is_due(local_now, "weekly") or force_user_id:
                kinds_to_run.append("weekly")
            if _is_due(local_now, "monthly") or force_user_id:
                kinds_to_run.append("monthly")

        for kind in kinds_to_run:
            window = (
                _weekly_window(local_now) if kind == "weekly"
                else _monthly_window(local_now)
            )
            if dry_run:
                log.info(
                    f"reports_cron[dry_run]: user={user.get('user_id')} kind={kind} "
                    f"window={_to_iso(window[0])}..{_to_iso(window[1])}"
                )
                continue
            try:
                result = _generate_for_user(user, kind, window[0], window[1])
                if result:
                    created.append({
                        "user_id": user.get("user_id"),
                        "kind": kind,
                        "report_id": result["report_id"],
                    })
            except Exception as e:
                # Never let a single user fail the whole cron.
                log.error(
                    f"reports_cron: failed for user={user.get('user_id')} "
                    f"kind={kind}: {e}"
                )

    log.info(f"reports_cron: completed; created={len(created)}")
    return {"statusCode": 200, "body": {"created": created}}
