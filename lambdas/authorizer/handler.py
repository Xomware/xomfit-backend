"""
API Gateway Lambda Authorizer
Validates JWT tokens from auth provider
"""
import os
import json
import jwt
from lambdas.common.logger import get_logger

log = get_logger(__file__)

SECRET_KEY = os.environ.get("JWT_SECRET", "xomfit-dev-secret")
ISSUER = os.environ.get("JWT_ISSUER", "xomfit")


def handler(event, context):
    token = event.get("authorizationToken", "").replace("Bearer ", "")

    if not token:
        log.warning("No token provided")
        raise Exception("Unauthorized")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"], issuer=ISSUER)
        user_id = payload.get("sub") or payload.get("user_id")

        if not user_id:
            raise Exception("Invalid token: no user_id")

        log.info(f"Authorized user: {user_id}")

        return {
            "principalId": user_id,
            "policyDocument": {
                "Version": "2012-10-17",
                "Statement": [{
                    "Action": "execute-api:Invoke",
                    "Effect": "Allow",
                    "Resource": event["methodArn"]
                }]
            },
            "context": {
                "user_id": user_id,
                "username": payload.get("username", ""),
            }
        }
    except jwt.ExpiredSignatureError:
        log.warning("Token expired")
        raise Exception("Unauthorized")
    except jwt.InvalidTokenError as e:
        log.warning(f"Invalid token: {e}")
        raise Exception("Unauthorized")
