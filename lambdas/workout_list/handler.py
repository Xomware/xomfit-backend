"""
GET /workout/list - Get user's workout history
"""
from lambdas.common.logger import get_logger
from lambdas.common.errors import handle_errors
from lambdas.common.utility_helpers import get_query_params, get_user_id, success_response
from lambdas.common.dynamo_helpers import get_user_workouts

log = get_logger(__file__)
HANDLER = "workout_list"


@handle_errors(HANDLER)
def handler(event, context):
    user_id = get_user_id(event)
    params = get_query_params(event)
    limit = int(params.get("limit", 20))
    results = get_user_workouts(user_id, limit=limit)
    log.info(f"Retrieved {len(results)} workouts for user {user_id}")
    return success_response(results)
