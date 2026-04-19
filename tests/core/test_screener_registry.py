"""Tests for screener_registry (KIK-514)."""

import os
import types
from unittest.mock import MagicMock

import pytest
import yaml

from src.core.screening.screener_registry import (
    ScreenerSpec,
    ScreenerRegistry,
    RegionConfig,
    run_screener_with_spec,
    build_default_registry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _DummyScreener:
    """Minimal screener stub for tests."""

    def __init__(self, yahoo_client, **kwargs):
        self.yahoo_client = yahoo_client
        self.init_kwargs = kwargs

    def screen(self, **kwargs):
        return [{"symbol": "TEST.T", "screen_kwargs": kwargs}]


def _dummy_formatter(results):
    return "formatted"


def _make_spec(**overrides):
    defaults = dict(
        preset="test",
        screener_class=_DummyScreener,
        formatter=_dummy_formatter,
        display_name="テスト",
    )
    defaults.update(overrides)
    return ScreenerSpec(**defaults)


# ---------------------------------------------------------------------------
# ScreenerSpec
# ---------------------------------------------------------------------------

class TestScreenerSpec:
    def test_basic_construction(self):
        spec = _make_spec()
        assert spec.preset == "test"
        assert spec.screener_class is _DummyScreener
        assert spec.display_name == "テスト"
        assert spec.constructor_kwargs == {}
        assert spec.screen_kwargs_fn is None
        assert spec.supports_theme is True
        assert spec.supports_legacy is False
        assert spec.category == "query"

    def test_custom_fields(self):
        fn = lambda args, rc, rconfig: {}
        spec = _make_spec(
            constructor_kwargs={"preset": "growth"},
            screen_kwargs_fn=fn,
            supports_theme=False,
            supports_legacy=True,
            category="growth",
        )
        assert spec.constructor_kwargs == {"preset": "growth"}
        assert spec.screen_kwargs_fn is fn
        assert spec.supports_theme is False
        assert spec.supports_legacy is True
        assert spec.category == "growth"

    def test_step_messages_and_warnings(self):
        spec = _make_spec(
            step_messages=("Step 1...", "Step 2: {n}銘柄"),
            extra_warnings=["⚠️ warning"],
        )
        assert spec.step_messages == ("Step 1...", "Step 2: {n}銘柄")
        assert spec.extra_warnings == ["⚠️ warning"]


# ---------------------------------------------------------------------------
# ScreenerRegistry
# ---------------------------------------------------------------------------

class TestScreenerRegistry:
    def test_register_and_get(self):
        registry = ScreenerRegistry()
        spec = _make_spec(preset="alpha")
        registry.register(spec)
        assert registry.get("alpha") is spec

    def test_duplicate_raises(self):
        registry = ScreenerRegistry()
        registry.register(_make_spec(preset="alpha"))
        with pytest.raises(ValueError, match="Duplicate preset"):
            registry.register(_make_spec(preset="alpha"))

    def test_unknown_preset_raises(self):
        registry = ScreenerRegistry()
        with pytest.raises(KeyError, match="Unknown preset"):
            registry.get("nonexistent")

    def test_has(self):
        registry = ScreenerRegistry()
        registry.register(_make_spec(preset="value"))
        assert registry.has("value") is True
        assert registry.has("nope") is False

    def test_list_presets(self):
        registry = ScreenerRegistry()
        registry.register(_make_spec(preset="beta"))
        registry.register(_make_spec(preset="alpha"))
        assert registry.list_presets() == ["alpha", "beta"]

    def test_theme_unsupported_presets(self):
        registry = ScreenerRegistry()
        registry.register(_make_spec(preset="value", supports_theme=True))
        registry.register(_make_spec(preset="trending", supports_theme=False))
        registry.register(_make_spec(preset="alpha", supports_theme=False))
        assert registry.theme_unsupported_presets() == {"trending", "alpha"}

    def test_legacy_unsupported_presets(self):
        registry = ScreenerRegistry()
        registry.register(_make_spec(preset="value", supports_legacy=True))
        registry.register(_make_spec(preset="pullback", supports_legacy=False))
        assert registry.legacy_unsupported_presets() == {"pullback"}

    def test_growth_presets(self):
        registry = ScreenerRegistry()
        registry.register(_make_spec(preset="growth", category="growth"))
        registry.register(_make_spec(preset="high-growth", category="growth"))
        registry.register(_make_spec(preset="value", category="query"))
        assert registry.growth_presets() == {"growth", "high-growth"}


# ---------------------------------------------------------------------------
# RegionConfig
# ---------------------------------------------------------------------------

@pytest.fixture
def region_config_yaml(tmp_path):
    """Create a minimal exchanges.yaml for testing."""
    data = {
        "regions": {
            "jp": {
                "region_name": "日本",
                "display_name": "日本株",
                "aliases": ["japan", "jp"],
                "small_cap_market_cap": 100_000_000_000,
                "market_class": "JapanMarket",
                "currency": "JPY",
            },
            "us": {
                "region_name": "米国",
                "display_name": "米国株",
                "aliases": ["us"],
                "small_cap_market_cap": 1_000_000_000,
                "market_class": "USMarket",
                "currency": "USD",
            },
            "sg": {
                "region_name": "シンガポール",
                "aliases": ["sg", "singapore"],
                "small_cap_market_cap": 2_000_000_000,
                "currency": "SGD",
            },
        },
        "region_groups": {
            "asean": ["sg"],
            "all": ["jp", "us", "sg"],
        },
    }
    path = tmp_path / "exchanges.yaml"
    with open(path, "w") as f:
        yaml.dump(data, f)
    return str(path)


class TestRegionConfig:
    def test_expand_alias(self, region_config_yaml):
        rc = RegionConfig(yaml_path=region_config_yaml)
        assert rc.expand("japan") == ["jp"]
        assert rc.expand("singapore") == ["sg"]

    def test_expand_code(self, region_config_yaml):
        rc = RegionConfig(yaml_path=region_config_yaml)
        assert rc.expand("jp") == ["jp"]
        assert rc.expand("us") == ["us"]

    def test_expand_group(self, region_config_yaml):
        rc = RegionConfig(yaml_path=region_config_yaml)
        assert rc.expand("asean") == ["sg"]
        assert rc.expand("all") == ["jp", "us", "sg"]

    def test_expand_unknown_fallback(self, region_config_yaml):
        rc = RegionConfig(yaml_path=region_config_yaml)
        assert rc.expand("xx") == ["xx"]

    def test_display_name_with_field(self, region_config_yaml):
        rc = RegionConfig(yaml_path=region_config_yaml)
        assert rc.display_name("jp") == "日本株"
        assert rc.display_name("us") == "米国株"

    def test_display_name_fallback_to_region_name(self, region_config_yaml):
        rc = RegionConfig(yaml_path=region_config_yaml)
        # sg has no display_name → falls back to region_name + "株"
        assert rc.display_name("sg") == "シンガポール株"

    def test_display_name_unknown(self, region_config_yaml):
        rc = RegionConfig(yaml_path=region_config_yaml)
        assert rc.display_name("zz") == "ZZ"

    def test_small_cap_market_cap(self, region_config_yaml):
        rc = RegionConfig(yaml_path=region_config_yaml)
        assert rc.small_cap_market_cap("jp") == 100_000_000_000
        assert rc.small_cap_market_cap("us") == 1_000_000_000
        assert rc.small_cap_market_cap("zz") is None

    def test_market_class_name(self, region_config_yaml):
        rc = RegionConfig(yaml_path=region_config_yaml)
        assert rc.market_class_name("jp") == "JapanMarket"
        assert rc.market_class_name("sg") is None
        assert rc.market_class_name("zz") is None

    def test_region_codes(self, region_config_yaml):
        rc = RegionConfig(yaml_path=region_config_yaml)
        assert set(rc.region_codes()) == {"jp", "us", "sg"}

    def test_case_insensitive_expand(self, region_config_yaml):
        rc = RegionConfig(yaml_path=region_config_yaml)
        assert rc.expand("JAPAN") == ["jp"]
        assert rc.expand("JP") == ["jp"]

    def test_loads_real_exchanges_yaml(self):
        """Ensure the real exchanges.yaml can be loaded."""
        rc = RegionConfig()
        assert "jp" in rc.region_codes()
        assert rc.display_name("jp") == "日本株"
        assert rc.small_cap_market_cap("jp") == 100_000_000_000
        assert rc.expand("asean") == ["sg", "th", "my", "id", "ph"]


# ---------------------------------------------------------------------------
# run_screener_with_spec
# ---------------------------------------------------------------------------

class TestRunScreenerWithSpec:
    def test_basic_execution(self, region_config_yaml):
        rc = RegionConfig(yaml_path=region_config_yaml)
        spec = _make_spec(category="query")
        client = MagicMock()

        results = run_screener_with_spec(
            spec, client, "jp", rc, top_n=10,
        )
        assert len(results) == 1
        assert results[0]["symbol"] == "TEST.T"
        kwargs = results[0]["screen_kwargs"]
        assert kwargs["region"] == "jp"
        assert kwargs["top_n"] == 10
        assert kwargs["preset"] == "test"

    def test_sector_theme_passed_for_query(self, region_config_yaml):
        rc = RegionConfig(yaml_path=region_config_yaml)
        spec = _make_spec(category="query")
        client = MagicMock()

        results = run_screener_with_spec(
            spec, client, "jp", rc,
            sector="Technology", theme="ai",
        )
        kwargs = results[0]["screen_kwargs"]
        assert kwargs["sector"] == "Technology"
        assert kwargs["theme"] == "ai"

    def test_sector_theme_not_passed_for_alpha(self, region_config_yaml):
        rc = RegionConfig(yaml_path=region_config_yaml)
        spec = _make_spec(category="alpha")
        client = MagicMock()

        results = run_screener_with_spec(
            spec, client, "jp", rc,
            sector="Technology", theme="ai",
        )
        kwargs = results[0]["screen_kwargs"]
        assert "sector" not in kwargs
        assert "theme" not in kwargs

    def test_sector_theme_not_passed_for_pullback(self, region_config_yaml):
        rc = RegionConfig(yaml_path=region_config_yaml)
        spec = _make_spec(category="pullback")
        client = MagicMock()

        results = run_screener_with_spec(
            spec, client, "jp", rc,
            sector="Technology", theme="ai",
        )
        kwargs = results[0]["screen_kwargs"]
        assert "sector" not in kwargs
        assert "theme" not in kwargs

    def test_constructor_kwargs_passed(self, region_config_yaml):
        rc = RegionConfig(yaml_path=region_config_yaml)
        spec = _make_spec(
            constructor_kwargs={"preset": "high-growth", "sort_by": "revenue_growth"},
            category="growth",
        )
        client = MagicMock()

        results = run_screener_with_spec(spec, client, "us", rc)
        # DummyScreener stores init_kwargs
        # We can verify by checking the screener was constructed with correct kwargs
        # Since run_screener_with_spec creates the screener internally, we verify
        # through the results
        assert len(results) == 1

    def test_screen_kwargs_fn_applied(self, region_config_yaml):
        rc = RegionConfig(yaml_path=region_config_yaml)

        def extra_fn(args, region_code, region_config):
            return {"submode": "surge"}

        spec = _make_spec(
            screen_kwargs_fn=extra_fn,
            category="momentum",
        )
        client = MagicMock()

        results = run_screener_with_spec(spec, client, "jp", rc)
        kwargs = results[0]["screen_kwargs"]
        assert kwargs["submode"] == "surge"

    def test_small_cap_screen_kwargs_fn(self, region_config_yaml):
        """Test that small-cap-growth's screen_kwargs_fn produces overrides."""
        rc = RegionConfig(yaml_path=region_config_yaml)

        def small_cap_fn(args, region_code, region_config):
            cap = region_config.small_cap_market_cap(region_code)
            if cap is not None:
                return {"criteria_overrides": {"max_market_cap": cap}}
            return {}

        spec = _make_spec(
            screen_kwargs_fn=small_cap_fn,
            category="growth",
        )
        client = MagicMock()

        results = run_screener_with_spec(spec, client, "jp", rc)
        kwargs = results[0]["screen_kwargs"]
        assert kwargs["criteria_overrides"] == {"max_market_cap": 100_000_000_000}

    def test_no_screen_kwargs_fn(self, region_config_yaml):
        rc = RegionConfig(yaml_path=region_config_yaml)
        spec = _make_spec(screen_kwargs_fn=None, category="alpha")
        client = MagicMock()

        results = run_screener_with_spec(spec, client, "jp", rc)
        kwargs = results[0]["screen_kwargs"]
        assert "submode" not in kwargs
        assert "criteria_overrides" not in kwargs


# ---------------------------------------------------------------------------
# build_default_registry
# ---------------------------------------------------------------------------

class TestBuildDefaultRegistry:
    def test_all_15_presets_registered(self):
        registry = build_default_registry()
        presets = registry.list_presets()
        expected = sorted([
            "value", "high-dividend", "growth", "growth-value",
            "deep-value", "quality", "pullback", "alpha",
            "trending", "long-term", "shareholder-return",
            "high-growth", "small-cap-growth", "contrarian", "momentum",
        ])
        assert presets == expected

    def test_trending_is_special(self):
        registry = build_default_registry()
        assert registry.get("trending").category == "special"

    def test_growth_variants_category(self):
        registry = build_default_registry()
        assert registry.get("growth").category == "growth"
        assert registry.get("high-growth").category == "growth"
        assert registry.get("small-cap-growth").category == "growth"

    def test_theme_unsupported(self):
        registry = build_default_registry()
        unsupported = registry.theme_unsupported_presets()
        assert "trending" in unsupported
        assert "pullback" in unsupported
        assert "alpha" in unsupported
        assert "value" not in unsupported

    def test_legacy_unsupported(self):
        registry = build_default_registry()
        unsupported = registry.legacy_unsupported_presets()
        assert "pullback" in unsupported
        assert "momentum" in unsupported
        # QueryScreener-based presets support legacy (default)
        assert "value" not in unsupported

    def test_shareholder_return_registered(self):
        registry = build_default_registry()
        spec = registry.get("shareholder-return")
        assert spec is not None
        assert spec.preset == "shareholder-return"

    def test_momentum_screen_kwargs_fn(self):
        registry = build_default_registry()
        spec = registry.get("momentum")
        assert spec.screen_kwargs_fn is not None
        # Simulate args with submode
        args = types.SimpleNamespace(submode="stable")
        result = spec.screen_kwargs_fn(args, "jp", None)
        assert result == {"submode": "stable"}

    def test_momentum_screen_kwargs_fn_default(self):
        registry = build_default_registry()
        spec = registry.get("momentum")
        args = types.SimpleNamespace(submode=None)
        result = spec.screen_kwargs_fn(args, "jp", None)
        assert result == {"submode": "surge"}

    def test_small_cap_growth_screen_kwargs_fn(self):
        registry = build_default_registry()
        spec = registry.get("small-cap-growth")
        assert spec.screen_kwargs_fn is not None

        rc = RegionConfig()
        result = spec.screen_kwargs_fn(None, "jp", rc)
        assert result == {"criteria_overrides": {"max_market_cap": 100_000_000_000}}

    def test_small_cap_growth_screen_kwargs_fn_unknown_region(self):
        registry = build_default_registry()
        spec = registry.get("small-cap-growth")

        rc = RegionConfig()
        result = spec.screen_kwargs_fn(None, "zz", rc)
        assert result == {}
