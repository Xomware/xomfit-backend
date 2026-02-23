"""
GET /user/data - Get user profile data
"""
from lambdas.common.logger import get_logger
from lambdas.common.errors import handle_errors
from lambdas.common.utility_helpers import get_query_params, get_user_id, success_response
from lambdas.common.dynamo_helpers import get_user

log = get_logger(__file__)
HANDLER = "user_data"


@handle_errors(HANDLER)
def handler(event, context):
    params = get_query_params(event)
    # Can fetch own data or another user's
    user_id = params.get("user_id") or get_user_id(event)

    user = get_user(user_id)
    log.info(f"Retrieved data for user {user_id}")
    return success_response(user)
