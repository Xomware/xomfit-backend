# Infra changes for #260 — Weekly + Monthly Reports

This repo (xomfit-backend) is just the Lambda handlers. Tables, schedules,
and routes are provisioned in `xomfit-infrastructure` (Terraform). The
following is the schema/contract this code expects.

## New DynamoDB Table — `xomfit-reports`

| Attribute            | Type      | Notes                                  |
|----------------------|-----------|----------------------------------------|
| `report_id` (PK)     | String    | `r-<12 hex>`                           |
| `user_id`            | String    | FK to `xomfit-users.user_id`           |
| `kind`               | String    | `weekly` \| `monthly`                  |
| `period_start`       | String    | ISO8601 UTC, inclusive                 |
| `period_end`         | String    | ISO8601 UTC, exclusive                 |
| `stats_json`         | Map       | Aggregator output                      |
| `recommendation_text`| String    | ~80 word Claude-generated text         |
| `created_at`         | String    | ISO8601 UTC                            |
| `read_at`            | String    | nullable, ISO8601 UTC                  |
| `feedback_rating`    | Number    | nullable, -1 \| 0 \| 1                 |
| `feedback_text`      | String    | nullable, <= 1000 chars                |
| `feedback_at`        | String    | nullable, ISO8601 UTC                  |

### Required GSI: `user_id-period_start-index`

* PK: `user_id` (S)
* SK: `period_start` (S)
* Projection: ALL

Used by `list_user_reports`.

## Existing tables — additive fields

### `xomfit-users` (additive, no schema change in DynamoDB)

* `apns_device_token`        — string, set by iOS after push reg (#260 iOS task)
* `timezone`                 — IANA name (e.g. `America/New_York`) optional
* `tz_offset_minutes`        — integer, optional fallback when IANA unavailable
* `report_feedback`          — list of {report_id, kind, period_start, rating, text, at}
                               last 10 entries; mirrored from `reports_feedback` so
                               the AI helper (#252) can read it on profile fetch.

## Lambdas to provision

| Logical name        | Handler module path                         |
|---------------------|---------------------------------------------|
| reports_list        | `lambdas.reports_list.handler.handler`      |
| reports_read        | `lambdas.reports_read.handler.handler`      |
| reports_feedback    | `lambdas.reports_feedback.handler.handler`  |
| reports_cron        | `lambdas.reports_cron.handler.handler`      |

All four need IAM read/write on `xomfit-reports`. The cron also needs
`Query/Scan` on `xomfit-users` and `Query` on `xomfit-workouts` (existing GSI
`user_id-started_at-index`). The cron should have a 5-minute timeout.

## API Gateway routes (JWT-authorized)

```
GET  /reports                       -> reports_list
POST /reports/{id}/read             -> reports_read
POST /reports/{id}/feedback         -> reports_feedback
```

## Cron schedule

Single EventBridge rule:

```
cron(0 * * * ? *)   # every hour, on the hour, UTC
```

The Lambda decides per user (using their stored timezone) whether the
user's local clock is currently Monday 08:00 (weekly) or 1st-of-month
08:00 (monthly), and skips otherwise. This avoids per-user schedules
while still respecting timezones.

## Required env vars on Lambdas

Cron + handlers (set via SSM-backed Terraform variables, never hard-coded):

| Var                 | Lambdas                          | Notes                                      |
|---------------------|----------------------------------|--------------------------------------------|
| `REPORTS_TABLE`     | all                              | defaults to `xomfit-reports`               |
| `ANTHROPIC_API_KEY` | reports_cron                     | from SSM `/xomfit/anthropic/api-key`       |
| `ANTHROPIC_MODEL`   | reports_cron                     | optional override; default `claude-sonnet-4-6` |
| `APNS_KEY_ID`       | reports_cron                     | from SSM                                   |
| `APNS_TEAM_ID`      | reports_cron                     | from SSM                                   |
| `APNS_BUNDLE_ID`    | reports_cron                     | `com.xomware.xomfit`                       |
| `APNS_AUTH_KEY`     | reports_cron                     | full PEM of .p8 from SSM SecureString      |
| `APNS_HOST`         | reports_cron                     | `api.push.apple.com` (prod) / sandbox      |

## Open question for user (Dom)

* APNs Auth Key (.p8) needs to be generated in Apple Developer and uploaded
  to SSM as a SecureString. The Lambda reads via the standard SSM-backed
  env var mechanism already in use elsewhere. No change to handler code.
