"""Tests for screen_stocks() pagination in src/data/yahoo_client.py."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.yahoo_client import screen_stocks


def _make_quotes(n: int, start: int = 0) -> list[dict]:
    """Create a list of n dummy quote dicts with unique symbols."""
    return [{"symbol": f"STOCK{start + i}"} for i in range(n)]


# ---------------------------------------------------------------------------
# Single page
# ---------------------------------------------------------------------------


class TestSinglePage:
    """When total <= page size, only one page is fetched."""

    @patch("src.data.yahoo_client.time.sleep")
    @patch("src.data.yahoo_client.yf.screen")
    def test_single_page(self, mock_screen, mock_sleep):
        quotes = _make_quotes(5)
        mock_screen.return_value = {"total": 5, "quotes": quotes}

        query = MagicMock()
        result = screen_stocks(query)

        assert len(result) == 5
        assert mock_screen.call_count == 1
        # No sleep needed when there is only one page
        mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# Multi page
# ---------------------------------------------------------------------------


class TestMultiPage:
    """When total > page size, multiple pages are fetched."""

    @patch("src.data.yahoo_client.time.sleep")
    @patch("src.data.yahoo_client.yf.screen")
    def test_multi_page(self, mock_screen, mock_sleep):
        page1 = _make_quotes(250, start=0)
        page2 = _make_quotes(250, start=250)
        page3 = _make_quotes(100, start=500)

        def side_effect(query, size=250, offset=0, sortField="intradaymarketcap", sortAsc=False):
            if offset == 0:
                return {"total": 600, "quotes": page1}
            elif offset == 250:
                return {"total": 600, "quotes": page2}
            elif offset == 500:
                return {"total": 600, "quotes": page3}
            return {"total": 600, "quotes": []}

        mock_screen.side_effect = side_effect

        query = MagicMock()
        result = screen_stocks(query)

        assert len(result) == 600
        assert mock_screen.call_count == 3
        # sleep(1) between pages (2 sleeps for 3 pages)
        assert mock_sleep.call_count == 2


# ---------------------------------------------------------------------------
# max_results limiting
# ---------------------------------------------------------------------------


class TestMaxResultsLimit:
    """max_results should cap the number of results fetched."""

    @patch("src.data.yahoo_client.time.sleep")
    @patch("src.data.yahoo_client.yf.screen")
    def test_max_results_limit(self, mock_screen, mock_sleep):
        quotes = _make_quotes(100)
        mock_screen.return_value = {"total": 1000, "quotes": quotes}

        query = MagicMock()
        result = screen_stocks(query, max_results=100)

        assert len(result) == 100
        # Should only call once since first page returns 100 which equals max_results
        assert mock_screen.call_count == 1


# ---------------------------------------------------------------------------
# max_results=0 means no limit
# ---------------------------------------------------------------------------


class TestMaxResultsZero:
    """max_results=0 should fetch all available pages."""

    @patch("src.data.yahoo_client.time.sleep")
    @patch("src.data.yahoo_client.yf.screen")
    def test_max_results_zero_means_no_limit(self, mock_screen, mock_sleep):
        page1 = _make_quotes(250, start=0)
        page2 = _make_quotes(250, start=250)

        def side_effect(query, size=250, offset=0, sortField="intradaymarketcap", sortAsc=False):
            if offset == 0:
                return {"total": 500, "quotes": page1}
            elif offset == 250:
                return {"total": 500, "quotes": page2}
            return {"total": 500, "quotes": []}

        mock_screen.side_effect = side_effect

        query = MagicMock()
        result = screen_stocks(query, max_results=0)

        assert len(result) == 500


# ---------------------------------------------------------------------------
# Empty responses
# ---------------------------------------------------------------------------


class TestEmptyResponses:
    """Handle None and empty responses gracefully."""

    @patch("src.data.yahoo_client.time.sleep")
    @patch("src.data.yahoo_client.yf.screen")
    def test_empty_response_none(self, mock_screen, mock_sleep):
        """yf.screen returns None -> empty list."""
        mock_screen.return_value = None

        query = MagicMock()
        result = screen_stocks(query)

        assert result == []

    @patch("src.data.yahoo_client.time.sleep")
    @patch("src.data.yahoo_client.yf.screen")
    def test_empty_quotes(self, mock_screen, mock_sleep):
        """yf.screen returns total=0 and empty quotes -> empty list."""
        mock_screen.return_value = {"total": 0, "quotes": []}

        query = MagicMock()
        result = screen_stocks(query)

        assert result == []


# ---------------------------------------------------------------------------
# Error handling (partial results)
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Errors during pagination should return partial results."""

    @patch("src.data.yahoo_client.time.sleep")
    @patch("src.data.yahoo_client.yf.screen")
    def test_error_returns_partial(self, mock_screen, mock_sleep):
        page1 = _make_quotes(250)

        call_count = 0

        def side_effect(query, size=250, offset=0, sortField="intradaymarketcap", sortAsc=False):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"total": 600, "quotes": page1}
            raise ConnectionError("API error on page 2")

        mock_screen.side_effect = side_effect

        query = MagicMock()
        result = screen_stocks(query)

        # Should return the 250 items from page 1
        assert len(result) == 250


# ---------------------------------------------------------------------------
# Rate limit delay
# ---------------------------------------------------------------------------


class TestRateLimitDelay:
    """Verify time.sleep(1) is called between pages."""

    @patch("src.data.yahoo_client.time.sleep")
    @patch("src.data.yahoo_client.yf.screen")
    def test_rate_limit_delay(self, mock_screen, mock_sleep):
        page1 = _make_quotes(250, start=0)
        page2 = _make_quotes(50, start=250)

        def side_effect(query, size=250, offset=0, sortField="intradaymarketcap", sortAsc=False):
            if offset == 0:
                return {"total": 300, "quotes": page1}
            elif offset == 250:
                return {"total": 300, "quotes": page2}
            return {"total": 300, "quotes": []}

        mock_screen.side_effect = side_effect

        query = MagicMock()
        screen_stocks(query)

        # sleep(1) called once between page 1 and page 2
        mock_sleep.assert_called_once_with(1)


# ---------------------------------------------------------------------------
# Page size adjustment
# ---------------------------------------------------------------------------


class TestPageSizeAdjustment:
    """When max_results limits the second page, size should be adjusted."""

    @patch("src.data.yahoo_client.time.sleep")
    @patch("src.data.yahoo_client.yf.screen")
    def test_page_size_adjustment(self, mock_screen, mock_sleep):
        page1 = _make_quotes(250, start=0)
        page2 = _make_quotes(50, start=250)

        def side_effect(query, size=250, offset=0, sortField="intradaymarketcap", sortAsc=False):
            if offset == 0:
                return {"total": 1000, "quotes": page1}
            elif offset == 250:
                return {"total": 1000, "quotes": page2[:size]}
            return {"total": 1000, "quotes": []}

        mock_screen.side_effect = side_effect

        query = MagicMock()
        result = screen_stocks(query, max_results=300)

        # Check that second call used size=50 (300 - 250 = 50)
        calls = mock_screen.call_args_list
        assert len(calls) == 2

        # First call: size=250 (default, min(250, 300))
        assert calls[0].kwargs.get("size", calls[0][1].get("size", 250)) == 250
        # Second call: size=50 (min(250, 300-250))
        assert calls[1].kwargs.get("size", calls[1][1].get("size", 250)) == 50


# ---------------------------------------------------------------------------
# Offset parameter
# ---------------------------------------------------------------------------


class TestOffsetParameter:
    """Verify the offset parameter is correctly passed on each call."""

    @patch("src.data.yahoo_client.time.sleep")
    @patch("src.data.yahoo_client.yf.screen")
    def test_offset_parameter_passed(self, mock_screen, mock_sleep):
        page1 = _make_quotes(250, start=0)
        page2 = _make_quotes(250, start=250)
        page3 = _make_quotes(100, start=500)

        def side_effect(query, size=250, offset=0, sortField="intradaymarketcap", sortAsc=False):
            if offset == 0:
                return {"total": 600, "quotes": page1}
            elif offset == 250:
                return {"total": 600, "quotes": page2}
            elif offset == 500:
                return {"total": 600, "quotes": page3}
            return {"total": 600, "quotes": []}

        mock_screen.side_effect = side_effect

        query = MagicMock()
        screen_stocks(query)

        calls = mock_screen.call_args_list
        assert len(calls) == 3

        # Verify offset values: 0, 250, 500
        offsets = [c.kwargs.get("offset", c[1].get("offset", 0)) for c in calls]
        assert offsets == [0, 250, 500]
