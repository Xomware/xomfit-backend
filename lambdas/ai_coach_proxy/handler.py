"""
POST /ai-coach/messages — Anthropic Messages API proxy.

Why this exists
---------------
The iOS app used to call api.anthropic.com directly using each user's own
Anthropic API key (set in Settings → Anthropic API Key). We want every user
to share the same Haiku key, but shipping that key in the iOS binary is a
non-starter. This Lambda holds the key, enforces a per-user daily message
limit, and logs token usage so we can roll up cost weekly.

Request body
------------
Same shape the iOS client sends to Anthropic today:

    {
        "model": "claude-haiku-4-5",
        "messages": [...],
        "system": "...",          # optional
        "tools": [...],           # optional
        "max_tokens": 1024,
        "stream": false           # currently forced false server-side
    }

Streaming
---------
Anthropic's `/v1/messages` SSE stream is supported by their REST API, but
proxying SSE through API Gateway requires either response streaming
(Lambda Function URLs) or WebSockets. The rest of this backend is regular
HTTP-Lambda + API Gateway, so v1 of this proxy forces `stream: false`
server-side and returns the full Anthropic JSON body in one shot.
TODO(#391): swap to a Lambda Function URL with `InvokeMode=RESPONSE_STREAM`
so we can pipe SSE chunks straight through.

Rate limiting
-------------
Per-user, per-day. Counter lives in DynamoDB table `xomfit-ai-coach-usage`
keyed by (user_id, date) where date is YYYYMMDD UTC. Limit is 50/day.
Pre-check is best-effort (eventually consistent) and we increment on
success to avoid charging users for failed Anthropic calls. There's a
small race window where two concurrent requests could push a user one
over the limit; that's acceptable for a personal-app daily cap.

Cost logging
------------
Per-request token usage (input_tokens + output_tokens from
`response.usage`) is written to `xomfit-ai-coach-cost`. The weekly
reports cron (#260) reads from this table to surface usage.
"""
import json
import os
import uuid
from datetime import datetime, timezone

import requests

from lambdas.common.logger import get_logger
from lambdas.common.errors import (
    handle_errors,
    ValidationError,
    XomFitError,
)
from lambdas.common.utility_helpers import (
    get_body,
    get_user_id,
    json_dumps,
)
from lambdas.common.dynamo_helpers import (
    get_ai_coach_daily_count,
    increment_ai_coach_daily_count,
    put_ai_coach_cost,
)

log = get_logger(__file__)
HANDLER = "ai_coach_proxy"

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_TIMEOUT_SECONDS = int(os.environ.get("ANTHROPIC_TIMEOUT_SECONDS", "55"))

DEFAULT_DAILY_LIMIT = 50
DAILY_LIMIT = int(os.environ.get("AI_COACH_DAILY_LIMIT", DEFAULT_DAILY_LIMIT))

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")
DEFAULT_MAX_TOKENS = int(os.environ.get("AI_COACH_DEFAULT_MAX_TOKENS", "1024"))

# Hard cap so a client cannot ask for an absurd response size.
MAX_TOKENS_CEILING = int(os.environ.get("AI_COACH_MAX_TOKENS_CEILING", "4096"))

# Allow-list of models. Empty string -> allow anything Anthropic accepts.
# Comma-separated. Default keeps us on the cheap models.
_allowed_raw = os.environ.get("AI_COACH_ALLOWED_MODELS", "claude-haiku-4-5,claude-sonnet-4-6")
ALLOWED_MODELS = {m.strip() for m in _allowed_raw.split(",") if m.strip()}


def _today_yyyymmdd() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _rate_limited_response() -> dict:
    """Build the 429 response. Not a XomFitError because the shape is fixed
    by the spec (`{error: "..."}`) for direct iOS client consumption."""
    return {
        "statusCode": 429,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json",
        },
        "body": json.dumps(
            {"error": "Daily message limit reached. Try again tomorrow."}
        ),
        "isBase64Encoded": False,
    }


def _passthrough_response(status: int, body: dict) -> dict:
    """Wrap an Anthropic JSON response for API Gateway. Always returns
    `application/json` regardless of upstream status — clients keep the
    same decode path."""
    return {
        "statusCode": status,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json",
        },
        "body": json_dumps(body),
        "isBase64Encoded": False,
    }


def _validate_body(body: dict) -> dict:
    """Validate + normalize the incoming Anthropic-shaped body. Returns
    the payload we will forward."""
    if not isinstance(body, dict):
        raise ValidationError("Body must be a JSON object")

    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValidationError("`messages` must be a non-empty array")

    # Light shape check — the upstream API will surface deeper errors.
    for idx, m in enumerate(messages):
        if not isinstance(m, dict) or "role" not in m or "content" not in m:
            raise ValidationError(
                f"messages[{idx}] must have `role` and `content`"
            )

    model = body.get("model") or DEFAULT_MODEL
    if ALLOWED_MODELS and model not in ALLOWED_MODELS:
        raise ValidationError(f"Model `{model}` is not allowed")

    try:
        max_tokens = int(body.get("max_tokens") or DEFAULT_MAX_TOKENS)
    except (TypeError, ValueError):
        raise ValidationError("`max_tokens` must be an integer")
    if max_tokens <= 0:
        raise ValidationError("`max_tokens` must be > 0")
    max_tokens = min(max_tokens, MAX_TOKENS_CEILING)

    payload: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        # v1: force non-streaming server-side. See module docstring.
        "stream": False,
    }

    # Optional passthrough fields.
    if "system" in body and body["system"] is not None:
        payload["system"] = body["system"]
    if "tools" in body and body["tools"] is not None:
        payload["tools"] = body["tools"]
    if "tool_choice" in body and body["tool_choice"] is not None:
        payload["tool_choice"] = body["tool_choice"]
    if "temperature" in body and body["temperature"] is not None:
        payload["temperature"] = body["temperature"]
    if "stop_sequences" in body and body["stop_sequences"] is not None:
        payload["stop_sequences"] = body["stop_sequences"]
    if "metadata" in body and body["metadata"] is not None:
        payload["metadata"] = body["metadata"]

    return payload


def _call_anthropic(payload: dict, api_key: str, request_id: str) -> tuple:
    """Forward the payload to Anthropic. Returns (status_code, json_body).

    Never raises on HTTP errors — the upstream response is passed through
    so the client sees actionable error detail. Raises XomFitError only on
    transport / parse failures.
    """
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
        # Useful for grepping CloudWatch + Anthropic logs.
        "x-xomfit-request-id": request_id,
    }
    try:
        resp = requests.post(
            ANTHROPIC_API_URL,
            headers=headers,
            data=json.dumps(payload),
            timeout=ANTHROPIC_TIMEOUT_SECONDS,
        )
    except requests.RequestException as e:
        log.error(f"Anthropic transport error (req={request_id}): {e}")
        raise XomFitError(
            message="Upstream model service unavailable",
            handler=HANDLER,
            function="_call_anthropic",
            status=502,
        )

    try:
        body = resp.json()
    except ValueError:
        log.error(
            f"Anthropic non-JSON response (req={request_id}) "
            f"status={resp.status_code} body={resp.text[:300]}"
        )
        raise XomFitError(
            message="Upstream model service returned invalid response",
            handler=HANDLER,
            function="_call_anthropic",
            status=502,
        )
    return resp.status_code, body


def _extract_usage(body: dict) -> tuple:
    """Pull (input_tokens, output_tokens) from an Anthropic response."""
    usage = body.get("usage") or {}
    try:
        input_tokens = int(usage.get("input_tokens") or 0)
    except (TypeError, ValueError):
        input_tokens = 0
    try:
        output_tokens = int(usage.get("output_tokens") or 0)
    except (TypeError, ValueError):
        output_tokens = 0
    return input_tokens, output_tokens


@handle_errors(HANDLER)
def handler(event, context):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        # This is a deploy-time misconfiguration, not a client error.
        log.error("ANTHROPIC_API_KEY is not set")
        raise XomFitError(
            message="AI coach is not configured",
            handler=HANDLER,
            function="handler",
            status=503,
        )

    user_id = get_user_id(event)
    body = get_body(event)
    payload = _validate_body(body)

    # --- rate limit (pre-check, best-effort) -------------------------------
    today = _today_yyyymmdd()
    current = get_ai_coach_daily_count(user_id, today)
    if current >= DAILY_LIMIT:
        log.info(
            f"ai_coach_proxy: user={user_id} rate-limited "
            f"(count={current}, limit={DAILY_LIMIT})"
        )
        return _rate_limited_response()

    # --- forward -----------------------------------------------------------
    request_id = f"aic-{uuid.uuid4().hex[:12]}"
    status, response_body = _call_anthropic(payload, api_key, request_id)

    if status >= 400:
        # Anthropic 4xx/5xx — surface to client without incrementing the
        # counter or logging cost (no tokens billed if it errored hard).
        log.warning(
            f"ai_coach_proxy: upstream {status} for user={user_id} "
            f"req={request_id} body={json.dumps(response_body)[:300]}"
        )
        return _passthrough_response(status, response_body)

    # --- accounting (success path) -----------------------------------------
    try:
        new_count = increment_ai_coach_daily_count(user_id, today)
        log.info(
            f"ai_coach_proxy: user={user_id} req={request_id} "
            f"count={new_count}/{DAILY_LIMIT}"
        )
    except Exception as e:
        # Counter failure should not block the user's response — log loudly.
        log.error(f"ai_coach_proxy: counter increment failed user={user_id}: {e}")

    try:
        input_tokens, output_tokens = _extract_usage(response_body)
        put_ai_coach_cost(
            user_id=user_id,
            date_yyyymmdd=today,
            request_id=request_id,
            model=payload["model"],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        log.info(
            f"ai_coach_proxy: cost logged user={user_id} req={request_id} "
            f"in={input_tokens} out={output_tokens} model={payload['model']}"
        )
    except Exception as e:
        # Cost logging is best-effort. The user already got their response.
        log.error(f"ai_coach_proxy: cost log failed user={user_id}: {e}")

    return _passthrough_response(status, response_body)
