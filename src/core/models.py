"""Core data models for portfolio management (KIK-365 Phase 2).

Dataclasses providing type safety for the main domain objects.
External interfaces remain dict-based for backward compatibility;
these classes are used internally and provide to_dict() for conversion.
"""

from dataclasses import asdict, dataclass, field
from typing import Optional, Union


@dataclass
class Position:
    """A single portfolio position.

    Attributes
    ----------
    symbol : str
        Ticker symbol (e.g., "7203.T", "AAPL", "JPY.CASH").
    shares : int
        Number of shares held.
    cost_price : float
        Average acquisition price per share (in cost_currency).
    cost_currency : str
        Currency of the cost_price (e.g., "JPY", "USD").
    current_price : float
        Latest market price per share (in market_currency).
    value_jpy : float
        Current position value in JPY.
    sector : str
        GICS sector name (e.g., "Technology").
    country : str
        Country of domicile.
    market_currency : str
        Trading currency on the exchange.
    name : str
        Company/fund display name.
    purchase_date : str
        Date of last purchase (YYYY-MM-DD).
    memo : str
        Free-form note.
    """

    symbol: str
    shares: int
    cost_price: float
    cost_currency: str
    current_price: float = 0.0
    value_jpy: float = 0.0
    sector: str = ""
    country: str = ""
    market_currency: str = ""
    name: str = ""
    purchase_date: str = ""
    memo: str = ""

    @property
    def is_cash(self) -> bool:
        from src.core.common import is_cash
        return is_cash(self.symbol)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Position":
        return cls(
            symbol=d.get("symbol", ""),
            shares=int(d.get("shares", 0)),
            cost_price=float(d.get("cost_price", 0.0)),
            cost_currency=d.get("cost_currency", "JPY"),
            current_price=float(d.get("current_price", 0.0)),
            value_jpy=float(d.get("value_jpy") or d.get("evaluation_jpy") or 0.0),
            sector=d.get("sector") or "",
            country=d.get("country") or "",
            market_currency=d.get("market_currency") or "",
            name=d.get("name") or "",
            purchase_date=d.get("purchase_date") or "",
            memo=d.get("memo") or "",
        )


@dataclass
class ForecastResult:
    """Return estimate for a single stock.

    Attributes
    ----------
    symbol : str
        Ticker symbol.
    method : str
        Estimation method: "analyst", "historical", "no_data", or "cash".
    base : float or None
        Base-case annualized return estimate.
    optimistic : float or None
        Optimistic annualized return estimate.
    pessimistic : float or None
        Pessimistic annualized return estimate.
    """

    symbol: str
    method: str
    base: Optional[float] = None
    optimistic: Optional[float] = None
    pessimistic: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ForecastResult":
        return cls(
            symbol=d.get("symbol", ""),
            method=d.get("method", "no_data"),
            base=d.get("base"),
            optimistic=d.get("optimistic"),
            pessimistic=d.get("pessimistic"),
        )


@dataclass
class HealthResult:
    """Health check result for a single holding.

    Attributes
    ----------
    symbol : str
        Ticker symbol.
    trend : str
        Price trend direction: "上昇", "横ばい", or "下降".
    quality_label : str
        Fundamental quality: "良好", "1指標↓", "複数悪化", or "対象外".
    alert_level : str
        Alert severity: "", "early_warning", "caution", or "exit".
    reasons : list
        Human-readable alert reason strings.
    """

    symbol: str
    trend: str = ""
    quality_label: str = ""
    alert_level: str = ""
    reasons: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "HealthResult":
        alert = d.get("alert", {})
        return cls(
            symbol=d.get("symbol", ""),
            trend=d.get("trend_health", {}).get("trend", ""),
            quality_label=d.get("change_quality", {}).get("quality_label", ""),
            alert_level=alert.get("level", ""),
            reasons=alert.get("reasons", []),
        )


@dataclass
class RebalanceAction:
    """A single rebalancing action proposal.

    Attributes
    ----------
    action : str
        Action type: "sell", "reduce", "increase", or "buy".
    symbol : str
        Ticker symbol.
    name : str
        Company/fund display name.
    ratio : float
        Proportion to sell/reduce (0.0-1.0) for sell/reduce actions.
    amount_jpy : float
        Amount in JPY for increase actions.
    reason : str
        Human-readable justification.
    priority : int
        Execution priority (1=highest, 99=default).
    """

    action: str
    symbol: str
    name: str = ""
    ratio: float = 0.0
    amount_jpy: float = 0.0
    reason: str = ""
    priority: int = 99

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class YearlySnapshot:
    """1年分のシミュレーション結果 (KIK-366)."""

    year: int
    value: float
    cumulative_input: float
    capital_gain: float
    cumulative_dividends: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SimulationResult:
    """複利シミュレーション結果 (KIK-366)."""

    scenarios: dict[str, list[YearlySnapshot]]
    target: Optional[float]
    target_year_base: Optional[float]
    target_year_optimistic: Optional[float]
    target_year_pessimistic: Optional[float]
    required_monthly: Optional[float]
    dividend_effect: float
    dividend_effect_pct: float

    years: int = 0
    monthly_add: float = 0.0
    reinvest_dividends: bool = True
    current_value: float = 0.0
    portfolio_return_base: Union[float, None] = None
    dividend_yield: float = 0.0

    def to_dict(self) -> dict:
        result = {
            "scenarios": {
                key: [s.to_dict() for s in snapshots]
                for key, snapshots in self.scenarios.items()
            },
            "target": self.target,
            "target_year_base": self.target_year_base,
            "target_year_optimistic": self.target_year_optimistic,
            "target_year_pessimistic": self.target_year_pessimistic,
            "required_monthly": self.required_monthly,
            "dividend_effect": self.dividend_effect,
            "dividend_effect_pct": self.dividend_effect_pct,
            "years": self.years,
            "monthly_add": self.monthly_add,
            "reinvest_dividends": self.reinvest_dividends,
            "current_value": self.current_value,
            "portfolio_return_base": self.portfolio_return_base,
            "dividend_yield": self.dividend_yield,
        }
        return result

    @classmethod
    def empty(cls) -> "SimulationResult":
        """シミュレーション不可時の空結果。"""
        return cls(
            scenarios={},
            target=None,
            target_year_base=None,
            target_year_optimistic=None,
            target_year_pessimistic=None,
            required_monthly=None,
            dividend_effect=0.0,
            dividend_effect_pct=0.0,
        )
