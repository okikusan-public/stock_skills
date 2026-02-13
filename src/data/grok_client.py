"""Grok API (xAI) wrapper for X Search and sentiment analysis (KIK-359).

Uses the xAI Responses API to search X (Twitter) posts and analyze
market sentiment for individual stocks.

API key is read from the XAI_API_KEY environment variable.
When the key is not set, is_available() returns False and
search_x_sentiment() returns an empty result (graceful degradation).
"""

import json
import os
from typing import Optional

import requests


_API_URL = "https://api.x.ai/v1/responses"
_DEFAULT_MODEL = "grok-3-mini"


def is_available() -> bool:
    """Check if Grok API is available (XAI_API_KEY is set)."""
    return bool(os.environ.get("XAI_API_KEY"))


def _get_api_key() -> Optional[str]:
    """Return the API key or None."""
    return os.environ.get("XAI_API_KEY")


def _build_sentiment_prompt(symbol: str, company_name: str = "") -> str:
    """Build the prompt for sentiment analysis."""
    name_part = f" ({company_name})" if company_name else ""
    return (
        f"Search X for recent posts about {symbol}{name_part} stock. "
        f"Analyze the sentiment of the posts and provide:\n"
        f"1. A list of positive factors (bullish signals) mentioned\n"
        f"2. A list of negative factors (bearish signals) mentioned\n"
        f"3. An overall sentiment score from -1.0 (very bearish) to 1.0 (very bullish)\n\n"
        f"Respond in JSON format:\n"
        f'{{"positive": ["factor1", "factor2"], '
        f'"negative": ["factor1", "factor2"], '
        f'"sentiment_score": 0.0}}'
    )


def search_x_sentiment(
    symbol: str,
    company_name: str = "",
    timeout: int = 30,
) -> dict:
    """Search X for stock sentiment using Grok API.

    Parameters
    ----------
    symbol : str
        Stock ticker symbol (e.g. "AAPL", "7203.T").
    company_name : str
        Company name for better search context.
    timeout : int
        Request timeout in seconds.

    Returns
    -------
    dict
        Keys: positive (list[str]), negative (list[str]),
              sentiment_score (float, -1 to 1),
              raw_response (str).
        Returns empty result on error or when API is unavailable.
    """
    empty_result = {
        "positive": [],
        "negative": [],
        "sentiment_score": 0.0,
        "raw_response": "",
    }

    api_key = _get_api_key()
    if not api_key:
        return empty_result

    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": _DEFAULT_MODEL,
            "tools": [{"type": "x_search"}],
            "input": _build_sentiment_prompt(symbol, company_name),
        }

        response = requests.post(
            _API_URL,
            headers=headers,
            json=payload,
            timeout=timeout,
        )

        if response.status_code != 200:
            print(
                f"[grok_client] API error for {symbol}: "
                f"status={response.status_code}"
            )
            return empty_result

        data = response.json()

        # Extract text content from the response
        raw_text = ""
        output_items = data.get("output", [])
        for item in output_items:
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        raw_text = content.get("text", "")
                        break

        if not raw_text:
            return empty_result

        # Try to parse JSON from the response
        result = dict(empty_result)
        result["raw_response"] = raw_text

        try:
            # Find JSON block in the response
            json_start = raw_text.find("{")
            json_end = raw_text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                parsed = json.loads(raw_text[json_start:json_end])
                if isinstance(parsed.get("positive"), list):
                    result["positive"] = parsed["positive"]
                if isinstance(parsed.get("negative"), list):
                    result["negative"] = parsed["negative"]
                score = parsed.get("sentiment_score")
                if isinstance(score, (int, float)):
                    result["sentiment_score"] = max(-1.0, min(1.0, float(score)))
        except (json.JSONDecodeError, ValueError):
            pass  # Keep raw_response, return empty structured data

        return result

    except requests.exceptions.Timeout:
        print(f"[grok_client] Timeout for {symbol}")
        return empty_result
    except requests.exceptions.RequestException as e:
        print(f"[grok_client] Request error for {symbol}: {e}")
        return empty_result
    except Exception as e:
        print(f"[grok_client] Unexpected error for {symbol}: {e}")
        return empty_result
