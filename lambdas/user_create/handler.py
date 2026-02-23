"""
POST /user/create - Create a new user profile
"""
from lambdas.common.logger import get_logger
from lambdas.common.errors import handle_errors, ConflictError
from lambdas.common.utility_helpers import get_body, get_user_id, require_fields, created_response, generate_id, now_iso
from lambdas.common.dynamo_helpers import put_user, get_user

log = get_logger(__file__)
HANDLER = "user_create"


@handle_errors(HANDLER)
def handler(event, context):
    user_id = get_user_id(event)
    body = get_body(event)
    require_fields(body, "username", "display_name")

    user = {
        "user_id": user_id,
        "username": body["username"].lower().strip(),
        "display_name": body["display_name"],
        "avatar_url": body.get("avatar_url", ""),
        "bio": body.get("bio", ""),
        "stats": {
            "total_workouts": 0,
            "total_volume": 0,
            "total_prs": 0,
            "current_streak": 0,
            "longest_streak": 0,
        },
        "is_private": body.get("is_private", False),
        "created_at": now_iso(),
    }

    result = put_user(user)
    log.info(f"Created user {user_id} (@{user['username']})")
    return created_response(result)
