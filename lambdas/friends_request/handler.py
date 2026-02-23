"""
POST /friends/request - Send a friend request
"""
from lambdas.common.logger import get_logger
from lambdas.common.errors import handle_errors, ValidationError
from lambdas.common.utility_helpers import get_body, get_user_id, require_fields, created_response
from lambdas.common.dynamo_helpers import add_friend_request

log = get_logger(__file__)
HANDLER = "friends_request"


@handle_errors(HANDLER)
def handler(event, context):
    user_id = get_user_id(event)
    body = get_body(event)
    require_fields(body, "to_user_id")

    if body["to_user_id"] == user_id:
        raise ValidationError("Cannot send friend request to yourself")

    result = add_friend_request(user_id, body["to_user_id"])
    log.info(f"Friend request: {user_id} -> {body['to_user_id']}")
    return created_response(result)
