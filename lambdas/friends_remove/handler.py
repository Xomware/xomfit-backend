"""
POST /friends/remove - Remove a friend
"""
import os, boto3
from lambdas.common.logger import get_logger
from lambdas.common.errors import handle_errors
from lambdas.common.utility_helpers import get_body, get_user_id, require_fields, success_response

log = get_logger(__file__)
HANDLER = "friends_remove"
dynamodb = boto3.resource("dynamodb")
SOCIAL_TABLE = os.environ.get("SOCIAL_TABLE", "xomfit-social")


@handle_errors(HANDLER)
def handler(event, context):
    user_id = get_user_id(event)
    body = get_body(event)
    require_fields(body, "friend_id")

    table = dynamodb.Table(SOCIAL_TABLE)
    # Remove bidirectional
    table.delete_item(Key={"user_id": user_id, "sk": f"friend#{body['friend_id']}"})
    table.delete_item(Key={"user_id": body["friend_id"], "sk": f"friend#{user_id}"})

    log.info(f"Friendship removed: {user_id} <-> {body['friend_id']}")
    return success_response(message="friend removed")
