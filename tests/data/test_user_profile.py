"""Tests for src/data/user_profile.py (KIK-599)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.data import user_profile


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset the module-level cache before each test."""
    user_profile.reset_cache()
    yield
    user_profile.reset_cache()


# ---------------------------------------------------------------------------
# get_profile: defaults when no file exists
# ---------------------------------------------------------------------------

class TestGetProfileDefaults:
    """get_profile() returns defaults when both YAML files are missing."""

    def test_returns_dict(self, monkeypatch, tmp_path):
        """Should return a dict with broker/fees/tax keys."""
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", tmp_path / "nope.yaml")
        monkeypatch.setattr(user_profile, "_DEFAULT_PATH", tmp_path / "nope2.yaml")

        profile = user_profile.get_profile()
        assert isinstance(profile, dict)
        assert "broker" in profile
        assert "fees" in profile
        assert "tax" in profile

    def test_default_broker(self, monkeypatch, tmp_path):
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", tmp_path / "nope.yaml")
        monkeypatch.setattr(user_profile, "_DEFAULT_PATH", tmp_path / "nope2.yaml")

        profile = user_profile.get_profile()
        assert profile["broker"]["name"] == "不明"
        assert profile["broker"]["account_type"] == "一般口座"

    def test_default_us_fee(self, monkeypatch, tmp_path):
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", tmp_path / "nope.yaml")
        monkeypatch.setattr(user_profile, "_DEFAULT_PATH", tmp_path / "nope2.yaml")

        profile = user_profile.get_profile()
        assert profile["fees"]["us_stock"]["rate"] == 0.00495

    def test_default_tax_rate(self, monkeypatch, tmp_path):
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", tmp_path / "nope.yaml")
        monkeypatch.setattr(user_profile, "_DEFAULT_PATH", tmp_path / "nope2.yaml")

        profile = user_profile.get_profile()
        assert profile["tax"]["capital_gains_rate"] == 0.20315


# ---------------------------------------------------------------------------
# get_profile: reads YAML correctly
# ---------------------------------------------------------------------------

class TestGetProfileFromYAML:
    """get_profile() reads user_profile.yaml when present."""

    def test_reads_custom_yaml(self, monkeypatch, tmp_path):
        yaml_content = textwrap.dedent("""\
            broker:
              name: SBI証券
              account_type: 特定口座源泉あり
            fees:
              us_stock:
                rate: 0.00495
                min_usd: 0
                max_usd: 22
                sec_fee: 0.0000206
              jp_stock:
                rate: 0
              asean_stock:
                rate: 0.011
              fx:
                realtime_spread: 0
                scheduled_spread: 0
            tax:
              capital_gains_rate: 0.20315
              needs_filing: false
              realized_losses_ytd: 50000
        """)
        yaml_file = tmp_path / "user_profile.yaml"
        yaml_file.write_text(yaml_content)

        monkeypatch.setattr(user_profile, "_PROFILE_PATH", yaml_file)

        profile = user_profile.get_profile()
        assert profile["broker"]["name"] == "SBI証券"
        assert profile["broker"]["account_type"] == "特定口座源泉あり"
        assert profile["tax"]["needs_filing"] is False
        assert profile["tax"]["realized_losses_ytd"] == 50000

    def test_falls_back_to_example(self, monkeypatch, tmp_path):
        """When user_profile.yaml is missing, falls back to .example."""
        example_content = textwrap.dedent("""\
            broker:
              name: 楽天証券
              account_type: 一般口座
            fees:
              us_stock:
                rate: 0.00495
                min_usd: 0
                max_usd: 22
                sec_fee: 0.0000206
              jp_stock:
                rate: 0
              asean_stock:
                rate: 0.011
              fx:
                realtime_spread: 0
                scheduled_spread: 0
            tax:
              capital_gains_rate: 0.20315
              needs_filing: true
              realized_losses_ytd: 0
        """)
        example_file = tmp_path / "user_profile.yaml.example"
        example_file.write_text(example_content)

        monkeypatch.setattr(user_profile, "_PROFILE_PATH", tmp_path / "missing.yaml")
        monkeypatch.setattr(user_profile, "_DEFAULT_PATH", example_file)

        profile = user_profile.get_profile()
        assert profile["broker"]["name"] == "楽天証券"

    def test_empty_yaml_returns_defaults(self, monkeypatch, tmp_path):
        """Empty YAML file should return defaults."""
        yaml_file = tmp_path / "user_profile.yaml"
        yaml_file.write_text("")

        monkeypatch.setattr(user_profile, "_PROFILE_PATH", yaml_file)

        profile = user_profile.get_profile()
        assert profile["broker"]["name"] == "不明"


# ---------------------------------------------------------------------------
# get_fee
# ---------------------------------------------------------------------------

class TestGetFee:
    """get_fee() correctly calculates trading fees."""

    def test_us_stock_fee(self, monkeypatch, tmp_path):
        """US stock: 1245.10 * 0.00495 = 6.1632, clamped to [0, 22]."""
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", tmp_path / "nope.yaml")
        monkeypatch.setattr(user_profile, "_DEFAULT_PATH", tmp_path / "nope2.yaml")

        result = user_profile.get_fee("us", 1245.10)
        assert result["rate"] == 0.00495
        assert result["fee"] == round(1245.10 * 0.00495, 4)
        assert "sec_fee" not in result
        assert result["total"] == result["fee"]

    def test_us_stock_sell_with_sec_fee(self, monkeypatch, tmp_path):
        """Sell includes SEC fee."""
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", tmp_path / "nope.yaml")
        monkeypatch.setattr(user_profile, "_DEFAULT_PATH", tmp_path / "nope2.yaml")

        result = user_profile.get_fee("us", 1245.10, is_sell=True)
        expected_fee = round(1245.10 * 0.00495, 4)
        expected_sec = round(1245.10 * 0.0000206, 4)
        assert result["fee"] == expected_fee
        assert result["sec_fee"] == expected_sec
        assert result["total"] == round(expected_fee + expected_sec, 4)

    def test_us_stock_max_fee_cap(self, monkeypatch, tmp_path):
        """Large US trade should cap fee at $22."""
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", tmp_path / "nope.yaml")
        monkeypatch.setattr(user_profile, "_DEFAULT_PATH", tmp_path / "nope2.yaml")

        # 10000 * 0.00495 = 49.5 → capped at 22
        result = user_profile.get_fee("us", 10000)
        assert result["fee"] == 22

    def test_us_stock_min_fee(self, monkeypatch, tmp_path):
        """Very small US trade should use min fee (0)."""
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", tmp_path / "nope.yaml")
        monkeypatch.setattr(user_profile, "_DEFAULT_PATH", tmp_path / "nope2.yaml")

        result = user_profile.get_fee("us", 0)
        assert result["fee"] == 0

    def test_japan_stock_zero_fee(self, monkeypatch, tmp_path):
        """Japan stock with zero-cost course should be 0."""
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", tmp_path / "nope.yaml")
        monkeypatch.setattr(user_profile, "_DEFAULT_PATH", tmp_path / "nope2.yaml")

        result = user_profile.get_fee("japan", 500000)
        assert result["fee"] == 0
        assert result["rate"] == 0
        assert result["total"] == 0

    def test_jp_alias(self, monkeypatch, tmp_path):
        """'jp' should map to jp_stock."""
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", tmp_path / "nope.yaml")
        monkeypatch.setattr(user_profile, "_DEFAULT_PATH", tmp_path / "nope2.yaml")

        result = user_profile.get_fee("jp", 500000)
        assert result["fee"] == 0

    def test_asean_stock_fee(self, monkeypatch, tmp_path):
        """ASEAN stock: 5000 * 0.011 = 55."""
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", tmp_path / "nope.yaml")
        monkeypatch.setattr(user_profile, "_DEFAULT_PATH", tmp_path / "nope2.yaml")

        result = user_profile.get_fee("sg", 5000)
        assert result["rate"] == 0.011
        assert result["fee"] == round(5000 * 0.011, 4)

    def test_hk_maps_to_asean(self, monkeypatch, tmp_path):
        """HK should map to asean_stock fees."""
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", tmp_path / "nope.yaml")
        monkeypatch.setattr(user_profile, "_DEFAULT_PATH", tmp_path / "nope2.yaml")

        result = user_profile.get_fee("hk", 10000)
        assert result["rate"] == 0.011

    def test_unknown_region_falls_back_to_us(self, monkeypatch, tmp_path):
        """Unknown region should default to us_stock fees."""
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", tmp_path / "nope.yaml")
        monkeypatch.setattr(user_profile, "_DEFAULT_PATH", tmp_path / "nope2.yaml")

        result = user_profile.get_fee("unknown_region", 1000)
        assert result["rate"] == 0.00495


# ---------------------------------------------------------------------------
# get_tax_cost
# ---------------------------------------------------------------------------

class TestGetTaxCost:
    """get_tax_cost() correctly calculates capital gains tax."""

    def test_basic_tax(self, monkeypatch, tmp_path):
        """33396 JPY gain → tax = round(33396 * 0.20315) = 6785."""
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", tmp_path / "nope.yaml")
        monkeypatch.setattr(user_profile, "_DEFAULT_PATH", tmp_path / "nope2.yaml")

        result = user_profile.get_tax_cost(33396)
        assert result["rate"] == 0.20315
        assert result["tax"] == round(33396 * 0.20315)
        assert result["taxable_gain"] == 33396
        assert result["offset_applied"] == 0
        assert result["net_gain"] == round(33396 - result["tax"])
        assert result["needs_filing"] is True

    def test_loss_offset(self, monkeypatch, tmp_path):
        """With YTD losses, taxable gain should be reduced."""
        yaml_content = textwrap.dedent("""\
            broker:
              name: 楽天証券
              account_type: 一般口座
            fees:
              us_stock:
                rate: 0.00495
                min_usd: 0
                max_usd: 22
                sec_fee: 0.0000206
              jp_stock:
                rate: 0
              asean_stock:
                rate: 0.011
              fx:
                realtime_spread: 0
                scheduled_spread: 0
            tax:
              capital_gains_rate: 0.20315
              needs_filing: true
              realized_losses_ytd: 10000
        """)
        yaml_file = tmp_path / "user_profile.yaml"
        yaml_file.write_text(yaml_content)
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", yaml_file)

        result = user_profile.get_tax_cost(33396)
        # taxable_gain = max(0, 33396 - 10000) = 23396
        assert result["taxable_gain"] == 23396
        assert result["offset_applied"] == 10000
        assert result["tax"] == round(23396 * 0.20315)

    def test_losses_exceed_gain(self, monkeypatch, tmp_path):
        """When losses exceed gain, tax should be 0."""
        yaml_content = textwrap.dedent("""\
            broker:
              name: 楽天証券
              account_type: 一般口座
            fees:
              us_stock:
                rate: 0.00495
                min_usd: 0
                max_usd: 22
                sec_fee: 0.0000206
              jp_stock:
                rate: 0
              asean_stock:
                rate: 0.011
              fx:
                realtime_spread: 0
                scheduled_spread: 0
            tax:
              capital_gains_rate: 0.20315
              needs_filing: true
              realized_losses_ytd: 50000
        """)
        yaml_file = tmp_path / "user_profile.yaml"
        yaml_file.write_text(yaml_content)
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", yaml_file)

        result = user_profile.get_tax_cost(10000)
        assert result["taxable_gain"] == 0
        assert result["tax"] == 0
        assert result["offset_applied"] == 10000
        assert result["net_gain"] == 10000

    def test_zero_gain(self, monkeypatch, tmp_path):
        """Zero gain should produce zero tax."""
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", tmp_path / "nope.yaml")
        monkeypatch.setattr(user_profile, "_DEFAULT_PATH", tmp_path / "nope2.yaml")

        result = user_profile.get_tax_cost(0)
        assert result["tax"] == 0
        assert result["net_gain"] == 0


# ---------------------------------------------------------------------------
# needs_tax_filing
# ---------------------------------------------------------------------------

class TestNeedsTaxFiling:
    """needs_tax_filing() returns correct boolean."""

    def test_default_true(self, monkeypatch, tmp_path):
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", tmp_path / "nope.yaml")
        monkeypatch.setattr(user_profile, "_DEFAULT_PATH", tmp_path / "nope2.yaml")

        assert user_profile.needs_tax_filing() is True

    def test_tokutei_account_false(self, monkeypatch, tmp_path):
        yaml_content = textwrap.dedent("""\
            broker:
              name: SBI証券
              account_type: 特定口座源泉あり
            fees:
              us_stock:
                rate: 0.00495
                min_usd: 0
                max_usd: 22
                sec_fee: 0.0000206
              jp_stock:
                rate: 0
              asean_stock:
                rate: 0.011
              fx:
                realtime_spread: 0
                scheduled_spread: 0
            tax:
              capital_gains_rate: 0.20315
              needs_filing: false
              realized_losses_ytd: 0
        """)
        yaml_file = tmp_path / "user_profile.yaml"
        yaml_file.write_text(yaml_content)
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", yaml_file)

        assert user_profile.needs_tax_filing() is False


# ---------------------------------------------------------------------------
# get_broker_info
# ---------------------------------------------------------------------------

class TestGetBrokerInfo:
    """get_broker_info() returns broker dict."""

    def test_default_broker(self, monkeypatch, tmp_path):
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", tmp_path / "nope.yaml")
        monkeypatch.setattr(user_profile, "_DEFAULT_PATH", tmp_path / "nope2.yaml")

        info = user_profile.get_broker_info()
        assert info["name"] == "不明"
        assert info["account_type"] == "一般口座"

    def test_custom_broker(self, monkeypatch, tmp_path):
        yaml_content = textwrap.dedent("""\
            broker:
              name: マネックス証券
              account_type: NISA
            fees:
              us_stock:
                rate: 0
                min_usd: 0
                max_usd: 0
                sec_fee: 0
              jp_stock:
                rate: 0
              asean_stock:
                rate: 0
              fx:
                realtime_spread: 0
                scheduled_spread: 0
            tax:
              capital_gains_rate: 0
              needs_filing: false
              realized_losses_ytd: 0
        """)
        yaml_file = tmp_path / "user_profile.yaml"
        yaml_file.write_text(yaml_content)
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", yaml_file)

        info = user_profile.get_broker_info()
        assert info["name"] == "マネックス証券"
        assert info["account_type"] == "NISA"


# ---------------------------------------------------------------------------
# get_screening_regions
# ---------------------------------------------------------------------------

class TestGetScreeningRegions:
    """get_screening_regions() returns preferred/excluded region lists."""

    def test_get_screening_regions_defaults(self, monkeypatch, tmp_path):
        """Default should return empty lists for both keys."""
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", tmp_path / "nope.yaml")
        monkeypatch.setattr(user_profile, "_DEFAULT_PATH", tmp_path / "nope2.yaml")

        result = user_profile.get_screening_regions()
        assert result == {"preferred": [], "excluded": []}

    def test_get_screening_regions_custom(self, monkeypatch, tmp_path):
        """Should read screening config from YAML."""
        yaml_content = textwrap.dedent("""\
            broker:
              name: 楽天証券
              account_type: 一般口座
            fees:
              us_stock:
                rate: 0.00495
                min_usd: 0
                max_usd: 22
                sec_fee: 0.0000206
              jp_stock:
                rate: 0
              asean_stock:
                rate: 0.011
              fx:
                realtime_spread: 0
                scheduled_spread: 0
            tax:
              capital_gains_rate: 0.20315
              needs_filing: true
              realized_losses_ytd: 0
            screening:
              excluded_regions: [kr, tw, europe, uk]
              preferred_regions: [japan, us, sg, hk, id]
        """)
        yaml_file = tmp_path / "user_profile.yaml"
        yaml_file.write_text(yaml_content)
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", yaml_file)

        result = user_profile.get_screening_regions()
        assert result["preferred"] == ["japan", "us", "sg", "hk", "id"]
        assert result["excluded"] == ["kr", "tw", "europe", "uk"]

    def test_get_screening_regions_preferred(self, monkeypatch, tmp_path):
        """Should return preferred_regions correctly when only preferred is set."""
        yaml_content = textwrap.dedent("""\
            broker:
              name: 楽天証券
              account_type: 一般口座
            fees:
              us_stock:
                rate: 0.00495
                min_usd: 0
                max_usd: 22
                sec_fee: 0.0000206
              jp_stock:
                rate: 0
              asean_stock:
                rate: 0.011
              fx:
                realtime_spread: 0
                scheduled_spread: 0
            tax:
              capital_gains_rate: 0.20315
              needs_filing: true
              realized_losses_ytd: 0
            screening:
              preferred_regions: [japan, us]
        """)
        yaml_file = tmp_path / "user_profile.yaml"
        yaml_file.write_text(yaml_content)
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", yaml_file)

        result = user_profile.get_screening_regions()
        assert result["preferred"] == ["japan", "us"]
        assert result["excluded"] == []

    def test_get_screening_regions_excluded(self, monkeypatch, tmp_path):
        """Should return excluded_regions correctly when only excluded is set."""
        yaml_content = textwrap.dedent("""\
            broker:
              name: 楽天証券
              account_type: 一般口座
            fees:
              us_stock:
                rate: 0.00495
                min_usd: 0
                max_usd: 22
                sec_fee: 0.0000206
              jp_stock:
                rate: 0
              asean_stock:
                rate: 0.011
              fx:
                realtime_spread: 0
                scheduled_spread: 0
            tax:
              capital_gains_rate: 0.20315
              needs_filing: true
              realized_losses_ytd: 0
            screening:
              excluded_regions: [kr, tw]
        """)
        yaml_file = tmp_path / "user_profile.yaml"
        yaml_file.write_text(yaml_content)
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", yaml_file)

        result = user_profile.get_screening_regions()
        assert result["preferred"] == []
        assert result["excluded"] == ["kr", "tw"]


# ---------------------------------------------------------------------------
# Cache behavior
# ---------------------------------------------------------------------------

class TestCache:
    """Cache is used after first load and cleared by reset_cache()."""

    def test_cache_is_reused(self, monkeypatch, tmp_path):
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", tmp_path / "nope.yaml")
        monkeypatch.setattr(user_profile, "_DEFAULT_PATH", tmp_path / "nope2.yaml")

        p1 = user_profile.get_profile()
        p2 = user_profile.get_profile()
        assert p1 is p2  # Same object = cached

    def test_reset_cache_clears(self, monkeypatch, tmp_path):
        monkeypatch.setattr(user_profile, "_PROFILE_PATH", tmp_path / "nope.yaml")
        monkeypatch.setattr(user_profile, "_DEFAULT_PATH", tmp_path / "nope2.yaml")

        p1 = user_profile.get_profile()
        user_profile.reset_cache()
        p2 = user_profile.get_profile()
        assert p1 is not p2  # Different objects after reset
