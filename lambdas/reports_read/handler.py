"""
POST /reports/{id}/read - Mark a report as read.
"""
from lambdas.common.logger import get_logger
from lambdas.common.errors import handle_errors, ValidationError
from lambdas.common.utility_helpers import (
    get_path_params,
    get_query_params,
    get_user_id,
    now_iso,
    success_response,
)
from lambdas.common.dynamo_helpers import update_report

log = get_logger(__file__)
HANDLER = "reports_read"


@handle_errors(HANDLER)
def handler(event, context):
    user_id = get_user_id(event)

    # Path param when routed via /reports/{id}/read; fallback to query for direct invokes.
    report_id = (
        get_path_params(event).get("id")
        or get_path_params(event).get("report_id")
        or get_query_params(event).get("report_id")
    )
    if not report_id:
        raise ValidationError("Missing required path parameter: id")

    result = update_report(user_id, report_id, {"read_at": now_iso()})
    log.info(f"User {user_id} marked report {report_id} as read")
    return success_response(result)
