"""
XOMFIT Utility Helpers
"""

import json
import decimal
import uuid
from datetime import datetime
from typing import Any, Optional

from lambdas.common.logger import get_logger
from lambdas.common.errors import ValidationError

log = get_logger(__file__)


class XomFitJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, set):
            return list(obj)
        return super().default(obj)


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, cls=XomFitJSONEncoder)


def success_response(data: Any = None, status: int = 200, message: str = "ok") -> dict:
    body = {"status": message}
    if data is not None:
        body["data"] = data
    return {
        "statusCode": status,
        "headers": {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"},
        "body": json_dumps(body),
        "isBase64Encoded": False
    }


def created_response(data: Any = None) -> dict:
    return success_response(data, status=201, message="created")


def get_body(event: dict) -> dict:
    body = event.get("body", "{}")
    if isinstance(body, str):
        return json.loads(body) if body else {}
    return body or {}


def get_query_params(event: dict) -> dict:
    return event.get("queryStringParameters") or {}


def get_path_params(event: dict) -> dict:
    return event.get("pathParameters") or {}


def get_user_id(event: dict) -> str:
    """Extract user ID from authorizer context."""
    try:
        return event["requestContext"]["authorizer"]["user_id"]
    except (KeyError, TypeError):
        raise ValidationError("Missing user authentication")


def require_fields(data: dict, *fields: str):
    missing = [f for f in fields if not data.get(f)]
    if missing:
        raise ValidationError(f"Missing required fields: {', '.join(missing)}")


def generate_id(prefix: str = "") -> str:
    short_id = str(uuid.uuid4())[:8]
    return f"{prefix}{short_id}" if prefix else short_id


def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"
