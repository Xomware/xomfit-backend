"""
XOMFIT DynamoDB Helpers
"""

import os
import boto3
from boto3.dynamodb.conditions import Key, Attr
from typing import Any, Optional
from lambdas.common.logger import get_logger
from lambdas.common.errors import NotFoundError

log = get_logger(__file__)

dynamodb = boto3.resource("dynamodb")

# Table names from environment
USERS_TABLE = os.environ.get("USERS_TABLE", "xomfit-users")
WORKOUTS_TABLE = os.environ.get("WORKOUTS_TABLE", "xomfit-workouts")
EXERCISES_TABLE = os.environ.get("EXERCISES_TABLE", "xomfit-exercises")
SOCIAL_TABLE = os.environ.get("SOCIAL_TABLE", "xomfit-social")
FEED_TABLE = os.environ.get("FEED_TABLE", "xomfit-feed")


# ============================================
# Users
# ============================================

def get_user(user_id: str) -> dict:
    table = dynamodb.Table(USERS_TABLE)
    resp = table.get_item(Key={"user_id": user_id})
    item = resp.get("Item")
    if not item:
        raise NotFoundError(f"User {user_id} not found")
    return item


def put_user(user_data: dict) -> dict:
    table = dynamodb.Table(USERS_TABLE)
    table.put_item(Item=user_data)
    return user_data


def update_user(user_id: str, updates: dict) -> dict:
    table = dynamodb.Table(USERS_TABLE)
    expr_parts = []
    expr_values = {}
    expr_names = {}
    for key, val in updates.items():
        safe_key = f"#{key}"
        expr_parts.append(f"{safe_key} = :{key}")
        expr_values[f":{key}"] = val
        expr_names[safe_key] = key

    resp = table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET " + ", ".join(expr_parts),
        ExpressionAttributeValues=expr_values,
        ExpressionAttributeNames=expr_names,
        ReturnValues="ALL_NEW"
    )
    return resp.get("Attributes", {})


def search_users(query: str, limit: int = 20) -> list:
    table = dynamodb.Table(USERS_TABLE)
    resp = table.scan(
        FilterExpression=Attr("username").contains(query.lower()) | Attr("display_name").contains(query),
        Limit=limit
    )
    return resp.get("Items", [])


# ============================================
# Workouts
# ============================================

def save_workout(workout: dict) -> dict:
    table = dynamodb.Table(WORKOUTS_TABLE)
    table.put_item(Item=workout)
    return workout


def get_workout(workout_id: str) -> dict:
    table = dynamodb.Table(WORKOUTS_TABLE)
    resp = table.get_item(Key={"workout_id": workout_id})
    item = resp.get("Item")
    if not item:
        raise NotFoundError(f"Workout {workout_id} not found")
    return item


def get_user_workouts(user_id: str, limit: int = 20) -> list:
    table = dynamodb.Table(WORKOUTS_TABLE)
    resp = table.query(
        IndexName="user_id-started_at-index",
        KeyConditionExpression=Key("user_id").eq(user_id),
        ScanIndexForward=False,
        Limit=limit
    )
    return resp.get("Items", [])


def get_user_prs(user_id: str) -> list:
    """Get all PRs for a user from their workouts."""
    workouts = get_user_workouts(user_id, limit=100)
    prs = {}  # exercise_id -> best set
    for workout in workouts:
        for exercise in workout.get("exercises", []):
            ex_id = exercise["exercise_id"]
            for s in exercise.get("sets", []):
                weight = float(s.get("weight", 0))
                reps = int(s.get("reps", 0))
                est_1rm = weight * (1 + reps / 30.0) if reps > 1 else weight
                if ex_id not in prs or est_1rm > prs[ex_id]["estimated_1rm"]:
                    prs[ex_id] = {
                        "exercise_id": ex_id,
                        "exercise_name": exercise.get("exercise_name", ""),
                        "weight": weight,
                        "reps": reps,
                        "estimated_1rm": est_1rm,
                        "date": s.get("completed_at", workout.get("started_at", "")),
                    }
    return list(prs.values())


# ============================================
# Social / Friends
# ============================================

def get_friends(user_id: str) -> list:
    table = dynamodb.Table(SOCIAL_TABLE)
    resp = table.query(
        KeyConditionExpression=Key("user_id").eq(user_id) & Key("sk").begins_with("friend#"),
    )
    return resp.get("Items", [])


def add_friend_request(from_id: str, to_id: str) -> dict:
    table = dynamodb.Table(SOCIAL_TABLE)
    item = {
        "user_id": to_id,
        "sk": f"request#{from_id}",
        "from_user_id": from_id,
        "status": "pending",
        "created_at": __import__("lambdas.common.utility_helpers", fromlist=["now_iso"]).now_iso(),
    }
    table.put_item(Item=item)
    return item


def accept_friend(user_id: str, friend_id: str):
    table = dynamodb.Table(SOCIAL_TABLE)
    now = __import__("lambdas.common.utility_helpers", fromlist=["now_iso"]).now_iso()
    # Add bidirectional friendship
    table.put_item(Item={"user_id": user_id, "sk": f"friend#{friend_id}", "friend_id": friend_id, "since": now})
    table.put_item(Item={"user_id": friend_id, "sk": f"friend#{user_id}", "friend_id": user_id, "since": now})
    # Remove the request
    table.delete_item(Key={"user_id": user_id, "sk": f"request#{friend_id}"})


def get_pending_requests(user_id: str) -> list:
    table = dynamodb.Table(SOCIAL_TABLE)
    resp = table.query(
        KeyConditionExpression=Key("user_id").eq(user_id) & Key("sk").begins_with("request#"),
    )
    return resp.get("Items", [])


# ============================================
# Feed
# ============================================

def post_to_feed(user_id: str, workout_id: str, workout_summary: dict) -> dict:
    table = dynamodb.Table(FEED_TABLE)
    now = __import__("lambdas.common.utility_helpers", fromlist=["now_iso"]).now_iso()
    item = {
        "user_id": user_id,
        "sk": f"post#{now}#{workout_id}",
        "workout_id": workout_id,
        "summary": workout_summary,
        "likes": 0,
        "comments": [],
        "created_at": now,
    }
    table.put_item(Item=item)
    return item


def get_feed(user_id: str, limit: int = 20) -> list:
    """Get feed items from user's friends."""
    friends = get_friends(user_id)
    friend_ids = [f["friend_id"] for f in friends] + [user_id]

    table = dynamodb.Table(FEED_TABLE)
    all_posts = []
    for fid in friend_ids:
        resp = table.query(
            KeyConditionExpression=Key("user_id").eq(fid),
            ScanIndexForward=False,
            Limit=5
        )
        all_posts.extend(resp.get("Items", []))

    # Sort by created_at descending
    all_posts.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return all_posts[:limit]
