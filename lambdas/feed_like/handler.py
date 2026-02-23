"""
POST /feed/like - Like/unlike a feed post
"""
import os
import boto3
from boto3.dynamodb.conditions import Key
from lambdas.common.logger import get_logger
from lambdas.common.errors import handle_errors
from lambdas.common.utility_helpers import get_body, get_user_id, require_fields, success_response

log = get_logger(__file__)
HANDLER = "feed_like"

dynamodb = boto3.resource("dynamodb")
FEED_TABLE = os.environ.get("FEED_TABLE", "xomfit-feed")


@handle_errors(HANDLER)
def handler(event, context):
    user_id = get_user_id(event)
    body = get_body(event)
    require_fields(body, "post_user_id", "post_sk")

    table = dynamodb.Table(FEED_TABLE)
    # Increment likes
    resp = table.update_item(
        Key={"user_id": body["post_user_id"], "sk": body["post_sk"]},
        UpdateExpression="SET likes = likes + :inc",
        ExpressionAttributeValues={":inc": 1},
        ReturnValues="ALL_NEW"
    )

    log.info(f"User {user_id} liked post {body['post_sk']}")
    return success_response({"likes": resp["Attributes"].get("likes", 0)})
