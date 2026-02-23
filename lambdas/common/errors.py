"""
XOMFIT Error Classes
====================
Standardized error handling for all Lambda functions.
"""

import json
import traceback
from typing import Optional
from lambdas.common.logger import get_logger

log = get_logger(__file__)


class XomFitError(Exception):
    def __init__(self, message: str, handler: str = "unknown", function: str = "unknown",
                 status: int = 500, details: Optional[dict] = None):
        self.message = message
        self.handler = handler
        self.function = function
        self.status = status
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict:
        return {
            "error": {
                "message": self.message,
                "handler": self.handler,
                "function": self.function,
                "status": self.status,
                **self.details
            }
        }

    def to_response(self, is_api: bool = True) -> dict:
        body = self.to_dict()
        return {
            "statusCode": self.status,
            "headers": {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"},
            "body": json.dumps(body) if is_api else body,
            "isBase64Encoded": False
        }

    def log_error(self):
        log.error(f"💥 {self.__class__.__name__} in {self.handler}.{self.function}: {self.message}")
        if self.details:
            log.error(f"   Details: {self.details}")


class NotFoundError(XomFitError):
    def __init__(self, message: str = "Resource not found", **kwargs):
        super().__init__(message, status=404, **kwargs)


class ValidationError(XomFitError):
    def __init__(self, message: str = "Invalid request", **kwargs):
        super().__init__(message, status=400, **kwargs)


class UnauthorizedError(XomFitError):
    def __init__(self, message: str = "Unauthorized", **kwargs):
        super().__init__(message, status=401, **kwargs)


class ConflictError(XomFitError):
    def __init__(self, message: str = "Resource already exists", **kwargs):
        super().__init__(message, status=409, **kwargs)


def handle_errors(handler_name: str):
    """Decorator for consistent error handling across all handlers."""
    def decorator(func):
        def wrapper(event, context):
            try:
                return func(event, context)
            except XomFitError as e:
                e.handler = handler_name
                e.log_error()
                return e.to_response()
            except Exception as e:
                log.error(f"💥 Unhandled error in {handler_name}: {str(e)}")
                log.error(traceback.format_exc())
                return XomFitError(
                    message="Internal server error",
                    handler=handler_name,
                    status=500
                ).to_response()
        return wrapper
    return decorator
