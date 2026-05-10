# XomFit Backend 💪

Python Lambda backend for XomFit — social fitness & lifting tracker.

## Architecture

- **Runtime:** Python 3.12 on AWS Lambda
- **API:** API Gateway (REST) using [api-gateway-service](https://github.com/domgiordano/api-gateway-service) module
- **Database:** DynamoDB
- **Auth:** JWT Lambda Authorizer

## API Endpoints

### User Service (`/user`)
| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| POST | /user/create | user_create | Create user profile |
| GET | /user/data | user_data | Get user profile |
| POST | /user/update | user_update | Update profile fields |
| GET | /user/search | user_search | Search users by username |

### Workout Service (`/workout`)
| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| POST | /workout/create | workout_create | Save completed workout |
| GET | /workout/get | workout_get | Get single workout |
| GET | /workout/list | workout_list | User's workout history |
| POST | /workout/delete | workout_delete | Delete a workout |

### Feed Service (`/feed`)
| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| GET | /feed/get | feed_get | Social feed (friends' workouts) |
| POST | /feed/like | feed_like | Like a feed post |
| POST | /feed/comment | feed_comment | Comment on a post |

### Friends Service (`/friends`)
| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| POST | /friends/request | friends_request | Send friend request |
| POST | /friends/accept | friends_accept | Accept friend request |
| POST | /friends/reject | friends_reject | Reject friend request |
| GET | /friends/list | friends_list | Get friends list |
| GET | /friends/pending | friends_pending | Get pending requests |
| POST | /friends/remove | friends_remove | Remove a friend |

### PRs Service (`/prs`)
| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| GET | /prs/list | prs_list | Get personal records |

### Exercises Service (`/exercises`)
| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| GET | /exercises/list | exercises_list | Browse exercise library |

### Reports Service (`/reports`)
| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| GET | /reports | reports_list | List current user's reports (newest first) |
| POST | /reports/{id}/read | reports_read | Mark a report as read |
| POST | /reports/{id}/feedback | reports_feedback | Store rating + optional text on a report |

The cron handler `reports_cron` is invoked by EventBridge on an hourly
schedule. It iterates users, computes weekly (Mon..Sun) and monthly
(calendar month) windows in each user's local timezone, generates stats +
a Claude recommendation, persists a `user_report` row, and fires an APNs
push when an `apns_device_token` is present on the user.

## DynamoDB Tables

| Table | Partition Key | Sort Key | GSIs |
|-------|--------------|----------|------|
| xomfit-users | user_id | — | — |
| xomfit-workouts | workout_id | — | user_id-started_at-index |
| xomfit-social | user_id | sk | — |
| xomfit-feed | user_id | sk | — |
| xomfit-reports | report_id | — | user_id-period_start-index |

## Project Structure
```
lambdas/
├── common/              # Shared utilities
│   ├── errors.py       # Error classes + handler decorator
│   ├── logger.py       # Logging
│   ├── utility_helpers.py  # Request parsing, responses
│   └── dynamo_helpers.py   # DynamoDB operations
├── authorizer/         # JWT Lambda authorizer
├── user_*/             # User service handlers
├── workout_*/          # Workout service handlers
├── feed_*/             # Feed service handlers
├── friends_*/          # Friends service handlers
├── prs_list/           # PR service handler
└── exercises_list/     # Exercise library handler
```

## Related Repos
- [xomfit-ios](https://github.com/Xomware/xomfit-ios) — iOS app
- [xomfit-infrastructure](https://github.com/Xomware/xomfit-infrastructure) — Terraform/AWS infra
