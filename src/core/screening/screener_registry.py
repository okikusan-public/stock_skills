"""ScreenerRegistry: Strategy/Factory pattern for screening dispatch (KIK-514).

Eliminates OCP violations in run_screen.py by centralising screener specs,
formatter mappings, and region configuration into a single registry.
"""

import os
from dataclasses import dataclass, field
from typing import Callable, Optional

import yaml


# ---------------------------------------------------------------------------
# ScreenerSpec
# ---------------------------------------------------------------------------

@dataclass
class ScreenerSpec:
    """Specification for a single screening preset.

    Attributes
    ----------
    preset : str
        Preset name (e.g. "alpha", "growth").
    screener_class : type
        Screener class to instantiate.
    formatter : Callable
        Formatter function for results.
    display_name : str
        Japanese display name (e.g. "アルファシグナル").
    constructor_kwargs : dict
        Extra kwargs for screener constructor (beyond yahoo_client).
    screen_kwargs_fn : Callable | None
        ``(args) -> dict`` producing extra kwargs for ``.screen()``.
        Use for momentum submode, small-cap overrides, etc.
    supports_theme : bool
        Whether ``--theme`` is supported.
    supports_legacy : bool
        If False, legacy mode auto-switches to query mode.
    category : str
        Dispatch category: "query" (QueryScreener-based), "growth",
        "pullback", "alpha", "contrarian", "momentum", "special" (trending).
    step_messages : tuple[str, str]
        (step1_msg, step2_template) for progress output.
        step2_template uses ``{n}`` for result count.
    extra_warnings : list[str]
        Warning messages to print after results (e.g. small-cap liquidity).
    """

    preset: str
    screener_class: type
    formatter: Callable
    display_name: str
    constructor_kwargs: dict = field(default_factory=dict)
    screen_kwargs_fn: Optional[Callable] = None
    supports_theme: bool = True
    supports_legacy: bool = False
    category: str = "query"
    step_messages: tuple = ("", "")
    extra_warnings: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# ScreenerRegistry
# ---------------------------------------------------------------------------

class ScreenerRegistry:
    """Registry of screener specs, keyed by preset name."""

    def __init__(self):
        self._specs: dict[str, ScreenerSpec] = {}

    def register(self, spec: ScreenerSpec) -> None:
        """Register a screener spec.  Raises ValueError on duplicate."""
        if spec.preset in self._specs:
            raise ValueError(f"Duplicate preset: {spec.preset}")
        self._specs[spec.preset] = spec

    def get(self, preset: str) -> ScreenerSpec:
        """Return spec for *preset*.  Raises KeyError if not found."""
        if preset not in self._specs:
            raise KeyError(f"Unknown preset: {preset}")
        return self._specs[preset]

    def has(self, preset: str) -> bool:
        """Return True if *preset* is registered."""
        return preset in self._specs

    def list_presets(self) -> list[str]:
        """Return sorted list of registered preset names."""
        return sorted(self._specs)

    def theme_unsupported_presets(self) -> set[str]:
        """Return set of preset names that do not support --theme."""
        return {k for k, v in self._specs.items() if not v.supports_theme}

    def legacy_unsupported_presets(self) -> set[str]:
        """Return set of preset names that do not support legacy mode."""
        return {k for k, v in self._specs.items() if not v.supports_legacy}

    def growth_presets(self) -> set[str]:
        """Return set of presets in the 'growth' category."""
        return {k for k, v in self._specs.items() if v.category == "growth"}


# ---------------------------------------------------------------------------
# RegionConfig
# ---------------------------------------------------------------------------

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class RegionConfig:
    """Region configuration loaded from exchanges.yaml.

    Consolidates REGION_EXPAND, REGION_NAMES, _SMALL_CAP_MARKET_CAP
    and MARKETS into a single source of truth.
    """

    def __init__(self, yaml_path: Optional[str] = None):
        if yaml_path is None:
            yaml_path = os.path.join(_ROOT, "config", "exchanges.yaml")
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        self._regions: dict = data.get("regions", {})
        self._groups: dict = data.get("region_groups", {})

        # Build alias → [region_codes] mapping
        self._alias_map: dict[str, list[str]] = {}
        for code, info in self._regions.items():
            # Each region code maps to itself
            self._alias_map[code] = [code]
            for alias in info.get("aliases", []):
                self._alias_map[alias] = [code]

        # Add group expansions
        for group_name, codes in self._groups.items():
            self._alias_map[group_name] = list(codes)

    def expand(self, region: str) -> list[str]:
        """Expand a user-facing region name to a list of region codes.

        Falls back to treating the input as a raw region code.
        """
        return self._alias_map.get(region.lower(), [region.lower()])

    def display_name(self, code: str) -> str:
        """Return display name (e.g. "日本株") for a region code."""
        info = self._regions.get(code)
        if info is None:
            return code.upper()
        return info.get("display_name", info.get("region_name", code.upper()) + "株")

    def small_cap_market_cap(self, code: str) -> Optional[int]:
        """Return small-cap market cap threshold for a region code, or None."""
        info = self._regions.get(code)
        if info is None:
            return None
        return info.get("small_cap_market_cap")

    def market_class_name(self, code: str) -> Optional[str]:
        """Return market class name string (e.g. 'JapanMarket') for a region code."""
        info = self._regions.get(code)
        if info is None:
            return None
        return info.get("market_class")

    def region_codes(self) -> list[str]:
        """Return all known region codes."""
        return list(self._regions.keys())


# ---------------------------------------------------------------------------
# Unified screening execution
# ---------------------------------------------------------------------------

def run_screener_with_spec(
    spec: ScreenerSpec,
    yahoo_client,
    region_code: str,
    region_config: RegionConfig,
    *,
    top_n: int = 20,
    sector: Optional[str] = None,
    theme: Optional[str] = None,
    args=None,
) -> list[dict]:
    """Instantiate screener from *spec* and run screening for one region.

    Parameters
    ----------
    spec : ScreenerSpec
        Screener specification.
    yahoo_client : module
        Yahoo client module.
    region_code : str
        Single region code (e.g. "jp").
    region_config : RegionConfig
        Region configuration.
    top_n : int
        Max results.
    sector : str, optional
        Sector filter.
    theme : str, optional
        Theme filter.
    args : argparse.Namespace, optional
        Full CLI args (used by screen_kwargs_fn).

    Returns
    -------
    list[dict]
        Screening results.
    """
    # Instantiate screener
    screener = spec.screener_class(yahoo_client, **spec.constructor_kwargs)

    # Build screen() kwargs
    screen_kwargs: dict = {
        "region": region_code,
        "top_n": top_n,
    }

    # Only pass sector/theme if the screener's screen() accepts them
    # Growth, Contrarian, Momentum accept sector/theme
    # Pullback, Alpha do not
    if spec.category in ("query", "growth", "contrarian", "momentum"):
        if sector is not None:
            screen_kwargs["sector"] = sector
        if theme is not None:
            screen_kwargs["theme"] = theme

    # For query-category screeners (QueryScreener), pass preset
    if spec.category == "query":
        screen_kwargs["preset"] = spec.preset

    # Apply screen_kwargs_fn for preset-specific overrides
    if spec.screen_kwargs_fn is not None:
        extra = spec.screen_kwargs_fn(args, region_code, region_config)
        screen_kwargs.update(extra)

    return screener.screen(**screen_kwargs)


# ---------------------------------------------------------------------------
# Default registry builder
# ---------------------------------------------------------------------------

def build_default_registry() -> ScreenerRegistry:
    """Build the default registry with all 15 presets."""
    # Lazy imports to avoid circular dependencies
    from src.core.screening.screener import (
        QueryScreener, PullbackScreener, AlphaScreener,
        GrowthScreener, ContrarianScreener, MomentumScreener,
        TrendingScreener,
    )
    # Formatter imports are optional — agents format their own output (KIK-651)
    try:
        from src.output.formatter import (
            format_query_markdown, format_pullback_markdown,
            format_alpha_markdown, format_growth_markdown,
            format_contrarian_markdown, format_momentum_markdown,
            format_trending_markdown,
        )
    except ImportError:
        _noop_fmt = None
        format_query_markdown = _noop_fmt
        format_pullback_markdown = _noop_fmt
        format_alpha_markdown = _noop_fmt
        format_growth_markdown = _noop_fmt
        format_contrarian_markdown = _noop_fmt
        format_momentum_markdown = _noop_fmt
        format_trending_markdown = _noop_fmt

    try:
        from src.output.formatter import format_shareholder_return_markdown as _sr_fmt
    except ImportError:
        _sr_fmt = None

    registry = ScreenerRegistry()

    # --- QueryScreener-based presets (all support legacy mode) ---
    for preset, display in [
        ("value", "バリュー"),
        ("high-dividend", "高配当"),
        ("growth-value", "成長バリュー"),
        ("deep-value", "ディープバリュー"),
        ("quality", "クオリティバリュー"),
        ("long-term", "長期投資適性"),
    ]:
        registry.register(ScreenerSpec(
            preset=preset,
            screener_class=QueryScreener,
            formatter=format_query_markdown,
            display_name=display,
            category="query",
            supports_legacy=True,
        ))

    # shareholder-return: use dedicated formatter if available
    registry.register(ScreenerSpec(
        preset="shareholder-return",
        screener_class=QueryScreener,
        formatter=_sr_fmt if _sr_fmt else format_query_markdown,
        display_name="高還元",
        category="query",
        supports_legacy=True,
    ))

    # --- Pullback ---
    registry.register(ScreenerSpec(
        preset="pullback",
        screener_class=PullbackScreener,
        formatter=format_pullback_markdown,
        display_name="押し目買い",
        supports_theme=False,
        supports_legacy=False,
        category="pullback",
        step_messages=(
            "Step 1: ファンダメンタルズ条件で絞り込み中...",
            "Step 2-3 完了: {n}銘柄が条件に合致",
        ),
    ))

    # --- Alpha ---
    registry.register(ScreenerSpec(
        preset="alpha",
        screener_class=AlphaScreener,
        formatter=format_alpha_markdown,
        display_name="アルファシグナル",
        supports_theme=False,
        supports_legacy=False,
        category="alpha",
        step_messages=(
            "Step 1: 割安足切り (EquityQuery)...",
            "Step 2-4 完了: {n}銘柄がアルファ条件に合致",
        ),
    ))

    # --- Growth variants ---
    registry.register(ScreenerSpec(
        preset="growth",
        screener_class=GrowthScreener,
        formatter=format_growth_markdown,
        display_name="純成長株",
        constructor_kwargs={},
        supports_legacy=False,
        category="growth",
        step_messages=(
            "Step 1: 成長条件で絞り込み中 (EquityQuery)...",
            "Step 2: {n}銘柄のEPS成長率を取得・ソート完了",
        ),
    ))

    registry.register(ScreenerSpec(
        preset="high-growth",
        screener_class=GrowthScreener,
        formatter=format_growth_markdown,
        display_name="高成長株",
        constructor_kwargs={
            "preset": "high-growth",
            "sort_by": "revenue_growth",
            "require_positive_eps": False,
        },
        supports_legacy=False,
        category="growth",
        step_messages=(
            "Step 1: 高成長条件で絞り込み中 (EquityQuery, 利益不問)...",
            "Step 2: {n}銘柄の売上成長率を取得・ソート完了",
        ),
    ))

    def _small_cap_screen_kwargs(args, region_code, region_config):
        """Produce criteria_overrides for small-cap-growth."""
        cap = region_config.small_cap_market_cap(region_code)
        if cap is not None:
            return {"criteria_overrides": {"max_market_cap": cap}}
        return {}

    registry.register(ScreenerSpec(
        preset="small-cap-growth",
        screener_class=GrowthScreener,
        formatter=format_growth_markdown,
        display_name="小型急成長株",
        constructor_kwargs={
            "preset": "small-cap-growth",
            "sort_by": "revenue_growth",
            "require_positive_eps": False,
        },
        screen_kwargs_fn=_small_cap_screen_kwargs,
        supports_legacy=False,
        category="growth",
        step_messages=(
            "Step 1: 小型急成長条件で絞り込み中 (EquityQuery, 利益不問)...",
            "Step 2: {n}銘柄の売上成長率を取得・ソート完了",
        ),
        extra_warnings=[
            "⚠️ 小型株は流動性リスクが高く、スプレッドが広い場合があります。売買時は板の厚さを確認してください。",
        ],
    ))

    # --- Contrarian ---
    registry.register(ScreenerSpec(
        preset="contrarian",
        screener_class=ContrarianScreener,
        formatter=format_contrarian_markdown,
        display_name="逆張り候補",
        supports_legacy=False,
        category="contrarian",
        step_messages=(
            "Step 1: バリュー条件で絞り込み中...",
            "Step 2-3 完了: {n}銘柄が逆張り条件に合致",
        ),
    ))

    # --- Momentum ---
    def _momentum_screen_kwargs(args, region_code, region_config):
        """Pass submode to MomentumScreener.screen()."""
        submode = getattr(args, "submode", None) or "surge"
        return {"submode": submode}

    registry.register(ScreenerSpec(
        preset="momentum",
        screener_class=MomentumScreener,
        formatter=format_momentum_markdown,
        display_name="モメンタム",
        supports_legacy=False,
        category="momentum",
        screen_kwargs_fn=_momentum_screen_kwargs,
        step_messages=(
            "Step 1: モメンタム条件で絞り込み中...",
            "Step 2-3 完了: {n}銘柄がモメンタム条件に合致",
        ),
    ))

    # --- Trending (special: uses run_trending_mode) ---
    registry.register(ScreenerSpec(
        preset="trending",
        screener_class=TrendingScreener,
        formatter=format_trending_markdown,
        display_name="Xトレンド銘柄",
        supports_theme=False,
        supports_legacy=False,
        category="special",
    ))

    return registry
