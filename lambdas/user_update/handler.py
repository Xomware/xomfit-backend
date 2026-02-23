"""
POST /user/update - Update user profile
"""
from lambdas.common.logger import get_logger
from lambdas.common.errors import handle_errors
from lambdas.common.utility_helpers import get_body, get_user_id, success_response
from lambdas.common.dynamo_helpers import update_user

log = get_logger(__file__)
HANDLER = "user_update"

ALLOWED_FIELDS = {"display_name", "bio", "avatar_url", "is_private"}


@handle_errors(HANDLER)
def handler(event, context):
    user_id = get_user_id(event)
    body = get_body(event)

    updates = {k: v for k, v in body.items() if k in ALLOWED_FIELDS}
    if not updates:
        return success_response(message="nothing to update")

    result = update_user(user_id, updates)
    log.info(f"Updated user {user_id}: {list(updates.keys())}")
    return success_response(result)
