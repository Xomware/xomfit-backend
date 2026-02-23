"""
POST /feed/comment - Add a comment to a feed post
"""
import os
import boto3
from lambdas.common.logger import get_logger
from lambdas.common.errors import handle_errors
from lambdas.common.utility_helpers import get_body, get_user_id, require_fields, success_response, generate_id, now_iso

log = get_logger(__file__)
HANDLER = "feed_comment"
dynamodb = boto3.resource("dynamodb")
FEED_TABLE = os.environ.get("FEED_TABLE", "xomfit-feed")


@handle_errors(HANDLER)
def handler(event, context):
    user_id = get_user_id(event)
    body = get_body(event)
    require_fields(body, "post_user_id", "post_sk", "text")

    comment = {"id": generate_id("c-"), "user_id": user_id, "text": body["text"], "created_at": now_iso()}

    table = dynamodb.Table(FEED_TABLE)
    table.update_item(
        Key={"user_id": body["post_user_id"], "sk": body["post_sk"]},
        UpdateExpression="SET comments = list_append(if_not_exists(comments, :empty), :c)",
        ExpressionAttributeValues={":c": [comment], ":empty": []}
    )

    log.info(f"User {user_id} commented on {body['post_sk']}")
    return success_response(comment)
