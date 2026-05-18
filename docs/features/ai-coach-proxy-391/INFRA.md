# Infra changes for #391 — Anthropic API proxy

This repo (xomfit-backend) only contains the Lambda handler. Tables, IAM,
the API Gateway route, and SSM entries are provisioned in
`xomfit-infrastructure` (Terraform). Below is the contract this code expects.

## Why this exists

The iOS client used to call `api.anthropic.com` directly with each user's
own API key. We want every user to share the same Haiku key, but shipping
that key in the iOS binary is unacceptable. This proxy:

1. Holds the Anthropic API key server-side (SSM SecureString).
2. Enforces a per-user, per-day message limit (default 50/day).
3. Logs per-request token usage for the weekly cost roll-up (#260).

## New Lambda — `ai_coach_proxy`

| Field         | Value                                          |
|---------------|------------------------------------------------|
| Logical name  | `ai_coach_proxy`                               |
| Handler path  | `lambdas.ai_coach_proxy.handler.handler`       |
| Runtime       | python3.12                                     |
| Timeout       | 60s (upstream Anthropic timeout is 55s)        |
| Memory        | 512 MB                                         |

### IAM permissions

* `dynamodb:GetItem`, `dynamodb:UpdateItem` on `xomfit-ai-coach-usage`
* `dynamodb:PutItem` on `xomfit-ai-coach-cost`
* `ssm:GetParameter` on `/xomfit/anthropic/api-key` (decrypt)
* Standard `logs:CreateLogGroup` / `logs:CreateLogStream` / `logs:PutLogEvents`

### Env vars

| Var                            | Source / default                                    | Notes                                          |
|--------------------------------|-----------------------------------------------------|------------------------------------------------|
| `ANTHROPIC_API_KEY`            | SSM SecureString `/xomfit/anthropic/api-key`        | Required. Never hard-code.                     |
| `ANTHROPIC_MODEL`              | `claude-haiku-4-5`                                  | Default model when client omits it.            |
| `AI_COACH_DAILY_LIMIT`         | `50`                                                | Per-user, per-day message cap.                 |
| `AI_COACH_ALLOWED_MODELS`      | `claude-haiku-4-5,claude-sonnet-4-6`                | Comma-separated allow-list. Empty = allow all. |
| `AI_COACH_DEFAULT_MAX_TOKENS`  | `1024`                                              | Used when the client omits `max_tokens`.       |
| `AI_COACH_MAX_TOKENS_CEILING`  | `4096`                                              | Hard cap clients cannot exceed.                |
| `ANTHROPIC_TIMEOUT_SECONDS`    | `55`                                                | Upstream request timeout.                      |
| `AI_COACH_USAGE_TABLE`         | `xomfit-ai-coach-usage`                             | Override only for tests.                       |
| `AI_COACH_COST_TABLE`          | `xomfit-ai-coach-cost`                              | Override only for tests.                       |

## New DynamoDB tables

### `xomfit-ai-coach-usage`

Per-user daily counter. One row per user per day.

| Attribute    | Type   | Notes                                       |
|--------------|--------|---------------------------------------------|
| `user_id` (PK) | String | FK to `xomfit-users.user_id`              |
| `date` (SK)    | String | `YYYYMMDD` UTC                            |
| `count`        | Number | Incremented atomically via `ADD :one`     |
| `updated_at`   | String | ISO8601 UTC of last increment             |

* Billing: on-demand. Traffic is low and bursty.
* TTL: optional — could set a `ttl` attribute = now + 90d to auto-prune
  old daily rows. Not required.

### `xomfit-ai-coach-cost`

Per-request token usage. Feeds the weekly aggregation (#260).

| Attribute    | Type   | Notes                                              |
|--------------|--------|----------------------------------------------------|
| `user_id` (PK) | String | FK to `xomfit-users.user_id`                     |
| `sk`           | String | `YYYYMMDD#<request_id>` — sorts by day naturally |
| `date`         | String | `YYYYMMDD` UTC                                   |
| `request_id`   | String | `aic-<12 hex>`                                   |
| `model`        | String | e.g. `claude-haiku-4-5`                          |
| `input_tokens` | Number |                                                  |
| `output_tokens`| Number |                                                  |
| `created_at`   | String | ISO8601 UTC                                      |

### Optional GSI: `date-user_id-index` on `xomfit-ai-coach-cost`

* PK: `date` (S)
* SK: `user_id` (S)
* Projection: ALL

Used if we want a daily/weekly cost roll-up across all users without a
table scan. Not required for v1 of the weekly report — the cron can
`Query(user_id)` per user with `begins_with(sk, "YYYYMMDD")`.

## SSM parameters

| Name                          | Type           | Notes                          |
|-------------------------------|----------------|--------------------------------|
| `/xomfit/anthropic/api-key`   | SecureString   | Dom's personal Anthropic key   |

Already exists for the reports cron (#260). The proxy Lambda reads the
same parameter.

## API Gateway route (JWT-authorized)

```
POST /ai-coach/messages          -> ai_coach_proxy
```

Authorizer: existing JWT authorizer (`lambdas/authorizer/handler.py`).
The handler reads `requestContext.authorizer.user_id` exactly like every
other authenticated route in this backend.

### Request / response shape

Mirrors Anthropic `/v1/messages`. Clients build the same body they used
to send to `api.anthropic.com`:

```json
{
  "model": "claude-haiku-4-5",
  "messages": [{ "role": "user", "content": "give me a workout" }],
  "system": "You are a coach.",
  "tools": [ ... ],
  "max_tokens": 1024
}
```

Success returns Anthropic's full JSON body with `200`. On the per-user
daily limit:

```json
{ "error": "Daily message limit reached. Try again tomorrow." }
```

with HTTP `429`.

## Streaming (deferred)

v1 forces `stream: false` server-side. SSE through API Gateway requires
either a Lambda Function URL with `InvokeMode=RESPONSE_STREAM` or a
separate WebSocket API. We'll add streaming as a follow-up — see TODO
in `handler.py` module docstring.

## Open questions for Dom

* Confirm `/xomfit/anthropic/api-key` already points at the Haiku-capable
  key (it does, but worth double-checking before flipping iOS over).
* Decide whether to keep the `claude-sonnet-4-6` entry in
  `AI_COACH_ALLOWED_MODELS` — Sonnet is ~3-5x cost vs Haiku. Cheap default
  is to ship with Haiku only.
