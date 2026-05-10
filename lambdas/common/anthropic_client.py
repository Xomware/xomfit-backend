"""
XOMFIT Anthropic Client
=======================
Thin wrapper that asks Claude for an ~80 word focus recommendation given a
user's profile + last period stats. Falls back to a static line when the
ANTHROPIC_API_KEY is missing — never raises.
"""

import json
import os
from typing import Optional

import requests  # already in requirements.txt

from lambdas.common.logger import get_logger

log = get_logger(__file__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

FALLBACK_TEXT = (
    "Keep your routine consistent this week — aim for the same number of sessions "
    "as last period and prioritize progressive overload on your top lifts. "
    "Focus on quality reps, sleep, and recovery. Small wins compound."
)


def _build_prompt(kind: str, profile: dict, stats: dict, prior_feedback: Optional[list] = None) -> str:
    """Build the user message. Keeps the prompt deterministic and short."""
    profile_summary = {
        "display_name": profile.get("display_name"),
        "experience": profile.get("experience"),
        "goals": profile.get("goals"),
    }
    feedback_block = ""
    if prior_feedback:
        recent = prior_feedback[:3]
        feedback_block = (
            "\n\nRecent feedback this user gave on prior recommendations "
            f"(rating -1=bad, 0=neutral, 1=good):\n{json.dumps(recent)}"
        )

    return (
        f"You are XomFit's coaching assistant. Write a single paragraph of about "
        f"80 words telling this lifter what to focus on for the upcoming "
        f"{'week' if kind == 'weekly' else 'month'} based on the period stats below. "
        f"Be specific, motivating, and grounded in the data. No greetings, no sign-off, "
        f"no markdown — plain prose only.\n\n"
        f"Profile:\n{json.dumps(profile_summary)}\n\n"
        f"Last period stats:\n{json.dumps(stats)}"
        f"{feedback_block}"
    )


def generate_recommendation(
    kind: str,
    profile: dict,
    stats: dict,
    prior_feedback: Optional[list] = None,
    timeout_seconds: int = 20,
) -> str:
    """Return an ~80 word recommendation. Never raises — falls back on errors."""
    if not ANTHROPIC_API_KEY:
        log.warning("ANTHROPIC_API_KEY not set; using fallback recommendation text")
        return FALLBACK_TEXT

    prompt = _build_prompt(kind, profile, stats, prior_feedback)
    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 300,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    try:
        resp = requests.post(
            ANTHROPIC_API_URL,
            headers=headers,
            data=json.dumps(payload),
            timeout=timeout_seconds,
        )
        if resp.status_code != 200:
            log.error(
                f"Anthropic API non-200: {resp.status_code} body={resp.text[:300]}"
            )
            return FALLBACK_TEXT
        data = resp.json()
        # Response shape: {"content": [{"type": "text", "text": "..."}], ...}
        for block in data.get("content", []):
            if block.get("type") == "text":
                text = (block.get("text") or "").strip()
                if text:
                    return text
        log.error("Anthropic response had no text content")
        return FALLBACK_TEXT
    except requests.RequestException as e:
        log.error(f"Anthropic request failed: {e}")
        return FALLBACK_TEXT
    except (ValueError, KeyError) as e:
        log.error(f"Anthropic response parse failed: {e}")
        return FALLBACK_TEXT
