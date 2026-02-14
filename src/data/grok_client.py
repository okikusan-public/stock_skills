"""Grok API (xAI) wrapper for X Search and sentiment analysis (KIK-359).

Uses the xAI Responses API to search X (Twitter) posts and analyze
market sentiment for individual stocks, industries, and markets.

API key is read from the XAI_API_KEY environment variable.
When the key is not set, is_available() returns False and
all search functions return empty results (graceful degradation).
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


_API_URL = "https://api.x.ai/v1/responses"
_DEFAULT_MODEL = "grok-4-1-fast-non-reasoning"
_error_warned = [False]

# ---------------------------------------------------------------------------
# Empty result constants
# ---------------------------------------------------------------------------

EMPTY_STOCK_DEEP = {
    "recent_news": [],
    "catalysts": {"positive": [], "negative": []},
    "analyst_views": [],
    "x_sentiment": {"score": 0.0, "summary": "", "key_opinions": []},
    "competitive_notes": [],
    "raw_response": "",
}

EMPTY_INDUSTRY = {
    "trends": [],
    "key_players": [],
    "growth_drivers": [],
    "risks": [],
    "regulatory": [],
    "investor_focus": [],
    "raw_response": "",
}

EMPTY_MARKET = {
    "price_action": "",
    "macro_factors": [],
    "sentiment": {"score": 0.0, "summary": ""},
    "upcoming_events": [],
    "sector_rotation": [],
    "raw_response": "",
}

EMPTY_TRENDING = {
    "stocks": [],
    "market_context": "",
    "raw_response": "",
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def is_available() -> bool:
    """Check if Grok API is available (XAI_API_KEY is set)."""
    return bool(os.environ.get("XAI_API_KEY"))


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_api_key() -> Optional[str]:
    """Return the API key or None."""
    return os.environ.get("XAI_API_KEY")


def _is_japanese_stock(symbol: str) -> bool:
    """Return True if *symbol* looks like a JPX ticker (.T or .S suffix)."""
    return symbol.upper().endswith((".T", ".S"))


def _contains_japanese(text: str) -> bool:
    """Return True if *text* contains Japanese characters."""
    return any(0x3000 <= ord(c) <= 0x9FFF for c in text)


def _call_grok_api(prompt: str, timeout: int = 30) -> str:
    """Common request helper for the Grok API.

    Parameters
    ----------
    prompt : str
        Prompt to send to the API.
    timeout : int
        Request timeout in seconds.

    Returns
    -------
    str
        Text portion of the API response.  Empty string on error.
    """
    api_key = _get_api_key()
    if not api_key:
        return ""

    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": _DEFAULT_MODEL,
            "tools": [{"type": "x_search"}, {"type": "web_search"}],
            "input": prompt,
        }

        response = requests.post(
            _API_URL,
            headers=headers,
            json=payload,
            timeout=timeout,
        )

        if response.status_code != 200:
            if not _error_warned[0]:
                print(
                    f"[grok_client] API error: "
                    f"status={response.status_code} (subsequent errors suppressed)",
                    file=sys.stderr,
                )
                _error_warned[0] = True
            return ""

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

        return raw_text

    except requests.exceptions.Timeout:
        if not _error_warned[0]:
            print("[grok_client] Timeout (subsequent errors suppressed)", file=sys.stderr)
            _error_warned[0] = True
        return ""
    except requests.exceptions.RequestException as e:
        if not _error_warned[0]:
            print(f"[grok_client] Request error: {e} (subsequent errors suppressed)", file=sys.stderr)
            _error_warned[0] = True
        return ""
    except Exception as e:
        if not _error_warned[0]:
            print(f"[grok_client] Unexpected error: {e} (subsequent errors suppressed)", file=sys.stderr)
            _error_warned[0] = True
        return ""


def _parse_json_response(raw_text: str) -> dict:
    """Extract a JSON object from *raw_text*.

    Finds the first ``{`` and last ``}`` and attempts ``json.loads``.
    Returns an empty dict on failure.
    """
    try:
        json_start = raw_text.find("{")
        json_end = raw_text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            return json.loads(raw_text[json_start:json_end])
    except (json.JSONDecodeError, ValueError):
        pass
    return {}


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

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


def _build_stock_deep_prompt(symbol: str, company_name: str = "") -> str:
    """Build the prompt for deep stock research."""
    name_part = f" ({company_name})" if company_name else ""
    if _is_japanese_stock(symbol):
        return (
            f"{symbol}{name_part} について、X（Twitter）とWebの最新情報をもとに以下を調査してください。\n\n"
            f"1. 最近の重要ニュース（直近1-2週間）\n"
            f"2. 業績に影響する材料（ポジティブ/ネガティブ）\n"
            f"3. 機関投資家・アナリストの見方\n"
            f"4. X上の投資家センチメント\n"
            f"5. 競合他社との比較での注目点\n\n"
            f"JSON形式で回答:\n"
            f'{{\n'
            f'  "recent_news": ["ニュース1", "ニュース2"],\n'
            f'  "catalysts": {{\n'
            f'    "positive": ["材料1", "材料2"],\n'
            f'    "negative": ["材料1", "材料2"]\n'
            f'  }},\n'
            f'  "analyst_views": ["見解1", "見解2"],\n'
            f'  "x_sentiment": {{\n'
            f'    "score": 0.0,\n'
            f'    "summary": "概要テキスト",\n'
            f'    "key_opinions": ["意見1", "意見2"]\n'
            f'  }},\n'
            f'  "competitive_notes": ["注目点1", "注目点2"]\n'
            f'}}'
        )
    return (
        f"Research {symbol}{name_part} using X (Twitter) and web sources. Provide:\n\n"
        f"1. Key recent news (last 1-2 weeks)\n"
        f"2. Catalysts affecting earnings (positive/negative)\n"
        f"3. Institutional/analyst perspectives\n"
        f"4. X investor sentiment\n"
        f"5. Notable competitive dynamics\n\n"
        f"Respond in JSON:\n"
        f'{{\n'
        f'  "recent_news": ["news1", "news2"],\n'
        f'  "catalysts": {{\n'
        f'    "positive": ["catalyst1", "catalyst2"],\n'
        f'    "negative": ["catalyst1", "catalyst2"]\n'
        f'  }},\n'
        f'  "analyst_views": ["view1", "view2"],\n'
        f'  "x_sentiment": {{\n'
        f'    "score": 0.0,\n'
        f'    "summary": "summary text",\n'
        f'    "key_opinions": ["opinion1", "opinion2"]\n'
        f'  }},\n'
        f'  "competitive_notes": ["note1", "note2"]\n'
        f'}}'
    )


def _build_industry_prompt(industry_or_theme: str) -> str:
    """Build the prompt for industry research."""
    if _contains_japanese(industry_or_theme):
        return (
            f"「{industry_or_theme}」業界・テーマについて、X（Twitter）とWebの最新情報をもとに以下を調査してください。\n\n"
            f"1. 業界の現状と最近のトレンド\n"
            f"2. 主要プレイヤーと注目企業\n"
            f"3. 成長ドライバーとリスク要因\n"
            f"4. 規制・政策の動向\n"
            f"5. 投資家の注目ポイント\n\n"
            f"JSON形式で回答:\n"
            f'{{\n'
            f'  "trends": ["トレンド1", "トレンド2"],\n'
            f'  "key_players": [\n'
            f'    {{"name": "企業名", "ticker": "シンボル", "note": "注目理由"}}\n'
            f'  ],\n'
            f'  "growth_drivers": ["ドライバー1", "ドライバー2"],\n'
            f'  "risks": ["リスク1", "リスク2"],\n'
            f'  "regulatory": ["規制動向1", "規制動向2"],\n'
            f'  "investor_focus": ["注目点1", "注目点2"]\n'
            f'}}'
        )
    return (
        f"Research the \"{industry_or_theme}\" industry/theme using X (Twitter) and web sources. Provide:\n\n"
        f"1. Current trends\n"
        f"2. Key players and notable companies\n"
        f"3. Growth drivers and risk factors\n"
        f"4. Regulatory/policy developments\n"
        f"5. Investor focus points\n\n"
        f"Respond in JSON:\n"
        f'{{\n'
        f'  "trends": ["trend1", "trend2"],\n'
        f'  "key_players": [\n'
        f'    {{"name": "company", "ticker": "SYMBOL", "note": "reason"}}\n'
        f'  ],\n'
        f'  "growth_drivers": ["driver1", "driver2"],\n'
        f'  "risks": ["risk1", "risk2"],\n'
        f'  "regulatory": ["development1", "development2"],\n'
        f'  "investor_focus": ["point1", "point2"]\n'
        f'}}'
    )


def _build_trending_prompt(region: str = "japan", theme: Optional[str] = None) -> str:
    """Build the prompt for discovering trending stocks on X."""
    _REGION_DESC = {
        "japan": ("日本株", "Tokyo Stock Exchange", ".T"),
        "jp": ("日本株", "Tokyo Stock Exchange", ".T"),
        "us": ("米国株", "US stock exchanges (NYSE/NASDAQ)", ""),
        "asean": ("ASEAN株", "Singapore/Thailand/Malaysia/Indonesia/Philippines exchanges",
                  ".SI/.BK/.KL/.JK/.PS"),
        "sg": ("シンガポール株", "Singapore Exchange", ".SI"),
        "th": ("タイ株", "Stock Exchange of Thailand", ".BK"),
        "hk": ("香港株", "Hong Kong Stock Exchange", ".HK"),
        "kr": ("韓国株", "Korea Exchange", ".KS"),
        "tw": ("台湾株", "Taiwan Stock Exchange", ".TW"),
    }
    label, exchange, suffix = _REGION_DESC.get(region, _REGION_DESC["japan"])

    theme_part = f"\nFocus specifically on the theme/sector: {theme}" if theme else ""

    if suffix:
        suffix_inst = (
            f"Use Yahoo Finance ticker format with suffix '{suffix}' "
            f"(e.g., 7203{suffix.split('/')[0]} for Toyota)."
        )
    else:
        suffix_inst = "Use standard Yahoo Finance ticker symbols (e.g., AAPL, MSFT)."

    if region in ("japan", "jp"):
        return (
            f"X（Twitter）上で今、投資家の間で話題になっている{label}を検索してください。"
            f"{theme_part}\n\n"
            f"決算サプライズ、新製品発表、規制変更、業界トレンドなどで注目されている"
            f"銘柄を10〜20件見つけてください。\n"
            f"各銘柄について、ティッカーシンボルと話題の理由を提供してください。\n\n"
            f"重要: {suffix_inst}\n"
            f"Yahoo Finance で検索可能な実在のティッカーのみを返してください。\n\n"
            f"JSON形式で回答:\n"
            f'{{\n'
            f'  "stocks": [\n'
            f'    {{"ticker": "シンボル", "name": "企業名", "reason": "話題の理由"}}\n'
            f'  ],\n'
            f'  "market_context": "X上の市場センチメント概要"\n'
            f'}}'
        )
    return (
        f"Search X (Twitter) for stocks that are currently trending or heavily discussed "
        f"among investors in the {label} ({exchange}) market.{theme_part}\n\n"
        f"Find 10-20 stocks getting significant attention on X right now. "
        f"For each stock, provide the ticker symbol and a brief reason WHY it is trending.\n\n"
        f"IMPORTANT: {suffix_inst}\n"
        f"Return ONLY valid, real ticker symbols that can be looked up on Yahoo Finance.\n\n"
        f"Respond in JSON format:\n"
        f'{{\n'
        f'  "stocks": [\n'
        f'    {{"ticker": "SYMBOL", "name": "Company Name", "reason": "Why it is trending"}}\n'
        f'  ],\n'
        f'  "market_context": "Brief summary of the current market mood on X"\n'
        f'}}'
    )


def _build_market_prompt(market_or_index: str) -> str:
    """Build the prompt for market research."""
    return (
        f"「{market_or_index}」の最新マーケット概況を、X（Twitter）とWebの情報をもとに調査してください。\n\n"
        f"1. 直近の値動きと要因\n"
        f"2. マクロ経済の影響（金利・為替・商品）\n"
        f"3. センチメント（強気/弱気のバランス）\n"
        f"4. 注目イベント・経済指標の予定\n"
        f"5. セクターローテーションの兆候\n\n"
        f"JSON形式で回答:\n"
        f'{{\n'
        f'  "price_action": "直近の値動きサマリー",\n'
        f'  "macro_factors": ["要因1", "要因2"],\n'
        f'  "sentiment": {{\n'
        f'    "score": 0.0,\n'
        f'    "summary": "概要"\n'
        f'  }},\n'
        f'  "upcoming_events": ["イベント1", "イベント2"],\n'
        f'  "sector_rotation": ["兆候1", "兆候2"]\n'
        f'}}'
    )


# ---------------------------------------------------------------------------
# Public search functions
# ---------------------------------------------------------------------------

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

    raw_text = _call_grok_api(_build_sentiment_prompt(symbol, company_name), timeout)
    if not raw_text:
        return empty_result

    result = dict(empty_result)
    result["raw_response"] = raw_text

    parsed = _parse_json_response(raw_text)
    if isinstance(parsed.get("positive"), list):
        result["positive"] = parsed["positive"]
    if isinstance(parsed.get("negative"), list):
        result["negative"] = parsed["negative"]
    score = parsed.get("sentiment_score")
    if isinstance(score, (int, float)):
        result["sentiment_score"] = max(-1.0, min(1.0, float(score)))

    return result


def search_stock_deep(
    symbol: str,
    company_name: str = "",
    timeout: int = 30,
) -> dict:
    """Deep research on a stock via X and web search.

    Parameters
    ----------
    symbol : str
        Ticker symbol (e.g. "7203.T", "AAPL").
    company_name : str
        Company name for prompt accuracy.
    timeout : int
        Request timeout in seconds.

    Returns
    -------
    dict
        See EMPTY_STOCK_DEEP for the schema.
    """
    raw_text = _call_grok_api(_build_stock_deep_prompt(symbol, company_name), timeout)
    if not raw_text:
        return dict(EMPTY_STOCK_DEEP)

    result = dict(EMPTY_STOCK_DEEP)
    result["raw_response"] = raw_text

    parsed = _parse_json_response(raw_text)
    if not parsed:
        return result

    if isinstance(parsed.get("recent_news"), list):
        result["recent_news"] = parsed["recent_news"]

    catalysts = parsed.get("catalysts")
    if isinstance(catalysts, dict):
        result["catalysts"] = {
            "positive": catalysts.get("positive", []) if isinstance(catalysts.get("positive"), list) else [],
            "negative": catalysts.get("negative", []) if isinstance(catalysts.get("negative"), list) else [],
        }

    if isinstance(parsed.get("analyst_views"), list):
        result["analyst_views"] = parsed["analyst_views"]

    x_sent = parsed.get("x_sentiment")
    if isinstance(x_sent, dict):
        score = x_sent.get("score", 0.0)
        result["x_sentiment"] = {
            "score": max(-1.0, min(1.0, float(score))) if isinstance(score, (int, float)) else 0.0,
            "summary": x_sent.get("summary", "") if isinstance(x_sent.get("summary"), str) else "",
            "key_opinions": x_sent.get("key_opinions", []) if isinstance(x_sent.get("key_opinions"), list) else [],
        }

    if isinstance(parsed.get("competitive_notes"), list):
        result["competitive_notes"] = parsed["competitive_notes"]

    return result


def search_industry(
    industry_or_theme: str,
    timeout: int = 30,
) -> dict:
    """Research an industry or theme via X and web search.

    Parameters
    ----------
    industry_or_theme : str
        Industry name or theme (e.g. "半導体", "EV", "AI").
    timeout : int
        Request timeout in seconds.

    Returns
    -------
    dict
        See EMPTY_INDUSTRY for the schema.
    """
    raw_text = _call_grok_api(_build_industry_prompt(industry_or_theme), timeout)
    if not raw_text:
        return dict(EMPTY_INDUSTRY)

    result = dict(EMPTY_INDUSTRY)
    result["raw_response"] = raw_text

    parsed = _parse_json_response(raw_text)
    if not parsed:
        return result

    if isinstance(parsed.get("trends"), list):
        result["trends"] = parsed["trends"]
    if isinstance(parsed.get("key_players"), list):
        result["key_players"] = parsed["key_players"]
    if isinstance(parsed.get("growth_drivers"), list):
        result["growth_drivers"] = parsed["growth_drivers"]
    if isinstance(parsed.get("risks"), list):
        result["risks"] = parsed["risks"]
    if isinstance(parsed.get("regulatory"), list):
        result["regulatory"] = parsed["regulatory"]
    if isinstance(parsed.get("investor_focus"), list):
        result["investor_focus"] = parsed["investor_focus"]

    return result


def search_market(
    market_or_index: str,
    timeout: int = 30,
) -> dict:
    """Research a market or index via X and web search.

    Parameters
    ----------
    market_or_index : str
        Market name or index (e.g. "日経平均", "S&P500").
    timeout : int
        Request timeout in seconds.

    Returns
    -------
    dict
        See EMPTY_MARKET for the schema.
    """
    raw_text = _call_grok_api(_build_market_prompt(market_or_index), timeout)
    if not raw_text:
        return dict(EMPTY_MARKET)

    result = dict(EMPTY_MARKET)
    result["raw_response"] = raw_text

    parsed = _parse_json_response(raw_text)
    if not parsed:
        return result

    if isinstance(parsed.get("price_action"), str):
        result["price_action"] = parsed["price_action"]
    if isinstance(parsed.get("macro_factors"), list):
        result["macro_factors"] = parsed["macro_factors"]

    sentiment = parsed.get("sentiment")
    if isinstance(sentiment, dict):
        score = sentiment.get("score", 0.0)
        result["sentiment"] = {
            "score": max(-1.0, min(1.0, float(score))) if isinstance(score, (int, float)) else 0.0,
            "summary": sentiment.get("summary", "") if isinstance(sentiment.get("summary"), str) else "",
        }

    if isinstance(parsed.get("upcoming_events"), list):
        result["upcoming_events"] = parsed["upcoming_events"]
    if isinstance(parsed.get("sector_rotation"), list):
        result["sector_rotation"] = parsed["sector_rotation"]

    return result


def search_trending_stocks(
    region: str = "japan",
    theme: Optional[str] = None,
    timeout: int = 30,
) -> dict:
    """Search X for currently trending stocks in a specific market region.

    Parameters
    ----------
    region : str
        Market region (japan/us/asean/sg/hk/kr/tw).
    theme : str | None
        Optional theme/sector filter (AI/semiconductor/EV/etc).
    timeout : int
        Request timeout in seconds.

    Returns
    -------
    dict
        Keys: stocks (list of {ticker, name, reason}),
              market_context (str), raw_response (str).
    """
    raw_text = _call_grok_api(_build_trending_prompt(region, theme), timeout)
    if not raw_text:
        return dict(EMPTY_TRENDING)

    result = dict(EMPTY_TRENDING)
    result["raw_response"] = raw_text

    parsed = _parse_json_response(raw_text)
    if not parsed:
        return result

    stocks_raw = parsed.get("stocks")
    if isinstance(stocks_raw, list):
        validated = []
        for item in stocks_raw:
            if isinstance(item, dict) and isinstance(item.get("ticker"), str):
                validated.append({
                    "ticker": item["ticker"].strip(),
                    "name": item.get("name", "") if isinstance(item.get("name"), str) else "",
                    "reason": item.get("reason", "") if isinstance(item.get("reason"), str) else "",
                })
        result["stocks"] = validated

    if isinstance(parsed.get("market_context"), str):
        result["market_context"] = parsed["market_context"]

    return result
