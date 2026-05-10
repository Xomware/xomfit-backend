"""
XOMFIT APNs Client
==================
Sends a push to Apple's APNs HTTP/2 endpoint using token-based auth (ES256
JWT signed with an APNs auth key).

Required env vars (typically populated from SSM at deploy time):
    APNS_KEY_ID            — 10-char Key ID
    APNS_TEAM_ID           — 10-char Team ID
    APNS_BUNDLE_ID         — iOS app bundle id (e.g. com.xomware.xomfit)
    APNS_AUTH_KEY          — full PEM of the .p8 file (BEGIN/END PRIVATE KEY)
    APNS_HOST              — optional; defaults to api.push.apple.com
                             (use api.sandbox.push.apple.com for dev builds)

If any of these are missing the push is logged and skipped — the cron must
not fail because APNs isn't provisioned yet.
"""

import json
import os
import time
from typing import Optional

from lambdas.common.logger import get_logger

log = get_logger(__file__)

APNS_KEY_ID = os.environ.get("APNS_KEY_ID")
APNS_TEAM_ID = os.environ.get("APNS_TEAM_ID")
APNS_BUNDLE_ID = os.environ.get("APNS_BUNDLE_ID")
APNS_AUTH_KEY = os.environ.get("APNS_AUTH_KEY")
APNS_HOST = os.environ.get("APNS_HOST", "api.push.apple.com")


def _is_configured() -> bool:
    return all([APNS_KEY_ID, APNS_TEAM_ID, APNS_BUNDLE_ID, APNS_AUTH_KEY])


# Cache the JWT for ~50 minutes (Apple recommends < 60 min, > 20 min between rotations).
_token_cache: dict = {"token": None, "issued_at": 0}


def _build_jwt() -> Optional[str]:
    """Build the ES256 JWT used as the bearer token for APNs."""
    now = int(time.time())
    if _token_cache["token"] and now - _token_cache["issued_at"] < 50 * 60:
        return _token_cache["token"]

    try:
        import jwt  # PyJWT is already in requirements.txt
    except ImportError:
        log.error("PyJWT not installed — cannot build APNs token")
        return None

    try:
        token = jwt.encode(
            {"iss": APNS_TEAM_ID, "iat": now},
            APNS_AUTH_KEY,
            algorithm="ES256",
            headers={"kid": APNS_KEY_ID, "alg": "ES256"},
        )
    except Exception as e:  # cryptography errors, malformed key, etc.
        log.error(f"Failed to sign APNs JWT: {e}")
        return None

    _token_cache["token"] = token
    _token_cache["issued_at"] = now
    return token


def send_report_notification(
    device_token: str,
    title: str,
    body: str,
    report_id: str,
    *,
    sound: str = "default",
) -> bool:
    """Send an APNs alert to a single device. Returns True on success.

    Never raises — caller (cron) treats False as "skip" and continues.
    """
    if not device_token:
        log.info("send_report_notification: no device_token; skipping")
        return False

    if not _is_configured():
        log.warning("APNs not configured; skipping push notification")
        return False

    token = _build_jwt()
    if not token:
        return False

    payload = {
        "aps": {
            "alert": {"title": title, "body": body},
            "sound": sound,
            "badge": 1,
            "category": "REPORT_READY",
        },
        "report_id": report_id,
        "type": "report",
    }

    # HTTP/2 client — httpx if available, otherwise hyper / fall back & log skip.
    try:
        import httpx  # type: ignore
    except ImportError:
        log.error("httpx not installed; cannot send APNs over HTTP/2")
        return False

    url = f"https://{APNS_HOST}/3/device/{device_token}"
    headers = {
        "authorization": f"bearer {token}",
        "apns-topic": APNS_BUNDLE_ID,
        "apns-push-type": "alert",
        "apns-priority": "10",
    }

    try:
        with httpx.Client(http2=True, timeout=10.0) as client:
            resp = client.post(url, headers=headers, content=json.dumps(payload))
        if resp.status_code == 200:
            log.info(f"APNs push delivered for report {report_id}")
            return True
        log.error(
            f"APNs push failed: status={resp.status_code} body={resp.text[:300]}"
        )
        return False
    except Exception as e:
        log.error(f"APNs request failed: {e}")
        return False
