"""Tests for KIK-469 Phase 2: ETF/stock partition in health check results."""

import pytest


def _make_result(symbol, is_etf=False, etf_health=None, alert_level="none"):
    """Helper to build a health check result dict."""
    result = {
        "symbol": symbol,
        "pnl_pct": 0.05,
        "trend_health": {"trend": "上昇"},
        "change_quality": {"is_etf": is_etf},
        "long_term": {},
        "alert": {"level": alert_level, "label": "なし", "emoji": ""},
    }
    if etf_health:
        result["change_quality"]["etf_health"] = etf_health
    return result


class TestPartitionLogic:
    """Test stock/ETF partition logic directly (same logic used in run_health_check)."""

    def _partition(self, results):
        """Replicate the partition logic from run_health_check."""
        stock_positions = [
            r for r in results
            if not r.get("change_quality", {}).get("is_etf")
        ]
        etf_positions = [
            r for r in results
            if r.get("change_quality", {}).get("is_etf")
        ]
        return stock_positions, etf_positions

    def test_mixed_portfolio_partitioned(self):
        """Mixed portfolio should have stocks and ETFs separated."""
        results = [
            _make_result("7203.T", is_etf=False),
            _make_result("VGK", is_etf=True),
            _make_result("AAPL", is_etf=False),
        ]
        stocks, etfs = self._partition(results)
        assert len(stocks) == 2
        assert len(etfs) == 1
        assert etfs[0]["symbol"] == "VGK"

    def test_stock_only_empty_etf(self):
        """Stock-only portfolio should have empty etf_positions."""
        results = [_make_result("7203.T"), _make_result("AAPL")]
        stocks, etfs = self._partition(results)
        assert len(stocks) == 2
        assert len(etfs) == 0

    def test_etf_only_empty_stock(self):
        """ETF-only portfolio should have empty stock_positions."""
        results = [_make_result("VGK", is_etf=True), _make_result("SPY", is_etf=True)]
        stocks, etfs = self._partition(results)
        assert len(stocks) == 0
        assert len(etfs) == 2

    def test_backward_compat_all_in_results(self):
        """All positions should be in results list regardless of type."""
        results = [
            _make_result("7203.T"),
            _make_result("VGK", is_etf=True),
        ]
        stocks, etfs = self._partition(results)
        assert len(stocks) + len(etfs) == len(results)

    def test_missing_change_quality(self):
        """Position without change_quality should be classified as stock."""
        results = [{"symbol": "UNKNOWN", "change_quality": {}}]
        stocks, etfs = self._partition(results)
        assert len(stocks) == 1
        assert len(etfs) == 0

    def test_is_etf_false_explicit(self):
        """Explicit is_etf=False should be classified as stock."""
        results = [_make_result("AAPL", is_etf=False)]
        stocks, etfs = self._partition(results)
        assert len(stocks) == 1
        assert len(etfs) == 0
