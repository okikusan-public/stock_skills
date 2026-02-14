"""Tests for grok_client trending stock search (KIK-370)."""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.data.grok_client import (
    _build_trending_prompt,
    search_trending_stocks,
    EMPTY_TRENDING,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_grok_response(text: str) -> MagicMock:
    """Build a mock HTTP response that returns *text* as API output."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": text}
                ],
            }
        ]
    }
    return mock_response


@pytest.fixture(autouse=True)
def _reset_error_warned():
    from src.data import grok_client
    grok_client._error_warned[0] = False
    yield


# ===================================================================
# _build_trending_prompt
# ===================================================================

class TestBuildTrendingPrompt:
    def test_japan_default(self):
        prompt = _build_trending_prompt("japan")
        assert "日本株" in prompt
        assert ".T" in prompt
        assert "JSON" in prompt

    def test_japan_jp_alias(self):
        prompt = _build_trending_prompt("jp")
        assert "日本株" in prompt

    def test_us_region(self):
        prompt = _build_trending_prompt("us")
        assert "米国株" in prompt or "US stock" in prompt
        assert "AAPL" in prompt or "MSFT" in prompt

    def test_asean_region(self):
        prompt = _build_trending_prompt("asean")
        assert "ASEAN" in prompt

    def test_with_theme(self):
        prompt = _build_trending_prompt("japan", theme="AI")
        assert "AI" in prompt

    def test_without_theme(self):
        prompt = _build_trending_prompt("japan", theme=None)
        assert "Focus specifically" not in prompt

    def test_unknown_region_falls_back_to_japan(self):
        prompt = _build_trending_prompt("unknown")
        assert "日本株" in prompt

    def test_hk_region(self):
        prompt = _build_trending_prompt("hk")
        assert ".HK" in prompt

    def test_kr_region(self):
        prompt = _build_trending_prompt("kr")
        assert ".KS" in prompt


# ===================================================================
# search_trending_stocks
# ===================================================================

class TestSearchTrendingStocks:
    def test_no_api_key(self, monkeypatch):
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        result = search_trending_stocks("japan")
        assert result["stocks"] == []
        assert result["market_context"] == ""
        assert result["raw_response"] == ""

    @patch("src.data.grok_client.requests.post")
    def test_successful_response(self, mock_post, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        payload = {
            "stocks": [
                {"ticker": "7203.T", "name": "Toyota", "reason": "EV investment"},
                {"ticker": "6758.T", "name": "Sony", "reason": "PS6 hype"},
            ],
            "market_context": "Bullish on Japanese tech",
        }
        mock_post.return_value = _make_grok_response(json.dumps(payload))

        result = search_trending_stocks("japan")
        assert len(result["stocks"]) == 2
        assert result["stocks"][0]["ticker"] == "7203.T"
        assert result["stocks"][0]["name"] == "Toyota"
        assert result["stocks"][0]["reason"] == "EV investment"
        assert result["market_context"] == "Bullish on Japanese tech"

    @patch("src.data.grok_client.requests.post")
    def test_malformed_stocks_filtered(self, mock_post, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        payload = {
            "stocks": [
                {"ticker": "7203.T", "name": "Toyota", "reason": "OK"},
                {"name": "No Ticker Corp", "reason": "missing"},
                {"ticker": 123, "name": "Bad type"},
            ],
            "market_context": "",
        }
        mock_post.return_value = _make_grok_response(json.dumps(payload))

        result = search_trending_stocks("japan")
        assert len(result["stocks"]) == 1
        assert result["stocks"][0]["ticker"] == "7203.T"

    @patch("src.data.grok_client.requests.post")
    def test_theme_in_prompt(self, mock_post, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.return_value = _make_grok_response('{"stocks": [], "market_context": ""}')

        search_trending_stocks("us", theme="AI")

        call_args = mock_post.call_args
        prompt = call_args[1]["json"]["input"]
        assert "AI" in prompt

    @patch("src.data.grok_client.requests.post")
    def test_api_error_returns_empty(self, mock_post, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_post.return_value = mock_resp

        result = search_trending_stocks("japan")
        assert result["stocks"] == []

    @patch("src.data.grok_client.requests.post")
    def test_non_json_response(self, mock_post, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.return_value = _make_grok_response("Not JSON at all")

        result = search_trending_stocks("japan")
        assert result["stocks"] == []
        assert result["raw_response"] == "Not JSON at all"

    @patch("src.data.grok_client.requests.post")
    def test_empty_stocks_list(self, mock_post, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.return_value = _make_grok_response(
            '{"stocks": [], "market_context": "No trends"}'
        )

        result = search_trending_stocks("japan")
        assert result["stocks"] == []
        assert result["market_context"] == "No trends"

    @patch("src.data.grok_client.requests.post")
    def test_ticker_whitespace_stripped(self, mock_post, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        payload = {
            "stocks": [{"ticker": " 7203.T ", "name": "Toyota", "reason": "test"}],
            "market_context": "",
        }
        mock_post.return_value = _make_grok_response(json.dumps(payload))

        result = search_trending_stocks("japan")
        assert result["stocks"][0]["ticker"] == "7203.T"

    @patch("src.data.grok_client.requests.post")
    def test_non_string_name_reason(self, mock_post, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        payload = {
            "stocks": [{"ticker": "AAPL", "name": 123, "reason": None}],
            "market_context": "",
        }
        mock_post.return_value = _make_grok_response(json.dumps(payload))

        result = search_trending_stocks("us")
        assert result["stocks"][0]["name"] == ""
        assert result["stocks"][0]["reason"] == ""
