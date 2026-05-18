"""Unit tests for the AI coach proxy handler.

Mocks out boto3 DynamoDB + requests so the handler can run without AWS or
network access.

Run:
    python -m unittest tests.test_ai_coach_proxy
"""

import json
import os
import unittest
from unittest.mock import patch, MagicMock


def _event(body: dict, user_id: str = "u-test-1") -> dict:
    return {
        "body": json.dumps(body),
        "requestContext": {"authorizer": {"user_id": user_id}},
    }


def _ok_anthropic_response(text: str = "hi", input_tokens: int = 10, output_tokens: int = 5) -> dict:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-4-5",
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        "stop_reason": "end_turn",
    }


class ProxyHappyPath(unittest.TestCase):
    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=False)
    @patch("lambdas.ai_coach_proxy.handler.put_ai_coach_cost")
    @patch("lambdas.ai_coach_proxy.handler.increment_ai_coach_daily_count", return_value=1)
    @patch("lambdas.ai_coach_proxy.handler.get_ai_coach_daily_count", return_value=0)
    @patch("lambdas.ai_coach_proxy.handler.requests.post")
    def test_forwards_and_logs_cost(
        self,
        mock_post,
        mock_count,
        mock_inc,
        mock_cost,
    ):
        from lambdas.ai_coach_proxy.handler import handler

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _ok_anthropic_response(
            text="Let's lift", input_tokens=42, output_tokens=18
        )
        mock_post.return_value = mock_resp

        event = _event({
            "model": "claude-haiku-4-5",
            "messages": [{"role": "user", "content": "give me a workout"}],
            "max_tokens": 512,
        })

        result = handler(event, None)

        self.assertEqual(result["statusCode"], 200)
        body = json.loads(result["body"])
        self.assertEqual(body["content"][0]["text"], "Let's lift")

        # Forwarded with stream=False, even if client sent stream=true.
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        sent = json.loads(kwargs["data"])
        self.assertFalse(sent["stream"])
        self.assertEqual(sent["model"], "claude-haiku-4-5")
        self.assertEqual(sent["max_tokens"], 512)

        # Auth header carries the server-side key, NOT echoing anything client-side.
        headers = kwargs["headers"]
        self.assertEqual(headers["x-api-key"], "test-key")
        self.assertEqual(headers["anthropic-version"], "2023-06-01")

        # Counter incremented + cost logged exactly once.
        mock_inc.assert_called_once()
        mock_cost.assert_called_once()
        _, cost_kwargs = mock_cost.call_args
        self.assertEqual(cost_kwargs["input_tokens"], 42)
        self.assertEqual(cost_kwargs["output_tokens"], 18)
        self.assertEqual(cost_kwargs["model"], "claude-haiku-4-5")
        self.assertEqual(cost_kwargs["user_id"], "u-test-1")

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=False)
    @patch("lambdas.ai_coach_proxy.handler.put_ai_coach_cost")
    @patch("lambdas.ai_coach_proxy.handler.increment_ai_coach_daily_count", return_value=1)
    @patch("lambdas.ai_coach_proxy.handler.get_ai_coach_daily_count", return_value=0)
    @patch("lambdas.ai_coach_proxy.handler.requests.post")
    def test_passes_through_system_prompt_and_tools(
        self, mock_post, _gc, _inc, _cost,
    ):
        from lambdas.ai_coach_proxy.handler import handler

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _ok_anthropic_response()
        mock_post.return_value = mock_resp

        event = _event({
            "model": "claude-haiku-4-5",
            "system": "You are a coach.",
            "messages": [{"role": "user", "content": "hi"}],
            "tools": [{"name": "build_workout", "description": "x", "input_schema": {}}],
            "max_tokens": 100,
        })

        result = handler(event, None)
        self.assertEqual(result["statusCode"], 200)
        _, kwargs = mock_post.call_args
        sent = json.loads(kwargs["data"])
        self.assertEqual(sent["system"], "You are a coach.")
        self.assertEqual(len(sent["tools"]), 1)


class ProxyRateLimit(unittest.TestCase):
    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=False)
    @patch("lambdas.ai_coach_proxy.handler.put_ai_coach_cost")
    @patch("lambdas.ai_coach_proxy.handler.increment_ai_coach_daily_count")
    @patch("lambdas.ai_coach_proxy.handler.get_ai_coach_daily_count", return_value=50)
    @patch("lambdas.ai_coach_proxy.handler.requests.post")
    def test_returns_429_when_limit_hit(
        self, mock_post, _gc, mock_inc, mock_cost,
    ):
        from lambdas.ai_coach_proxy.handler import handler

        event = _event({
            "model": "claude-haiku-4-5",
            "messages": [{"role": "user", "content": "hi"}],
        })

        result = handler(event, None)

        self.assertEqual(result["statusCode"], 429)
        body = json.loads(result["body"])
        self.assertIn("error", body)
        self.assertIn("Daily message limit", body["error"])

        # No upstream call, no increment, no cost log.
        mock_post.assert_not_called()
        mock_inc.assert_not_called()
        mock_cost.assert_not_called()


class ProxyValidation(unittest.TestCase):
    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=False)
    @patch("lambdas.ai_coach_proxy.handler.get_ai_coach_daily_count", return_value=0)
    def test_missing_messages_is_400(self, _gc):
        from lambdas.ai_coach_proxy.handler import handler

        event = _event({"model": "claude-haiku-4-5"})
        result = handler(event, None)
        self.assertEqual(result["statusCode"], 400)
        body = json.loads(result["body"])
        self.assertIn("messages", body["error"]["message"])

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=False)
    @patch("lambdas.ai_coach_proxy.handler.get_ai_coach_daily_count", return_value=0)
    def test_disallowed_model_is_400(self, _gc):
        from lambdas.ai_coach_proxy.handler import handler

        event = _event({
            "model": "claude-opus-4-1",  # not in default allow-list
            "messages": [{"role": "user", "content": "hi"}],
        })
        result = handler(event, None)
        self.assertEqual(result["statusCode"], 400)

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_server_key_is_503(self):
        from lambdas.ai_coach_proxy.handler import handler

        event = _event({
            "model": "claude-haiku-4-5",
            "messages": [{"role": "user", "content": "hi"}],
        })
        result = handler(event, None)
        self.assertEqual(result["statusCode"], 503)


class ProxyUpstreamErrors(unittest.TestCase):
    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=False)
    @patch("lambdas.ai_coach_proxy.handler.put_ai_coach_cost")
    @patch("lambdas.ai_coach_proxy.handler.increment_ai_coach_daily_count")
    @patch("lambdas.ai_coach_proxy.handler.get_ai_coach_daily_count", return_value=0)
    @patch("lambdas.ai_coach_proxy.handler.requests.post")
    def test_upstream_4xx_is_passed_through_without_charge(
        self, mock_post, _gc, mock_inc, mock_cost,
    ):
        from lambdas.ai_coach_proxy.handler import handler

        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {
            "type": "error",
            "error": {"type": "invalid_request_error", "message": "nope"},
        }
        mock_post.return_value = mock_resp

        event = _event({
            "model": "claude-haiku-4-5",
            "messages": [{"role": "user", "content": "hi"}],
        })
        result = handler(event, None)
        self.assertEqual(result["statusCode"], 400)
        # Counter + cost untouched on upstream error.
        mock_inc.assert_not_called()
        mock_cost.assert_not_called()

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=False)
    @patch("lambdas.ai_coach_proxy.handler.get_ai_coach_daily_count", return_value=0)
    @patch("lambdas.ai_coach_proxy.handler.requests.post")
    def test_transport_error_is_502(self, mock_post, _gc):
        import requests as _requests
        from lambdas.ai_coach_proxy.handler import handler

        mock_post.side_effect = _requests.ConnectionError("boom")

        event = _event({
            "model": "claude-haiku-4-5",
            "messages": [{"role": "user", "content": "hi"}],
        })
        result = handler(event, None)
        self.assertEqual(result["statusCode"], 502)


if __name__ == "__main__":
    unittest.main()
