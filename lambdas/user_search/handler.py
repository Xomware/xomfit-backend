"""
GET /user/search - Search for users by username
"""
from lambdas.common.logger import get_logger
from lambdas.common.errors import handle_errors, ValidationError
from lambdas.common.utility_helpers import get_query_params, success_response
from lambdas.common.dynamo_helpers import search_users

log = get_logger(__file__)
HANDLER = "user_search"


@handle_errors(HANDLER)
def handler(event, context):
    params = get_query_params(event)
    query = params.get("q", "").strip()
    if len(query) < 2:
        raise ValidationError("Search query must be at least 2 characters")

    results = search_users(query, limit=int(params.get("limit", 20)))
    log.info(f"Search '{query}' returned {len(results)} results")
    return success_response(results)
