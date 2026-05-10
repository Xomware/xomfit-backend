"""
GET /reports - List the current user's reports newest first.

Query params:
    kind   optional, "weekly" | "monthly"
    limit  optional, default 50
"""
from lambdas.common.logger import get_logger
from lambdas.common.errors import handle_errors, ValidationError
from lambdas.common.utility_helpers import get_query_params, get_user_id, success_response
from lambdas.common.dynamo_helpers import list_user_reports

log = get_logger(__file__)
HANDLER = "reports_list"

ALLOWED_KINDS = {"weekly", "monthly"}


@handle_errors(HANDLER)
def handler(event, context):
    user_id = get_user_id(event)
    params = get_query_params(event)

    kind = params.get("kind")
    if kind and kind not in ALLOWED_KINDS:
        raise ValidationError(f"kind must be one of {sorted(ALLOWED_KINDS)}")

    try:
        limit = int(params.get("limit", 50))
    except (TypeError, ValueError):
        raise ValidationError("limit must be an integer")
    limit = max(1, min(limit, 200))

    reports = list_user_reports(user_id, kind=kind, limit=limit)
    log.info(f"Listed {len(reports)} reports for user {user_id} (kind={kind or 'any'})")
    return success_response(reports)
