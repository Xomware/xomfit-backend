"""
GET /workout/get - Get a single workout by ID
"""
from lambdas.common.logger import get_logger
from lambdas.common.errors import handle_errors
from lambdas.common.utility_helpers import get_query_params, require_fields, success_response
from lambdas.common.dynamo_helpers import get_workout

log = get_logger(__file__)
HANDLER = "workout_get"


@handle_errors(HANDLER)
def handler(event, context):
    params = get_query_params(event)
    require_fields(params, "workout_id")
    result = get_workout(params["workout_id"])
    return success_response(result)
