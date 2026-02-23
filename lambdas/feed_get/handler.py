"""
GET /feed/get - Get social feed (friends' workouts)
"""
from lambdas.common.logger import get_logger
from lambdas.common.errors import handle_errors
from lambdas.common.utility_helpers import get_query_params, get_user_id, success_response
from lambdas.common.dynamo_helpers import get_feed, get_user

log = get_logger(__file__)
HANDLER = "feed_get"


@handle_errors(HANDLER)
def handler(event, context):
    user_id = get_user_id(event)
    params = get_query_params(event)
    limit = int(params.get("limit", 20))

    posts = get_feed(user_id, limit=limit)

    # Enrich with user data
    user_cache = {}
    for post in posts:
        pid = post["user_id"]
        if pid not in user_cache:
            try:
                user_cache[pid] = get_user(pid)
            except Exception:
                user_cache[pid] = {"user_id": pid, "display_name": "Unknown"}
        post["user"] = {
            "user_id": pid,
            "display_name": user_cache[pid].get("display_name", ""),
            "username": user_cache[pid].get("username", ""),
            "avatar_url": user_cache[pid].get("avatar_url", ""),
        }

    log.info(f"Feed for {user_id}: {len(posts)} posts")
    return success_response(posts)
