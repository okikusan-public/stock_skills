"""Build yfinance EquityQuery objects from screening criteria dicts."""

from pathlib import Path
from typing import Optional

import yaml
from yfinance import EquityQuery

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent.parent / "config" / "screening_presets.yaml"


def load_preset(preset_name: str) -> dict:
    """Load screening criteria from the presets YAML file.

    Parameters
    ----------
    preset_name : str
        Name of the preset (e.g. 'value', 'alpha', 'growth').

    Returns
    -------
    dict
        Criteria dict ready for use with ``build_query`` or screeners.

    Raises
    ------
    ValueError
        If the preset is not found.
    """
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    presets = config.get("presets", {})
    if preset_name not in presets:
        raise ValueError(f"Unknown preset: '{preset_name}'. Available: {list(presets.keys())}")
    return presets[preset_name].get("criteria", {})


# ---------------------------------------------------------------------------
# Mapping: criteria dict key -> (EquityQuery field, operator)
# ---------------------------------------------------------------------------
# "max_*" criteria use "lt" (less-than) because we want stocks BELOW the max.
# "min_*" criteria use "gt" (greater-than) because we want stocks ABOVE the min.
_CRITERIA_FIELD_MAP: dict[str, tuple[str, str]] = {
    "max_per":              ("peratio.lasttwelvemonths",             "lt"),
    "max_pbr":              ("pricebookratio.quarterly",             "lt"),
    "min_dividend_yield":   ("forward_dividend_yield",               "gt"),
    "min_roe":              ("returnonequity.lasttwelvemonths",      "gt"),
    "min_revenue_growth":   ("totalrevenues1yrgrowth.lasttwelvemonths", "gt"),
    "min_earnings_growth":  ("epsgrowth.lasttwelvemonths",           "gt"),
    "min_market_cap":       ("intradaymarketcap",                    "gt"),
}

# ---------------------------------------------------------------------------
# Region / exchange helpers
# ---------------------------------------------------------------------------
# Market name -> yf.screen region code
REGION_MAP: dict[str, str] = {
    "japan":     "jp",
    "us":        "us",
    "singapore": "sg",
    "thailand":  "th",
    "malaysia":  "my",
    "indonesia": "id",
    "philippines": "ph",
}

# Market name -> yf.screen exchange code(s)
EXCHANGE_MAP: dict[str, list[str]] = {
    "japan":       ["JPX"],
    "us":          ["NMS", "NYQ"],
    "singapore":   ["SES"],
    "thailand":    ["SET"],
    "malaysia":    ["KLS"],
    "indonesia":   ["JKT"],
    "philippines": ["PHS"],
}

# Convenience: "asean" expands to multiple regions
ASEAN_REGIONS = ["sg", "th", "my", "id", "ph"]
ASEAN_EXCHANGES = ["SES", "SET", "KLS", "JKT", "PHS"]


def _build_criteria_conditions(criteria: dict) -> list[EquityQuery]:
    """Convert a criteria dict into a list of EquityQuery leaf conditions.

    Parameters
    ----------
    criteria : dict
        Keys like ``max_per``, ``max_pbr``, ``min_dividend_yield``,
        ``min_roe``, ``min_revenue_growth`` with numeric values.

    Returns
    -------
    list[EquityQuery]
        One EquityQuery per recognised criteria key.
    """
    conditions: list[EquityQuery] = []
    for key, value in criteria.items():
        mapping = _CRITERIA_FIELD_MAP.get(key)
        if mapping is None:
            continue
        field, operator = mapping
        conditions.append(EquityQuery(operator, [field, value]))
    return conditions


def _build_region_condition(region: str) -> Optional[EquityQuery]:
    """Build an EquityQuery condition for region filtering.

    Parameters
    ----------
    region : str
        Market name (e.g. 'japan', 'us', 'asean') or a raw yf region
        code (e.g. 'jp', 'us').

    Returns
    -------
    EquityQuery or None
        Region condition, or None if the region is not recognised.
    """
    region_lower = region.lower()

    # Special case: "asean" -> is-in across multiple regions
    if region_lower == "asean":
        return EquityQuery("is-in", ["region", *ASEAN_REGIONS])

    # Mapped name (e.g. "japan" -> "jp")
    code = REGION_MAP.get(region_lower)
    if code is not None:
        return EquityQuery("eq", ["region", code])

    # Assume it's already a raw region code (2-letter)
    if len(region_lower) <= 3:
        return EquityQuery("eq", ["region", region_lower])

    return None


def _build_exchange_condition(exchange: str) -> Optional[EquityQuery]:
    """Build an EquityQuery condition for exchange filtering.

    Parameters
    ----------
    exchange : str
        Market name (e.g. 'japan') or exchange code (e.g. 'JPX', 'NMS').

    Returns
    -------
    EquityQuery or None
    """
    exchange_key = exchange.lower()

    # Special case: "asean"
    if exchange_key == "asean":
        return EquityQuery("is-in", ["exchange", *ASEAN_EXCHANGES])

    # Mapped name
    codes = EXCHANGE_MAP.get(exchange_key)
    if codes is not None:
        if len(codes) == 1:
            return EquityQuery("eq", ["exchange", codes[0]])
        return EquityQuery("is-in", ["exchange", *codes])

    # Assume raw exchange code
    return EquityQuery("eq", ["exchange", exchange.upper()])


def _build_sector_condition(sector: str) -> EquityQuery:
    """Build an EquityQuery condition for sector filtering.

    Parameters
    ----------
    sector : str
        Sector name (e.g. 'Technology', 'Financial Services').

    Returns
    -------
    EquityQuery
    """
    return EquityQuery("eq", ["sector", sector])


def build_query(
    criteria: dict,
    region: Optional[str] = None,
    exchange: Optional[str] = None,
    sector: Optional[str] = None,
) -> EquityQuery:
    """Build a complete EquityQuery from criteria, region, exchange, and sector.

    All provided conditions are combined with AND.

    Parameters
    ----------
    criteria : dict
        Screening criteria (max_per, max_pbr, min_dividend_yield, etc.).
    region : str, optional
        Market region name or code (e.g. 'japan', 'us', 'asean', 'jp').
    exchange : str, optional
        Exchange name or code. If both region and exchange are given,
        both conditions are included.
    sector : str, optional
        Sector filter (e.g. 'Technology', 'Financial Services').

    Returns
    -------
    EquityQuery
        A single AND-combined query ready for ``yf.screen()``.

    Raises
    ------
    ValueError
        If no conditions could be built (empty criteria and no region/exchange/sector).
    """
    conditions: list[EquityQuery] = []

    # Region condition
    if region is not None:
        region_cond = _build_region_condition(region)
        if region_cond is not None:
            conditions.append(region_cond)

    # Exchange condition
    if exchange is not None:
        exchange_cond = _build_exchange_condition(exchange)
        if exchange_cond is not None:
            conditions.append(exchange_cond)

    # Sector condition
    if sector is not None:
        conditions.append(_build_sector_condition(sector))

    # Criteria conditions
    criteria_conds = _build_criteria_conditions(criteria)
    conditions.extend(criteria_conds)

    if not conditions:
        raise ValueError(
            "No query conditions could be built. "
            "Provide at least one of: region, exchange, sector, or screening criteria."
        )

    # Single condition doesn't need wrapping in AND
    if len(conditions) == 1:
        return conditions[0]

    return EquityQuery("and", conditions)
