"""
GET /friends/list - Get user's friends list
"""
from lambdas.common.logger import get_logger
from lambdas.common.errors import handle_errors
from lambdas.common.utility_helpers import get_user_id, success_response
from lambdas.common.dynamo_helpers import get_friends, get_user

log = get_logger(__file__)
HANDLER = "friends_list"


@handle_errors(HANDLER)
def handler(event, context):
    user_id = get_user_id(event)
    friends = get_friends(user_id)

    enriched = []
    for f in friends:
        try:
            user = get_user(f["friend_id"])
            enriched.append({
                "user_id": f["friend_id"],
                "display_name": user.get("display_name", ""),
                "username": user.get("username", ""),
                "avatar_url": user.get("avatar_url", ""),
                "since": f.get("since", ""),
            })
        except Exception:
            pass

    log.info(f"User {user_id} has {len(enriched)} friends")
    return success_response(enriched)
