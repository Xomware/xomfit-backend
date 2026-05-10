"""
POST /reports/{id}/feedback - Store user feedback on a report.

Body:
    rating  int, one of -1 | 0 | 1
    text    optional string

Feedback is stored on the report itself so it stays alongside the
recommendation, AND mirrored under the user record so the AI helper
(see issue #252) can pick up the user's recent rec feedback when building
future plans.
"""
from lambdas.common.logger import get_logger
from lambdas.common.errors import handle_errors, ValidationError
from lambdas.common.utility_helpers import (
    get_body,
    get_path_params,
    get_query_params,
    get_user_id,
    now_iso,
    success_response,
)
from lambdas.common.dynamo_helpers import (
    get_report,
    update_report,
    get_user,
    update_user,
)

log = get_logger(__file__)
HANDLER = "reports_feedback"

ALLOWED_RATINGS = {-1, 0, 1}
MAX_FEEDBACK_TEXT = 1000


@handle_errors(HANDLER)
def handler(event, context):
    user_id = get_user_id(event)
    body = get_body(event)

    report_id = (
        get_path_params(event).get("id")
        or get_path_params(event).get("report_id")
        or get_query_params(event).get("report_id")
        or body.get("report_id")
    )
    if not report_id:
        raise ValidationError("Missing required path parameter: id")

    if "rating" not in body:
        raise ValidationError("Missing required field: rating")
    try:
        rating = int(body["rating"])
    except (TypeError, ValueError):
        raise ValidationError("rating must be an integer (-1, 0, or 1)")
    if rating not in ALLOWED_RATINGS:
        raise ValidationError("rating must be -1, 0, or 1")

    text = body.get("text")
    if text is not None:
        if not isinstance(text, str):
            raise ValidationError("text must be a string")
        text = text.strip()[:MAX_FEEDBACK_TEXT]

    now = now_iso()
    updates = {
        "feedback_rating": rating,
        "feedback_text": text,
        "feedback_at": now,
    }
    result = update_report(user_id, report_id, updates)

    # Mirror the latest feedback onto the user record so the AI helper can use it.
    try:
        report = get_report(user_id, report_id)
        user = get_user(user_id)
        history = list(user.get("report_feedback", []) or [])
        history.insert(0, {
            "report_id": report_id,
            "kind": report.get("kind"),
            "period_start": report.get("period_start"),
            "rating": rating,
            "text": text,
            "at": now,
        })
        # Keep the 10 most recent.
        history = history[:10]
        update_user(user_id, {"report_feedback": history})
    except Exception as e:
        # Mirror is best-effort — do not fail the user-facing call.
        log.error(f"Failed to mirror feedback to user record: {e}")

    log.info(f"User {user_id} left feedback on report {report_id} (rating={rating})")
    return success_response(result)
