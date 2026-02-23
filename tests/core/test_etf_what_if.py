"""Tests for KIK-469 Phase 2: ETF quality signals in what-if judgment."""

import pytest
from src.core.portfolio.portfolio_simulation import _compute_judgment


def _base_before_after():
    """Base before/after dicts with neutral values."""
    before = {"sector_hhi": 0.3, "region_hhi": 0.2, "forecast_base": 0.08}
    after = {"sector_hhi": 0.3, "region_hhi": 0.2, "forecast_base": 0.08}
    return before, after


class TestETFQualityInJudgment:
    """Test ETF quality signals in _compute_judgment."""

    def test_judgment_etf_high_quality_positive(self):
        """High quality ETF (score >= 75) should add positive reason."""
        before, after = _base_before_after()
        proposed_health = [
            {
                "symbol": "VGK",
                "alert": {"level": "none", "label": "なし"},
                "change_quality": {
                    "is_etf": True,
                    "etf_health": {
                        "score": 85,
                        "alerts": [],
                        "expense_label": "低コスト",
                        "aum_label": "大型",
                    },
                },
            }
        ]
        result = _compute_judgment(before, after, proposed_health)
        reasons_text = " ".join(result["reasons"])
        assert "ETF品質良好" in reasons_text
        assert "VGK" in reasons_text

    def test_judgment_etf_low_quality_warning(self):
        """Low quality ETF (score < 40) should trigger warning."""
        before, after = _base_before_after()
        proposed_health = [
            {
                "symbol": "BAD_ETF",
                "alert": {"level": "none", "label": "なし"},
                "change_quality": {
                    "is_etf": True,
                    "etf_health": {
                        "score": 30,
                        "alerts": ["経費率が高い"],
                        "expense_label": "高コスト",
                        "aum_label": "小型",
                    },
                },
            }
        ]
        result = _compute_judgment(before, after, proposed_health)
        reasons_text = " ".join(result["reasons"])
        assert "ETF品質低" in reasons_text
        assert result["recommendation"] == "caution"

    def test_judgment_etf_alerts_in_reasons(self):
        """ETF alerts should appear in reasons."""
        before, after = _base_before_after()
        proposed_health = [
            {
                "symbol": "RISKY_ETF",
                "alert": {"level": "none", "label": "なし"},
                "change_quality": {
                    "is_etf": True,
                    "etf_health": {
                        "score": 50,
                        "alerts": ["AUMが小さい"],
                        "expense_label": "中コスト",
                        "aum_label": "小型",
                    },
                },
            }
        ]
        result = _compute_judgment(before, after, proposed_health)
        reasons_text = " ".join(result["reasons"])
        assert "ETF注意" in reasons_text
        assert "AUMが小さい" in reasons_text

    def test_judgment_no_etf_unchanged(self):
        """Stock-only portfolio should not have ETF reasons."""
        before, after = _base_before_after()
        proposed_health = [
            {
                "symbol": "7203.T",
                "alert": {"level": "none", "label": "なし"},
                "change_quality": {"is_etf": False},
            }
        ]
        result = _compute_judgment(before, after, proposed_health)
        reasons_text = " ".join(result["reasons"])
        assert "ETF" not in reasons_text

    def test_judgment_etf_medium_quality_no_flag(self):
        """Medium quality ETF (40 <= score < 75) should not add quality label."""
        before, after = _base_before_after()
        proposed_health = [
            {
                "symbol": "MED_ETF",
                "alert": {"level": "none", "label": "なし"},
                "change_quality": {
                    "is_etf": True,
                    "etf_health": {
                        "score": 55,
                        "alerts": [],
                        "expense_label": "中コスト",
                        "aum_label": "中型",
                    },
                },
            }
        ]
        result = _compute_judgment(before, after, proposed_health)
        reasons_text = " ".join(result["reasons"])
        assert "ETF品質良好" not in reasons_text
        assert "ETF品質低" not in reasons_text
