"""US stock market (NYSE / NASDAQ)."""

from .base import Market


class USMarket(Market):
    """US equities (no suffix required).

    EquityQuery region: ``us``
    EquityQuery exchanges: ``NMS`` (NASDAQ Global Select), ``NYQ`` (NYSE)
    """

    name = "米国株"

    # -- EquityQuery support ------------------------------------------------

    def get_region(self) -> str:
        """Return 'us' for yfinance EquityQuery."""
        return "us"

    def get_exchanges(self) -> list[str]:
        """Return the two major US exchanges.

        NMS = NASDAQ Global Select Market, NYQ = New York Stock Exchange.
        Additional exchanges (ASE, NGM, NCM, PCX, PNK) can be added by the
        caller if broader coverage is needed.
        """
        return ["NMS", "NYQ"]

    # -- Ticker formatting --------------------------------------------------

    def format_ticker(self, code: str) -> str:
        """Return the ticker as-is (no suffix needed for US stocks)."""
        return code.strip().upper()

    # -- Default symbol list (fallback) ------------------------------------

    def get_default_symbols(self) -> list[str]:
        """Major S&P 500 constituents (approx. 30 symbols)."""
        return [
            # Big Tech
            "AAPL",   # Apple
            "MSFT",   # Microsoft
            "GOOGL",  # Alphabet
            "AMZN",   # Amazon
            "META",   # Meta Platforms
            "NVDA",   # NVIDIA
            "TSLA",   # Tesla
            # Semiconductors
            "AVGO",   # Broadcom
            "AMD",    # AMD
            "INTC",   # Intel
            # Finance
            "JPM",    # JPMorgan Chase
            "BAC",    # Bank of America
            "GS",     # Goldman Sachs
            "BRK-B",  # Berkshire Hathaway
            "V",      # Visa
            "MA",     # Mastercard
            # Healthcare
            "JNJ",    # Johnson & Johnson
            "UNH",    # UnitedHealth
            "PFE",    # Pfizer
            "LLY",    # Eli Lilly
            # Consumer
            "PG",     # Procter & Gamble
            "KO",     # Coca-Cola
            "PEP",    # PepsiCo
            "WMT",    # Walmart
            "COST",   # Costco
            # Industrial / Energy
            "XOM",    # ExxonMobil
            "CVX",    # Chevron
            "CAT",    # Caterpillar
            # Communication / Media
            "DIS",    # Walt Disney
            "NFLX",   # Netflix
        ]

    # -- Thresholds --------------------------------------------------------

    def get_thresholds(self) -> dict:
        """US market specific thresholds."""
        return {
            "per_max": 20.0,
            "pbr_max": 3.0,
            "dividend_yield_min": 0.02,  # 2%
            "roe_min": 0.10,
            "rf": 0.04,  # 10-year Treasury
        }
