"""
GET /friends/pending - Get pending friend requests
"""
from lambdas.common.logger import get_logger
from lambdas.common.errors import handle_errors
from lambdas.common.utility_helpers import get_user_id, success_response
from lambdas.common.dynamo_helpers import get_pending_requests, get_user

log = get_logger(__file__)
HANDLER = "friends_pending"


@handle_errors(HANDLER)
def handler(event, context):
    user_id = get_user_id(event)
    requests = get_pending_requests(user_id)

    enriched = []
    for r in requests:
        try:
            user = get_user(r["from_user_id"])
            enriched.append({
                "user_id": r["from_user_id"],
                "display_name": user.get("display_name", ""),
                "username": user.get("username", ""),
                "avatar_url": user.get("avatar_url", ""),
                "requested_at": r.get("created_at", ""),
            })
        except Exception:
            pass

    return success_response(enriched)
