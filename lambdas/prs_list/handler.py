"""
GET /prs/list - Get user's personal records
"""
from lambdas.common.logger import get_logger
from lambdas.common.errors import handle_errors
from lambdas.common.utility_helpers import get_query_params, get_user_id, success_response
from lambdas.common.dynamo_helpers import get_user_prs

log = get_logger(__file__)
HANDLER = "prs_list"


@handle_errors(HANDLER)
def handler(event, context):
    user_id = get_user_id(event)
    params = get_query_params(event)
    target = params.get("user_id", user_id)

    prs = get_user_prs(target)
    prs.sort(key=lambda x: x.get("estimated_1rm", 0), reverse=True)

    log.info(f"Retrieved {len(prs)} PRs for user {target}")
    return success_response(prs)
