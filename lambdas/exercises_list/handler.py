"""
GET /exercises/list - Get exercise library
"""
import json
import os
from lambdas.common.logger import get_logger
from lambdas.common.errors import handle_errors
from lambdas.common.utility_helpers import get_query_params, success_response

log = get_logger(__file__)
HANDLER = "exercises_list"

# Load exercise database from bundled JSON
EXERCISES_FILE = os.path.join(os.path.dirname(__file__), "exercises.json")


def load_exercises():
    try:
        with open(EXERCISES_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return []


@handle_errors(HANDLER)
def handler(event, context):
    params = get_query_params(event)
    exercises = load_exercises()

    # Filter by muscle group
    muscle = params.get("muscle_group")
    if muscle:
        exercises = [e for e in exercises if muscle in e.get("muscle_groups", [])]

    # Filter by equipment
    equipment = params.get("equipment")
    if equipment:
        exercises = [e for e in exercises if e.get("equipment") == equipment]

    # Search by name
    query = params.get("q", "").lower()
    if query:
        exercises = [e for e in exercises if query in e["name"].lower()]

    return success_response(exercises)
