"""
POST /friends/accept - Accept a friend request
"""
from lambdas.common.logger import get_logger
from lambdas.common.errors import handle_errors
from lambdas.common.utility_helpers import get_body, get_user_id, require_fields, success_response
from lambdas.common.dynamo_helpers import accept_friend

log = get_logger(__file__)
HANDLER = "friends_accept"


@handle_errors(HANDLER)
def handler(event, context):
    user_id = get_user_id(event)
    body = get_body(event)
    require_fields(body, "friend_id")

    accept_friend(user_id, body["friend_id"])
    log.info(f"Friend accepted: {user_id} <-> {body['friend_id']}")
    return success_response(message="friend accepted")
