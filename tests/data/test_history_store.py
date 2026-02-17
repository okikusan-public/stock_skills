"""Tests for src.data.history_store module."""

import json
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from src.data.history_store import (
    _safe_filename,
    load_history,
    list_history_files,
    save_health,
    save_market_context,
    save_report,
    save_research,
    save_screening,
    save_trade,
)


# ===================================================================
# Helpers
# ===================================================================

def _read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _sample_results():
    return [
        {
            "symbol": "7203.T",
            "name": "Toyota Motor",
            "price": 2850,
            "per": 10.5,
            "pbr": 0.95,
            "dividend_yield": 0.032,
            "roe": 0.12,
            "value_score": 72.5,
        },
        {
            "symbol": "AAPL",
            "name": "Apple Inc",
            "price": 175.0,
            "per": 28.0,
            "pbr": 45.0,
            "dividend_yield": 0.005,
            "roe": 1.5,
            "value_score": 35.0,
        },
    ]


def _sample_stock_data():
    return {
        "name": "Toyota Motor",
        "sector": "Consumer Cyclical",
        "industry": "Auto Manufacturers",
        "price": 2850,
        "per": 10.5,
        "pbr": 0.95,
        "dividend_yield": 0.032,
        "roe": 0.12,
        "roa": 0.05,
        "revenue_growth": 0.08,
        "market_cap": 35000000000000,
    }


def _sample_health_data():
    return {
        "positions": [
            {
                "symbol": "7203.T",
                "pnl_pct": 0.15,
                "trend_health": {"trend": "上昇"},
                "change_quality": {"quality_label": "良好"},
                "alert": {"level": "none"},
            },
            {
                "symbol": "AAPL",
                "pnl_pct": -0.05,
                "trend_health": {"trend": "下降"},
                "change_quality": {"quality_label": "1指標悪化"},
                "alert": {"level": "caution"},
            },
        ],
        "summary": {
            "total": 2,
            "healthy": 1,
            "early_warning": 0,
            "caution": 1,
            "exit": 0,
        },
    }


# ===================================================================
# save_screening
# ===================================================================


class TestSaveScreening:
    def test_save_creates_file(self, tmp_path):
        path = save_screening("value", "japan", _sample_results(), base_dir=str(tmp_path))
        assert Path(path).exists()

    def test_save_file_naming(self, tmp_path):
        path = save_screening("value", "japan", _sample_results(), base_dir=str(tmp_path))
        filename = Path(path).name
        today = date.today().isoformat()
        assert filename == f"{today}_japan_value.json"

    def test_save_contains_metadata(self, tmp_path):
        path = save_screening("value", "japan", _sample_results(), base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["category"] == "screen"
        assert data["preset"] == "value"
        assert data["region"] == "japan"
        assert data["date"] == date.today().isoformat()
        assert "_saved_at" in data
        assert "timestamp" in data

    def test_save_contains_results(self, tmp_path):
        results = _sample_results()
        path = save_screening("value", "japan", results, base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["count"] == 2
        assert len(data["results"]) == 2
        assert data["results"][0]["symbol"] == "7203.T"
        assert data["results"][1]["symbol"] == "AAPL"

    def test_save_with_sector(self, tmp_path):
        path = save_screening("value", "japan", _sample_results(), sector="Technology", base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["sector"] == "Technology"

    def test_save_without_sector(self, tmp_path):
        path = save_screening("value", "japan", _sample_results(), base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["sector"] is None

    def test_save_overwrites_same_day(self, tmp_path):
        results1 = [{"symbol": "A", "value_score": 50}]
        results2 = [{"symbol": "B", "value_score": 60}]
        path1 = save_screening("value", "japan", results1, base_dir=str(tmp_path))
        path2 = save_screening("value", "japan", results2, base_dir=str(tmp_path))
        assert path1 == path2
        data = _read_json(path2)
        assert data["results"][0]["symbol"] == "B"

    def test_save_creates_screen_subdirectory(self, tmp_path):
        save_screening("value", "japan", [], base_dir=str(tmp_path))
        assert (tmp_path / "screen").is_dir()

    def test_save_region_with_dot(self, tmp_path):
        """Region containing dots should be safe in filename."""
        path = save_screening("value", "jp.asia", [], base_dir=str(tmp_path))
        filename = Path(path).name
        assert "." not in filename.split("_", 1)[1].replace(".json", "")


# ===================================================================
# save_report
# ===================================================================


class TestSaveReport:
    def test_save_creates_file(self, tmp_path):
        path = save_report("7203.T", _sample_stock_data(), 72.5, "割安", base_dir=str(tmp_path))
        assert Path(path).exists()

    def test_save_file_naming(self, tmp_path):
        path = save_report("7203.T", _sample_stock_data(), 72.5, "割安", base_dir=str(tmp_path))
        filename = Path(path).name
        today = date.today().isoformat()
        assert filename == f"{today}_7203_T.json"

    def test_save_contains_score_and_verdict(self, tmp_path):
        path = save_report("7203.T", _sample_stock_data(), 72.5, "割安（買い検討）", base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["category"] == "report"
        assert data["symbol"] == "7203.T"
        assert data["value_score"] == 72.5
        assert data["verdict"] == "割安（買い検討）"
        assert data["name"] == "Toyota Motor"
        assert data["sector"] == "Consumer Cyclical"

    def test_save_creates_report_subdirectory(self, tmp_path):
        save_report("AAPL", {}, 50.0, "中立", base_dir=str(tmp_path))
        assert (tmp_path / "report").is_dir()


# ===================================================================
# save_trade
# ===================================================================


class TestSaveTrade:
    def test_save_buy(self, tmp_path):
        path = save_trade("7203.T", "buy", 100, 2850.0, "JPY", "2026-02-14", base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["category"] == "trade"
        assert data["trade_type"] == "buy"
        assert data["symbol"] == "7203.T"
        assert data["shares"] == 100
        assert data["price"] == 2850.0
        assert data["currency"] == "JPY"

    def test_save_sell(self, tmp_path):
        path = save_trade("AAPL", "sell", 5, 180.0, "USD", "2026-02-14", base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["trade_type"] == "sell"
        assert data["symbol"] == "AAPL"
        assert data["shares"] == 5

    def test_save_file_naming(self, tmp_path):
        path = save_trade("7203.T", "buy", 100, 2850.0, "JPY", "2026-02-14", base_dir=str(tmp_path))
        filename = Path(path).name
        today = date.today().isoformat()
        assert filename == f"{today}_buy_7203_T.json"

    def test_save_sell_file_naming(self, tmp_path):
        path = save_trade("AAPL", "sell", 5, 180.0, "USD", "2026-02-14", base_dir=str(tmp_path))
        filename = Path(path).name
        today = date.today().isoformat()
        assert filename == f"{today}_sell_AAPL.json"

    def test_save_with_memo(self, tmp_path):
        path = save_trade("7203.T", "buy", 100, 2850.0, "JPY", "2026-02-14", memo="割安でエントリー", base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["memo"] == "割安でエントリー"

    def test_save_creates_trade_subdirectory(self, tmp_path):
        save_trade("X", "buy", 1, 1.0, "USD", "2026-01-01", base_dir=str(tmp_path))
        assert (tmp_path / "trade").is_dir()


# ===================================================================
# save_health
# ===================================================================


class TestSaveHealth:
    def test_save_creates_file(self, tmp_path):
        path = save_health(_sample_health_data(), base_dir=str(tmp_path))
        assert Path(path).exists()

    def test_save_file_naming(self, tmp_path):
        path = save_health(_sample_health_data(), base_dir=str(tmp_path))
        filename = Path(path).name
        today = date.today().isoformat()
        assert filename == f"{today}_health.json"

    def test_save_contains_summary(self, tmp_path):
        path = save_health(_sample_health_data(), base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["category"] == "health"
        assert data["summary"]["total"] == 2
        assert data["summary"]["healthy"] == 1
        assert data["summary"]["caution"] == 1
        assert data["summary"]["exit"] == 0

    def test_save_contains_positions(self, tmp_path):
        path = save_health(_sample_health_data(), base_dir=str(tmp_path))
        data = _read_json(path)
        assert len(data["positions"]) == 2
        pos0 = data["positions"][0]
        assert pos0["symbol"] == "7203.T"
        assert pos0["trend"] == "上昇"
        assert pos0["quality_label"] == "良好"
        assert pos0["alert_level"] == "none"

    def test_save_creates_health_subdirectory(self, tmp_path):
        save_health({"positions": [], "summary": {}}, base_dir=str(tmp_path))
        assert (tmp_path / "health").is_dir()


# ===================================================================
# load_history
# ===================================================================


class TestLoadHistory:
    def test_load_empty_directory(self, tmp_path):
        result = load_history("screen", base_dir=str(tmp_path))
        assert result == []

    def test_load_nonexistent_directory(self, tmp_path):
        result = load_history("nonexistent", base_dir=str(tmp_path))
        assert result == []

    def test_load_returns_saved_data(self, tmp_path):
        save_screening("value", "japan", _sample_results(), base_dir=str(tmp_path))
        results = load_history("screen", base_dir=str(tmp_path))
        assert len(results) == 1
        assert results[0]["preset"] == "value"
        assert results[0]["region"] == "japan"

    def test_load_with_days_back(self, tmp_path):
        # Save a file for today
        save_screening("value", "japan", [], base_dir=str(tmp_path))

        # Manually create an old file (60 days ago)
        old_date = (date.today() - timedelta(days=60)).isoformat()
        old_dir = tmp_path / "screen"
        old_dir.mkdir(parents=True, exist_ok=True)
        old_file = old_dir / f"{old_date}_japan_old.json"
        with open(old_file, "w") as f:
            json.dump({"date": old_date, "preset": "old", "region": "japan"}, f)

        # days_back=30 should exclude the 60-day old file
        results = load_history("screen", days_back=30, base_dir=str(tmp_path))
        assert len(results) == 1
        assert results[0]["preset"] == "value"

        # days_back=90 should include both
        results_all = load_history("screen", days_back=90, base_dir=str(tmp_path))
        assert len(results_all) == 2

    def test_load_sorts_by_date_desc(self, tmp_path):
        screen_dir = tmp_path / "screen"
        screen_dir.mkdir(parents=True, exist_ok=True)

        dates = [
            (date.today() - timedelta(days=2)).isoformat(),
            date.today().isoformat(),
            (date.today() - timedelta(days=1)).isoformat(),
        ]
        for d in dates:
            filepath = screen_dir / f"{d}_japan_value.json"
            with open(filepath, "w") as f:
                json.dump({"date": d, "preset": "value"}, f)

        results = load_history("screen", base_dir=str(tmp_path))
        result_dates = [r["date"] for r in results]
        assert result_dates == sorted(result_dates, reverse=True)

    def test_load_skips_invalid_json(self, tmp_path):
        screen_dir = tmp_path / "screen"
        screen_dir.mkdir(parents=True, exist_ok=True)

        # Write a corrupted JSON file
        bad_file = screen_dir / f"{date.today().isoformat()}_bad.json"
        with open(bad_file, "w") as f:
            f.write("{invalid json content")

        # Write a valid file
        save_screening("value", "japan", [], base_dir=str(tmp_path))

        results = load_history("screen", base_dir=str(tmp_path))
        # Only the valid file should be loaded
        assert len(results) == 1
        assert results[0]["preset"] == "value"


# ===================================================================
# list_history_files
# ===================================================================


class TestListHistoryFiles:
    def test_list_empty(self, tmp_path):
        result = list_history_files("screen", base_dir=str(tmp_path))
        assert result == []

    def test_list_returns_paths(self, tmp_path):
        save_screening("value", "japan", [], base_dir=str(tmp_path))
        paths = list_history_files("screen", base_dir=str(tmp_path))
        assert len(paths) == 1
        assert paths[0].endswith(".json")

    def test_list_sorted_desc(self, tmp_path):
        screen_dir = tmp_path / "screen"
        screen_dir.mkdir(parents=True, exist_ok=True)

        for i in range(3):
            d = (date.today() - timedelta(days=i)).isoformat()
            filepath = screen_dir / f"{d}_test.json"
            with open(filepath, "w") as f:
                json.dump({}, f)

        paths = list_history_files("screen", base_dir=str(tmp_path))
        filenames = [Path(p).name for p in paths]
        assert filenames == sorted(filenames, reverse=True)


# ===================================================================
# _safe_filename
# ===================================================================


class TestSafeName:
    def test_dot_replacement(self):
        assert _safe_filename("7203.T") == "7203_T"

    def test_slash_replacement(self):
        assert _safe_filename("foo/bar") == "foo_bar"

    def test_special_chars_bbl(self):
        assert _safe_filename("BBL.BK") == "BBL_BK"

    def test_special_chars_z74(self):
        assert _safe_filename("Z74.SI") == "Z74_SI"

    def test_multiple_dots(self):
        assert _safe_filename("A.B.C") == "A_B_C"

    def test_no_special_chars(self):
        assert _safe_filename("AAPL") == "AAPL"

    def test_mixed_dot_and_slash(self):
        assert _safe_filename("a.b/c.d") == "a_b_c_d"


# ===================================================================
# numpy / NaN / Inf handling
# ===================================================================


class TestNumpyHandling:
    def test_numpy_float(self, tmp_path):
        results = [{"symbol": "X", "value_score": np.float64(72.5), "price": np.float64(100.0)}]
        path = save_screening("value", "japan", results, base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["results"][0]["value_score"] == 72.5
        assert isinstance(data["results"][0]["value_score"], float)

    def test_numpy_int(self, tmp_path):
        results = [{"symbol": "X", "value_score": 50, "shares": np.int64(100)}]
        path = save_screening("value", "japan", results, base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["results"][0]["shares"] == 100
        assert isinstance(data["results"][0]["shares"], int)

    def test_nan_sanitized(self, tmp_path):
        results = [{"symbol": "X", "value_score": float("nan"), "per": np.float64("nan")}]
        path = save_screening("value", "japan", results, base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["results"][0]["value_score"] is None
        assert data["results"][0]["per"] is None

    def test_inf_sanitized(self, tmp_path):
        results = [{"symbol": "X", "value_score": float("inf"), "per": np.float64("-inf")}]
        path = save_screening("value", "japan", results, base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["results"][0]["value_score"] is None
        assert data["results"][0]["per"] is None

    def test_numpy_array_serialized(self, tmp_path):
        results = [{"symbol": "X", "values": np.array([1.0, 2.0, 3.0])}]
        path = save_screening("value", "japan", results, base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["results"][0]["values"] == [1.0, 2.0, 3.0]


# ===================================================================
# base_dir parameter
# ===================================================================


# ===================================================================
# save_research (KIK-405)
# ===================================================================


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class TestSaveResearch:
    def test_stock_research(self, tmp_path):
        result = {
            "type": "stock",
            "symbol": "7203.T",
            "name": "Toyota",
            "fundamentals": {"per": 10.5, "pbr": 1.2},
            "value_score": 65.0,
            "grok_research": {"recent_news": "test news"},
            "x_sentiment": {"sentiment_score": 0.5},
            "news": [{"title": "headline"}],
        }
        path = save_research("stock", "7203.T", result, base_dir=str(tmp_path))
        assert Path(path).exists()
        data = _read_json(path)
        assert data["category"] == "research"
        assert data["research_type"] == "stock"
        assert data["target"] == "7203.T"
        assert data["symbol"] == "7203.T"
        assert data["name"] == "Toyota"
        assert data["value_score"] == 65.0
        assert "type" not in data  # "type" from result excluded
        assert data["_saved_at"] is not None

    def test_industry_research(self, tmp_path):
        result = {
            "type": "industry",
            "theme": "半導体",
            "grok_research": {"trends": "AI demand"},
        }
        path = save_research("industry", "半導体", result, base_dir=str(tmp_path))
        assert Path(path).exists()
        data = _read_json(path)
        assert data["research_type"] == "industry"
        assert data["target"] == "半導体"
        assert "research" in path

    def test_market_research(self, tmp_path):
        result = {
            "type": "market",
            "market": "日経平均",
            "macro_indicators": [{"name": "日経平均", "price": 40000}],
            "grok_research": {"sentiment": "bullish"},
        }
        path = save_research("market", "日経平均", result, base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["research_type"] == "market"
        assert data["macro_indicators"][0]["price"] == 40000

    def test_business_research(self, tmp_path):
        result = {
            "type": "business",
            "symbol": "7751.T",
            "name": "Canon",
            "grok_research": {"overview": "imaging company"},
        }
        path = save_research("business", "7751.T", result, base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["research_type"] == "business"
        assert data["target"] == "7751.T"

    def test_filename_format(self, tmp_path):
        result = {"type": "stock", "symbol": "AAPL"}
        path = save_research("stock", "AAPL", result, base_dir=str(tmp_path))
        fname = Path(path).name
        today = date.today().isoformat()
        assert fname.startswith(today)
        assert "stock_AAPL" in fname

    def test_load_research(self, tmp_path):
        result = {"type": "stock", "symbol": "7203.T"}
        save_research("stock", "7203.T", result, base_dir=str(tmp_path))
        loaded = load_history("research", base_dir=str(tmp_path))
        assert len(loaded) == 1
        assert loaded[0]["research_type"] == "stock"


# ===================================================================
# save_market_context (KIK-405)
# ===================================================================


class TestSaveMarketContext:
    def test_basic(self, tmp_path):
        context = {
            "indices": [
                {"name": "S&P500", "symbol": "^GSPC", "price": 5800},
                {"name": "日経平均", "symbol": "^N225", "price": 40000},
                {"name": "VIX", "symbol": "^VIX", "price": 15.0},
                {"name": "USD/JPY", "symbol": "JPY=X", "price": 150.0},
            ]
        }
        path = save_market_context(context, base_dir=str(tmp_path))
        assert Path(path).exists()
        data = _read_json(path)
        assert data["category"] == "market_context"
        assert len(data["indices"]) == 4
        assert data["_saved_at"] is not None

    def test_filename_format(self, tmp_path):
        context = {"indices": []}
        path = save_market_context(context, base_dir=str(tmp_path))
        fname = Path(path).name
        today = date.today().isoformat()
        assert fname == f"{today}_context.json"

    def test_load_market_context(self, tmp_path):
        context = {"indices": [{"name": "VIX", "price": 20.0}]}
        save_market_context(context, base_dir=str(tmp_path))
        loaded = load_history("market_context", base_dir=str(tmp_path))
        assert len(loaded) == 1
        assert loaded[0]["category"] == "market_context"

    def test_numpy_handling(self, tmp_path):
        context = {"indices": [{"name": "test", "price": np.float64(100.5)}]}
        path = save_market_context(context, base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["indices"][0]["price"] == 100.5


# ===================================================================
# base_dir parameter
# ===================================================================


class TestBaseDirParameter:
    def test_deep_base_dir(self, tmp_path):
        deep_dir = str(tmp_path / "a" / "b" / "c")
        path = save_screening("value", "japan", [], base_dir=deep_dir)
        assert Path(path).exists()
        assert "a/b/c/screen" in path or "a\\b\\c\\screen" in path
