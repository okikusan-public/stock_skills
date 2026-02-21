"""Portfolio concentration analysis module.

Provides HHI (Herfindahl-Hirschman Index) calculation and
multi-axis concentration analysis for sector, region, and currency.
"""

from typing import Optional


def compute_hhi(weights: list[float]) -> float:
    """Compute the Herfindahl-Hirschman Index for a set of weights.

    HHI = sum(w_i^2) for each weight w_i.
    Range: 1/N (perfectly diversified) to 1.0 (single-asset concentration).

    Parameters
    ----------
    weights : list[float]
        Portfolio weights that should sum to approximately 1.0.

    Returns
    -------
    float
        HHI value between 0 and 1.
    """
    if not weights:
        return 0.0
    return sum(w * w for w in weights)


def get_concentration_multiplier(hhi: float) -> float:
    """Derive a concentration multiplier from an HHI value.

    The multiplier amplifies shock impact for concentrated portfolios.

    Mapping:
      - HHI < 0.25         -> 1.0  (well diversified, no amplification)
      - HHI 0.25 .. 0.50   -> 1.0 .. 1.3  (linear interpolation)
      - HHI 0.50 .. 1.00   -> 1.3 .. 1.6  (linear interpolation, capped at 1.6)

    Parameters
    ----------
    hhi : float
        Herfindahl-Hirschman Index value (0 to 1).

    Returns
    -------
    float
        Concentration multiplier (1.0 to 1.6).
    """
    if hhi < 0.25:
        return 1.0
    if hhi <= 0.50:
        # Linear interpolation: 0.25 -> 1.0, 0.50 -> 1.3
        return 1.0 + (hhi - 0.25) / (0.50 - 0.25) * (1.3 - 1.0)
    # hhi > 0.50: Linear interpolation: 0.50 -> 1.3, 1.00 -> 1.6
    multiplier = 1.3 + (hhi - 0.50) / (1.00 - 0.50) * (1.6 - 1.3)
    return min(multiplier, 1.6)


def _compute_axis_hhi(
    portfolio_data: list[dict],
    weights: list[float],
    key: str,
    default_label: str = "Unknown",
) -> tuple[float, dict[str, float]]:
    """Compute HHI along a single axis (sector, country, or currency).

    Groups portfolio weights by the given ``key`` and calculates HHI
    on the grouped weights.

    Parameters
    ----------
    portfolio_data : list[dict]
        Per-stock data dicts.  Each must contain the field named ``key``.
    weights : list[float]
        Portfolio weights aligned with ``portfolio_data``.
    key : str
        The dict key to group by (e.g. ``"sector"``, ``"country"``, ``"currency"``).
    default_label : str
        Label used when the key is missing or None.

    Returns
    -------
    tuple[float, dict[str, float]]
        ``(hhi, breakdown)`` where breakdown maps category -> summed weight.
    """
    breakdown: dict[str, float] = {}
    for stock, w in zip(portfolio_data, weights):
        label = stock.get(key) or default_label
        breakdown[label] = breakdown.get(label, 0.0) + w

    group_weights = list(breakdown.values())
    hhi = compute_hhi(group_weights)
    return hhi, breakdown


def _classify_risk_level(hhi: float) -> str:
    """Classify concentration risk level from HHI.

    Parameters
    ----------
    hhi : float
        Maximum HHI across all axes.

    Returns
    -------
    str
        Risk level label in Japanese.
    """
    if hhi < 0.25:
        return "分散"
    if hhi < 0.50:
        return "やや集中"
    return "危険な集中"


def analyze_concentration(
    portfolio_data: list[dict],
    weights: list[float],
) -> dict:
    """Perform multi-axis concentration analysis on a portfolio.

    Evaluates concentration along four axes -- sector, region (country),
    currency, and size (KIK-438) -- then identifies the weakest
    (most concentrated) axis.

    Parameters
    ----------
    portfolio_data : list[dict]
        Per-stock data dicts.  Expected keys per stock:
        ``sector``, ``country`` (or ``region``), ``currency``,
        ``size_class`` (optional, KIK-438).
    weights : list[float]
        Portfolio weights aligned with ``portfolio_data``.
        Should sum to approximately 1.0.

    Returns
    -------
    dict
        {
            "sector_hhi": float,
            "region_hhi": float,
            "currency_hhi": float,
            "size_hhi": float,
            "max_hhi": float,
            "max_hhi_axis": str,
            "concentration_multiplier": float,
            "sector_breakdown": dict,
            "region_breakdown": dict,
            "currency_breakdown": dict,
            "size_breakdown": dict,
            "risk_level": str,
        }
    """
    # Sector HHI
    sector_hhi, sector_breakdown = _compute_axis_hhi(
        portfolio_data, weights, "sector", default_label="不明"
    )

    # Region HHI -- try "country" first, fall back to "region"
    region_hhi, region_breakdown = _compute_axis_hhi(
        portfolio_data, weights, "country", default_label="不明"
    )
    # If all ended up "不明", try the "region" key instead
    if list(region_breakdown.keys()) == ["不明"]:
        region_hhi, region_breakdown = _compute_axis_hhi(
            portfolio_data, weights, "region", default_label="不明"
        )

    # Currency HHI
    currency_hhi, currency_breakdown = _compute_axis_hhi(
        portfolio_data, weights, "currency", default_label="不明"
    )

    # Size HHI (KIK-438)
    size_hhi, size_breakdown = _compute_axis_hhi(
        portfolio_data, weights, "size_class", default_label="不明"
    )

    # Determine the axis with the highest HHI
    # Exclude size axis from max_hhi if all entries are "不明" (no data)
    axes = {
        "sector": sector_hhi,
        "region": region_hhi,
        "currency": currency_hhi,
    }
    if set(size_breakdown.keys()) != {"不明"}:
        axes["size"] = size_hhi
    max_hhi_axis = max(axes, key=axes.get)
    max_hhi = axes[max_hhi_axis]

    concentration_multiplier = get_concentration_multiplier(max_hhi)
    risk_level = _classify_risk_level(max_hhi)

    return {
        "sector_hhi": round(sector_hhi, 4),
        "region_hhi": round(region_hhi, 4),
        "currency_hhi": round(currency_hhi, 4),
        "size_hhi": round(size_hhi, 4),
        "max_hhi": round(max_hhi, 4),
        "max_hhi_axis": max_hhi_axis,
        "concentration_multiplier": round(concentration_multiplier, 4),
        "sector_breakdown": sector_breakdown,
        "region_breakdown": region_breakdown,
        "currency_breakdown": currency_breakdown,
        "size_breakdown": size_breakdown,
        "risk_level": risk_level,
    }
