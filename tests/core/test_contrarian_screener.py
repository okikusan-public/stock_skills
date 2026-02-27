"""Tests for src/core/screening/contrarian_screener.py (KIK-504, KIK-519)."""

import pandas as pd
import numpy as np
import pytest

from src.core.screening.contrarian_screener import ContrarianScreener


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_oversold_hist() -> pd.DataFrame:
    """Generate history where RSI is very low (sharp recent decline)."""
    n = 250
    dates = pd.bdate_range(end="2026-02-27", periods=n)
    prices = np.full(n, 1000.0)
    prices[200:] = np.linspace(1000, 600, 50)
    volumes = np.full(n, 300_000.0)
    volumes[-5:] = 900_000
    return pd.DataFrame({"Close": prices, "Volume": volumes}, index=dates)


def _make_flat_hist() -> pd.DataFrame:
    """Generate flat price history (RSI ~50)."""
    n = 250
    dates = pd.bdate_range(end="2026-02-27", periods=n)
    prices = np.full(n, 1000.0) + np.random.RandomState(42).randn(n) * 2
    volumes = np.full(n, 300_000.0)
    return pd.DataFrame({"Close": prices, "Volume": volumes}, index=dates)


def _make_quote(symbol: str, per: float = 8.0, pbr: float = 0.7, roe: float = 0.10) -> dict:
    """Create a normalized-like raw quote for screen_stocks mock."""
    return {
        "symbol": symbol,
        "shortName": f"Company {symbol}",
        "sector": "Technology",
        "industry": "Semiconductors",
        "currency": "JPY",
        "regularMarketPrice": 1000.0,
        "marketCap": 100_000_000_000,
        "trailingPE": per,
        "priceToBook": pbr,
        "returnOnEquity": roe,
        "dividendYield": 3.0,
        "revenueGrowth": 0.05,
        "earningsGrowth": 0.08,
        "exchange": "JPX",
    }


def _make_detail(eps_growth: float = 0.05, fcf: float = 10_000_000_000,
                 roe: float = 0.12, div_yield: float = 0.04) -> dict:
    """Create stock detail dict."""
    return {
        "eps_growth": eps_growth,
        "fcf": fcf,
        "market_cap": 100_000_000_000,
        "roe": roe,
        "dividend_yield_trailing": div_yield,
    }


class _MockYahooClient:
    """Mock yahoo_client for ContrarianScreener tests."""

    def __init__(self, quotes=None, hist=None, detail=None):
        self._quotes = quotes or []
        self._hist = hist
        self._detail = detail or {}

    def screen_stocks(self, query, size=250, max_results=250,
                      sort_field=None, sort_asc=False):
        return self._quotes

    def get_price_history(self, symbol, period="1y"):
        if callable(self._hist):
            return self._hist(symbol)
        return self._hist

    def get_stock_detail(self, symbol):
        if callable(self._detail):
            return self._detail(symbol)
        return self._detail


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestContrarianScreener:
    def test_screen_returns_contrarian_results(self):
        """Normal case: quotes with oversold hist + good fundamentals."""
        quotes = [
            _make_quote("1001.T", per=7, pbr=0.4, roe=0.12),
            _make_quote("1002.T", per=9, pbr=0.6, roe=0.10),
        ]
        detail = _make_detail(eps_growth=0.05, fcf=15_000_000_000, roe=0.15, div_yield=0.04)
        hist = _make_oversold_hist()

        screener = ContrarianScreener(_MockYahooClient(
            quotes=quotes, hist=hist, detail=detail,
        ))
        results = screener.screen(region="jp", top_n=10)

        assert len(results) > 0
        for r in results:
            assert "contrarian_score" in r
            assert "contrarian_grade" in r
            assert r["contrarian_score"] >= 30.0

    def test_screen_empty_when_no_quotes(self):
        """EquityQuery returns nothing → empty results."""
        screener = ContrarianScreener(_MockYahooClient(quotes=[]))
        results = screener.screen(region="jp")
        assert results == []

    def test_screen_filters_low_score(self):
        """Stocks with score < 30 are excluded."""
        quotes = [_make_quote("1001.T", per=14, pbr=1.4, roe=0.04)]
        # Flat hist → low technical score
        # High PER/PBR → low valuation score
        # Low ROE → low fundamental score
        detail = _make_detail(eps_growth=-0.10, fcf=1_000_000_000, roe=0.03, div_yield=0.005)
        hist = _make_flat_hist()

        screener = ContrarianScreener(_MockYahooClient(
            quotes=quotes, hist=hist, detail=detail,
        ))
        results = screener.screen(region="jp")
        # All should be filtered out due to low score
        for r in results:
            assert r["contrarian_score"] >= 30.0

    def test_screen_sorts_by_contrarian_score(self):
        """Results are sorted by contrarian_score descending."""
        quotes = [
            _make_quote("1001.T", per=7, pbr=0.4, roe=0.15),
            _make_quote("1002.T", per=12, pbr=1.0, roe=0.08),
            _make_quote("1003.T", per=5, pbr=0.3, roe=0.18),
        ]

        def detail_by_symbol(symbol):
            if symbol == "1003.T":
                return _make_detail(eps_growth=0.15, fcf=20_000_000_000, roe=0.20, div_yield=0.06)
            elif symbol == "1001.T":
                return _make_detail(eps_growth=0.08, fcf=12_000_000_000, roe=0.15, div_yield=0.04)
            else:
                return _make_detail(eps_growth=0.02, fcf=5_000_000_000, roe=0.08, div_yield=0.02)

        screener = ContrarianScreener(_MockYahooClient(
            quotes=quotes,
            hist=_make_oversold_hist(),
            detail=detail_by_symbol,
        ))
        results = screener.screen(region="jp", top_n=10)

        if len(results) >= 2:
            scores = [r["contrarian_score"] for r in results]
            assert scores == sorted(scores, reverse=True)

    def test_screen_respects_top_n(self):
        """Only top_n results are returned."""
        quotes = [_make_quote(f"{i}.T", per=7, pbr=0.4, roe=0.12) for i in range(1001, 1011)]
        detail = _make_detail(eps_growth=0.05, fcf=15_000_000_000, roe=0.15, div_yield=0.04)

        screener = ContrarianScreener(_MockYahooClient(
            quotes=quotes,
            hist=_make_oversold_hist(),
            detail=detail,
        ))
        results = screener.screen(region="jp", top_n=3)
        assert len(results) <= 3

    def test_screen_with_none_detail(self):
        """get_stock_detail returns None → graceful handling."""
        quotes = [_make_quote("1001.T", per=7, pbr=0.4, roe=0.12)]
        screener = ContrarianScreener(_MockYahooClient(
            quotes=quotes,
            hist=_make_oversold_hist(),
            detail=None,
        ))
        # Should not raise
        results = screener.screen(region="jp")
        # May or may not have results depending on score with empty detail
        assert isinstance(results, list)

    def test_screen_with_none_hist(self):
        """get_price_history returns None → technical score 0."""
        quotes = [_make_quote("1001.T", per=6, pbr=0.3, roe=0.15)]
        detail = _make_detail(eps_growth=0.10, fcf=20_000_000_000, roe=0.18, div_yield=0.06)

        screener = ContrarianScreener(_MockYahooClient(
            quotes=quotes,
            hist=None,
            detail=detail,
        ))
        results = screener.screen(region="jp")
        # Valuation + fundamental alone may be >= 30
        assert isinstance(results, list)
        for r in results:
            assert r["tech_score"] == 0.0

    def test_result_fields(self):
        """Results contain all expected contrarian fields."""
        quotes = [_make_quote("1001.T", per=7, pbr=0.4, roe=0.12)]
        detail = _make_detail(eps_growth=0.05, fcf=15_000_000_000, roe=0.15, div_yield=0.04)

        screener = ContrarianScreener(_MockYahooClient(
            quotes=quotes,
            hist=_make_oversold_hist(),
            detail=detail,
        ))
        results = screener.screen(region="jp")
        if results:
            r = results[0]
            assert "contrarian_score" in r
            assert "contrarian_grade" in r
            assert "is_contrarian" in r
            assert "tech_score" in r
            assert "val_score" in r
            assert "fund_score" in r
            assert "rsi" in r
            assert "sma200_deviation" in r
            assert "bb_position" in r
            assert "volume_surge" in r
            # Original fields preserved
            assert "symbol" in r
            assert "per" in r
            assert "pbr" in r

    def test_default_criteria(self):
        """DEFAULT_CRITERIA has expected keys."""
        assert ContrarianScreener.DEFAULT_CRITERIA["max_per"] == 15
        assert ContrarianScreener.DEFAULT_CRITERIA["max_pbr"] == 1.5
        assert ContrarianScreener.DEFAULT_CRITERIA["min_roe"] == 0.03

    def test_min_score_threshold(self):
        """Minimum score threshold is 30."""
        assert ContrarianScreener._MIN_CONTRARIAN_SCORE == 30.0

    def test_screen_skips_no_symbol(self):
        """Quotes without symbol are skipped."""
        quotes = [{"shortName": "No Symbol Corp", "trailingPE": 7, "priceToBook": 0.5}]
        detail = _make_detail()
        screener = ContrarianScreener(_MockYahooClient(
            quotes=quotes, hist=_make_oversold_hist(), detail=detail,
        ))
        results = screener.screen(region="jp")
        assert results == []


# ---------------------------------------------------------------------------
# max_results performance tests (KIK-519)
# ---------------------------------------------------------------------------

class TestMaxResultsReduction:
    """Verify max_results is reduced for performance (KIK-519)."""

    def test_max_results_default_top_n(self):
        """top_n=10 → max_results=max(30, 30)=30."""
        called_args = {}

        class _SpyClient(_MockYahooClient):
            def screen_stocks(self, query, size=250, max_results=250, **kw):
                called_args["max_results"] = max_results
                return super().screen_stocks(query, size=size, max_results=max_results, **kw)

        quotes = [_make_quote("1001.T")]
        screener = ContrarianScreener(_SpyClient(
            quotes=quotes, hist=_make_oversold_hist(), detail=_make_detail(),
        ))
        screener.screen(region="jp", top_n=10)
        assert called_args["max_results"] == 30

    def test_max_results_scales_with_top_n(self):
        """top_n=20 → max_results=max(60, 30)=60."""
        called_args = {}

        class _SpyClient(_MockYahooClient):
            def screen_stocks(self, query, size=250, max_results=250, **kw):
                called_args["max_results"] = max_results
                return []

        screener = ContrarianScreener(_SpyClient())
        screener.screen(region="jp", top_n=20)
        assert called_args["max_results"] == 60
