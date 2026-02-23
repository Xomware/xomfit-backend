"""
POST /workout/create - Save a completed workout
"""
from lambdas.common.logger import get_logger
from lambdas.common.errors import handle_errors
from lambdas.common.utility_helpers import get_body, get_user_id, require_fields, created_response, generate_id, now_iso
from lambdas.common.dynamo_helpers import save_workout, post_to_feed, get_user, update_user

log = get_logger(__file__)
HANDLER = "workout_create"


@handle_errors(HANDLER)
def handler(event, context):
    user_id = get_user_id(event)
    body = get_body(event)
    require_fields(body, "name", "exercises", "started_at")

    workout_id = generate_id("w-")
    total_volume = 0
    total_sets = 0
    total_prs = 0

    for ex in body["exercises"]:
        for s in ex.get("sets", []):
            total_volume += float(s.get("weight", 0)) * int(s.get("reps", 0))
            total_sets += 1
            if s.get("is_personal_record"):
                total_prs += 1

    workout = {
        "workout_id": workout_id,
        "user_id": user_id,
        "name": body["name"],
        "exercises": body["exercises"],
        "started_at": body["started_at"],
        "ended_at": body.get("ended_at", now_iso()),
        "notes": body.get("notes", ""),
        "total_volume": int(total_volume),
        "total_sets": total_sets,
        "total_prs": total_prs,
        "created_at": now_iso(),
    }

    result = save_workout(workout)

    # Post to feed
    summary = {
        "name": workout["name"],
        "total_volume": workout["total_volume"],
        "total_sets": total_sets,
        "total_prs": total_prs,
        "exercise_count": len(body["exercises"]),
    }
    post_to_feed(user_id, workout_id, summary)

    # Update user stats
    try:
        user = get_user(user_id)
        stats = user.get("stats", {})
        update_user(user_id, {
            "stats": {
                **stats,
                "total_workouts": stats.get("total_workouts", 0) + 1,
                "total_volume": stats.get("total_volume", 0) + int(total_volume),
                "total_prs": stats.get("total_prs", 0) + total_prs,
            }
        })
    except Exception as e:
        log.error(f"Failed to update user stats: {e}")

    log.info(f"Workout {workout_id} saved for user {user_id} ({total_sets} sets, {int(total_volume)} lbs)")
    return created_response(result)
