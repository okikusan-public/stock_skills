"""Tests for small-cap classification and allocation (KIK-438)."""

import pytest

from src.core.portfolio.small_cap import (
    classify_market_cap,
    check_small_cap_allocation,
    _SMALL_CAP_THRESHOLDS,
    _LARGE_CAP_MULTIPLIER,
)
from src.core.ticker_utils import infer_region_code


# ---------------------------------------------------------------------------
# classify_market_cap
# ---------------------------------------------------------------------------

class TestClassifyMarketCap:
    """Tests for classify_market_cap()."""

    def test_jp_small(self):
        assert classify_market_cap(50_000_000_000, "jp") == "小型"

    def test_jp_small_boundary(self):
        assert classify_market_cap(100_000_000_000, "jp") == "小型"

    def test_jp_mid(self):
        assert classify_market_cap(200_000_000_000, "jp") == "中型"

    def test_jp_mid_boundary(self):
        threshold = _SMALL_CAP_THRESHOLDS["jp"] * _LARGE_CAP_MULTIPLIER
        assert classify_market_cap(threshold, "jp") == "中型"

    def test_jp_large(self):
        assert classify_market_cap(1_000_000_000_000, "jp") == "大型"

    def test_us_small(self):
        assert classify_market_cap(500_000_000, "us") == "小型"

    def test_us_mid(self):
        assert classify_market_cap(2_000_000_000, "us") == "中型"

    def test_us_large(self):
        assert classify_market_cap(10_000_000_000, "us") == "大型"

    def test_sg_small(self):
        assert classify_market_cap(1_000_000_000, "sg") == "小型"

    def test_hk_small(self):
        assert classify_market_cap(5_000_000_000, "hk") == "小型"

    def test_kr_mid(self):
        assert classify_market_cap(2_000_000_000_000, "kr") == "中型"

    def test_none_market_cap(self):
        assert classify_market_cap(None, "jp") == "不明"

    def test_zero_market_cap(self):
        assert classify_market_cap(0, "us") == "不明"

    def test_negative_market_cap(self):
        assert classify_market_cap(-100, "jp") == "不明"

    def test_unknown_region(self):
        assert classify_market_cap(1_000_000, "xx") == "不明"

    @pytest.mark.parametrize("region", list(_SMALL_CAP_THRESHOLDS.keys()))
    def test_all_regions_have_thresholds(self, region):
        """Every region should classify just-above-threshold as 中型."""
        threshold = _SMALL_CAP_THRESHOLDS[region]
        assert classify_market_cap(threshold + 1, region) == "中型"


# ---------------------------------------------------------------------------
# check_small_cap_allocation
# ---------------------------------------------------------------------------

class TestCheckSmallCapAllocation:
    """Tests for check_small_cap_allocation()."""

    def test_ok_level(self):
        result = check_small_cap_allocation(0.10)
        assert result["level"] == "ok"
        assert result["weight"] == 0.10

    def test_warning_level(self):
        result = check_small_cap_allocation(0.30)
        assert result["level"] == "warning"

    def test_critical_level(self):
        result = check_small_cap_allocation(0.40)
        assert result["level"] == "critical"

    def test_zero_weight(self):
        result = check_small_cap_allocation(0.0)
        assert result["level"] == "ok"

    def test_boundary_warn(self):
        # At exactly 25%, should still be ok (> not >=)
        result = check_small_cap_allocation(0.25)
        assert result["level"] == "ok"

    def test_boundary_crit(self):
        # At exactly 35%, should still be warning (> not >=)
        result = check_small_cap_allocation(0.35)
        assert result["level"] == "warning"

    def test_just_above_warn(self):
        result = check_small_cap_allocation(0.251)
        assert result["level"] == "warning"

    def test_just_above_crit(self):
        result = check_small_cap_allocation(0.351)
        assert result["level"] == "critical"


# ---------------------------------------------------------------------------
# infer_region_code
# ---------------------------------------------------------------------------

class TestInferRegionCode:
    """Tests for infer_region_code()."""

    def test_jp_suffix(self):
        assert infer_region_code("7203.T") == "jp"

    def test_us_no_suffix(self):
        assert infer_region_code("AAPL") == "us"

    def test_sg_suffix(self):
        assert infer_region_code("D05.SI") == "sg"

    def test_hk_suffix(self):
        assert infer_region_code("0005.HK") == "hk"

    def test_kr_ks(self):
        assert infer_region_code("005930.KS") == "kr"

    def test_kr_kq(self):
        assert infer_region_code("373220.KQ") == "kr"

    def test_tw_suffix(self):
        assert infer_region_code("2330.TW") == "tw"

    def test_cn_ss(self):
        assert infer_region_code("600519.SS") == "cn"

    def test_cash_jpy(self):
        assert infer_region_code("JPY.CASH") == "jp"

    def test_cash_usd(self):
        assert infer_region_code("USD.CASH") == "us"

    def test_unknown_suffix_defaults_us(self):
        assert infer_region_code("XYZ.ZZ") == "us"
