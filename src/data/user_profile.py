"""User profile settings loader (KIK-599).

Reads broker, fee, and tax configuration from config/user_profile.yaml.
Falls back to sensible defaults if file is missing (graceful degradation).
"""

from __future__ import annotations

import yaml
from pathlib import Path

_PROFILE_PATH = Path(__file__).resolve().parents[2] / "config" / "user_profile.yaml"
_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "user_profile.yaml.example"

_cache: dict | None = None


def get_profile() -> dict:
    """Load user profile. Returns defaults if file missing."""
    global _cache
    if _cache is not None:
        return _cache

    path = _PROFILE_PATH if _PROFILE_PATH.exists() else _DEFAULT_PATH
    if not path.exists():
        _cache = _get_defaults()
        return _cache

    with open(path) as f:
        _cache = yaml.safe_load(f) or _get_defaults()
    return _cache


def get_fee(region: str, amount_local: float, is_sell: bool = False) -> dict:
    """Calculate trading fee for a region and amount.

    Returns dict with keys: fee, rate, sec_fee (if applicable), total
    """
    profile = get_profile()
    fees = profile.get("fees", {})

    # Map region to fee config key
    region_map = {
        "us": "us_stock",
        "japan": "jp_stock",
        "jp": "jp_stock",
        "sg": "asean_stock",
        "id": "asean_stock",
        "th": "asean_stock",
        "my": "asean_stock",
        "ph": "asean_stock",
        "hk": "asean_stock",
    }
    fee_key = region_map.get(region.lower(), "us_stock")
    fee_config = fees.get(fee_key, {})

    rate = fee_config.get("rate", 0)
    fee = amount_local * rate

    # Apply min/max for US stocks
    if fee_key == "us_stock":
        min_fee = fee_config.get("min_usd", 0)
        max_fee = fee_config.get("max_usd", 22)
        fee = max(min_fee, min(fee, max_fee))

    result = {"fee": round(fee, 4), "rate": rate}

    # SEC fee (sell only, US only)
    if is_sell and fee_key == "us_stock":
        sec_rate = fee_config.get("sec_fee", 0)
        result["sec_fee"] = round(amount_local * sec_rate, 4)

    result["total"] = round(fee + result.get("sec_fee", 0), 4)
    return result


def get_tax_cost(gain_jpy: float) -> dict:
    """Calculate tax on capital gains.

    Returns dict with keys: tax, rate, needs_filing, taxable_gain,
    offset_applied, net_gain.
    Considers realized_losses_ytd for tax-loss harvesting.
    """
    profile = get_profile()
    tax_config = profile.get("tax", {})

    rate = tax_config.get("capital_gains_rate", 0.20315)
    needs_filing = tax_config.get("needs_filing", True)
    losses_ytd = tax_config.get("realized_losses_ytd", 0)

    # Offset gains with YTD losses
    taxable_gain = max(0, gain_jpy - abs(losses_ytd))
    tax = round(taxable_gain * rate)

    return {
        "tax": tax,
        "rate": rate,
        "needs_filing": needs_filing,
        "taxable_gain": taxable_gain,
        "offset_applied": min(abs(losses_ytd), gain_jpy) if losses_ytd else 0,
        "net_gain": round(gain_jpy - tax),
    }


def get_broker_info() -> dict:
    """Get broker name and account type."""
    profile = get_profile()
    return profile.get("broker", {"name": "不明", "account_type": "一般口座"})


def needs_tax_filing() -> bool:
    """Check if tax filing is required."""
    profile = get_profile()
    return profile.get("tax", {}).get("needs_filing", True)


def get_screening_regions() -> dict:
    """Get preferred and excluded regions for screening.

    Returns dict with keys:
    - preferred: list of region codes to include (empty = all)
    - excluded: list of region codes to exclude (empty = none)
    """
    profile = get_profile()
    screening = profile.get("screening", {})
    return {
        "preferred": screening.get("preferred_regions", []),
        "excluded": screening.get("excluded_regions", []),
    }


def _get_defaults() -> dict:
    """Return sensible default profile when no config file exists."""
    return {
        "broker": {"name": "不明", "account_type": "一般口座"},
        "fees": {
            "us_stock": {
                "rate": 0.00495,
                "min_usd": 0,
                "max_usd": 22,
                "sec_fee": 0.0000206,
            },
            "jp_stock": {"rate": 0},
            "asean_stock": {"rate": 0.011},
            "fx": {"realtime_spread": 0, "scheduled_spread": 0},
        },
        "tax": {
            "capital_gains_rate": 0.20315,
            "needs_filing": True,
            "realized_losses_ytd": 0,
        },
        "screening": {
            "preferred_regions": [],
            "excluded_regions": [],
        },
    }


def reset_cache():
    """Clear cached profile (for testing)."""
    global _cache
    _cache = None
