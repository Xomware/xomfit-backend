"""
POST /workout/delete - Delete a workout
"""
import os, boto3
from lambdas.common.logger import get_logger
from lambdas.common.errors import handle_errors, UnauthorizedError
from lambdas.common.utility_helpers import get_body, get_user_id, require_fields, success_response
from lambdas.common.dynamo_helpers import get_workout

log = get_logger(__file__)
HANDLER = "workout_delete"
dynamodb = boto3.resource("dynamodb")
WORKOUTS_TABLE = os.environ.get("WORKOUTS_TABLE", "xomfit-workouts")


@handle_errors(HANDLER)
def handler(event, context):
    user_id = get_user_id(event)
    body = get_body(event)
    require_fields(body, "workout_id")

    workout = get_workout(body["workout_id"])
    if workout["user_id"] != user_id:
        raise UnauthorizedError("Cannot delete another user's workout")

    table = dynamodb.Table(WORKOUTS_TABLE)
    table.delete_item(Key={"workout_id": body["workout_id"]})

    log.info(f"Workout {body['workout_id']} deleted by {user_id}")
    return success_response(message="workout deleted")
