"""Tests for screener max_results passed to screen_stocks()."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.screening.screener import AlphaScreener, PullbackScreener, QueryScreener


def _make_raw_quotes(n: int) -> list[dict]:
    """Create raw Yahoo Finance quote dicts for testing."""
    return [
        {
            "symbol": f"STOCK{i}",
            "shortName": f"Stock {i}",
            "regularMarketPrice": 100.0 + i,
            "trailingPE": 10.0,
            "priceToBook": 1.0,
            "dividendYield": 3.0,  # yfinance percentage: 3.0%
            "returnOnEquity": 0.12,
            "revenueGrowth": 0.08,
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# QueryScreener max_results
# ---------------------------------------------------------------------------


class TestQueryScreenerMaxResults:
    """Verify QueryScreener passes correct max_results to screen_stocks."""

    @patch("src.core.screening.screener.build_query")
    def test_normal_mode(self, mock_build_query, mock_yahoo_client):
        """top_n=20, no pullback -> max_results = 20 * 5 = 100."""
        mock_build_query.return_value = MagicMock()
        mock_yahoo_client.screen_stocks.return_value = _make_raw_quotes(20)

        screener = QueryScreener(mock_yahoo_client)
        screener.screen(region="jp", top_n=20, preset="value")

        # Check max_results arg
        call_kwargs = mock_yahoo_client.screen_stocks.call_args
        assert call_kwargs.kwargs.get("max_results", call_kwargs[1].get("max_results")) == 100

    @patch("src.core.screening.screener.build_query")
    def test_pullback_mode(self, mock_build_query, mock_yahoo_client):
        """top_n=20, with_pullback=True -> max_results = max(100, 250) = 250."""
        mock_build_query.return_value = MagicMock()
        mock_yahoo_client.screen_stocks.return_value = _make_raw_quotes(20)
        mock_yahoo_client.get_price_history.return_value = None

        screener = QueryScreener(mock_yahoo_client)
        screener.screen(region="jp", top_n=20, preset="value", with_pullback=True)

        call_kwargs = mock_yahoo_client.screen_stocks.call_args
        assert call_kwargs.kwargs.get("max_results", call_kwargs[1].get("max_results")) == 250

    @patch("src.core.screening.screener.build_query")
    def test_large_top_n_normal(self, mock_build_query, mock_yahoo_client):
        """top_n=200 -> max_results = 200 * 5 = 1000."""
        mock_build_query.return_value = MagicMock()
        mock_yahoo_client.screen_stocks.return_value = _make_raw_quotes(10)

        screener = QueryScreener(mock_yahoo_client)
        screener.screen(region="jp", top_n=200, preset="value")

        call_kwargs = mock_yahoo_client.screen_stocks.call_args
        assert call_kwargs.kwargs.get("max_results", call_kwargs[1].get("max_results")) == 1000

    @patch("src.core.screening.screener.build_query")
    def test_large_top_n_pullback(self, mock_build_query, mock_yahoo_client):
        """top_n=200, with_pullback=True -> max_results = max(1000, 250) = 1000."""
        mock_build_query.return_value = MagicMock()
        mock_yahoo_client.screen_stocks.return_value = _make_raw_quotes(10)
        mock_yahoo_client.get_price_history.return_value = None

        screener = QueryScreener(mock_yahoo_client)
        screener.screen(region="jp", top_n=200, preset="value", with_pullback=True)

        call_kwargs = mock_yahoo_client.screen_stocks.call_args
        assert call_kwargs.kwargs.get("max_results", call_kwargs[1].get("max_results")) == 1000


# ---------------------------------------------------------------------------
# PullbackScreener max_results
# ---------------------------------------------------------------------------


class TestPullbackScreenerMaxResults:
    """Verify PullbackScreener passes correct max_results to screen_stocks."""

    @patch("src.core.screening.screener.build_query")
    def test_default_top_n(self, mock_build_query, mock_yahoo_client):
        """top_n=20 -> max_results = max(100, 250) = 250."""
        mock_build_query.return_value = MagicMock()
        mock_yahoo_client.screen_stocks.return_value = []

        screener = PullbackScreener(mock_yahoo_client)
        screener.screen(region="jp", top_n=20)

        call_kwargs = mock_yahoo_client.screen_stocks.call_args
        assert call_kwargs.kwargs.get("max_results", call_kwargs[1].get("max_results")) == 250

    @patch("src.core.screening.screener.build_query")
    def test_large_top_n(self, mock_build_query, mock_yahoo_client):
        """top_n=100 -> max_results = max(500, 250) = 500."""
        mock_build_query.return_value = MagicMock()
        mock_yahoo_client.screen_stocks.return_value = []

        screener = PullbackScreener(mock_yahoo_client)
        screener.screen(region="jp", top_n=100)

        call_kwargs = mock_yahoo_client.screen_stocks.call_args
        assert call_kwargs.kwargs.get("max_results", call_kwargs[1].get("max_results")) == 500


# ---------------------------------------------------------------------------
# AlphaScreener max_results
# ---------------------------------------------------------------------------


class TestAlphaScreenerMaxResults:
    """Verify AlphaScreener passes correct max_results to screen_stocks."""

    @patch("src.core.screening.screener.build_query")
    def test_default_top_n(self, mock_build_query, mock_yahoo_client):
        """top_n=20 -> max_results = max(100, 250) = 250."""
        mock_build_query.return_value = MagicMock()
        mock_yahoo_client.screen_stocks.return_value = []

        screener = AlphaScreener(mock_yahoo_client)
        screener.screen(region="jp", top_n=20)

        call_kwargs = mock_yahoo_client.screen_stocks.call_args
        assert call_kwargs.kwargs.get("max_results", call_kwargs[1].get("max_results")) == 250

    @patch("src.core.screening.screener.build_query")
    def test_large_top_n(self, mock_build_query, mock_yahoo_client):
        """top_n=100 -> max_results = max(500, 250) = 500."""
        mock_build_query.return_value = MagicMock()
        mock_yahoo_client.screen_stocks.return_value = []

        screener = AlphaScreener(mock_yahoo_client)
        screener.screen(region="jp", top_n=100)

        call_kwargs = mock_yahoo_client.screen_stocks.call_args
        assert call_kwargs.kwargs.get("max_results", call_kwargs[1].get("max_results")) == 500
