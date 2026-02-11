"""Japanese stock market (Tokyo Stock Exchange)."""

from .base import Market


class JapanMarket(Market):
    """Tokyo Stock Exchange (.T suffix).

    EquityQuery region: ``jp``
    EquityQuery exchange: ``JPX`` (東証プライム・スタンダード・グロース)
    """

    name = "日本株"
    SUFFIX = ".T"

    # -- EquityQuery support ------------------------------------------------

    def get_region(self) -> str:
        """Return 'jp' for yfinance EquityQuery."""
        return "jp"

    def get_exchanges(self) -> list[str]:
        """Return JPX as the primary exchange.

        FKA (福岡) and SAP (札幌) are available but rarely needed for
        mainstream screening.  Callers may override if needed.
        """
        return ["JPX"]

    # -- Ticker formatting --------------------------------------------------

    def format_ticker(self, code: str) -> str:
        """Convert a stock code to a TSE ticker.

        If the code is a 4-digit number (e.g. '7203'), '.T' is appended automatically.
        If it already contains a suffix, it is returned as-is.
        """
        code = code.strip()
        if "." in code:
            return code
        if code.isdigit() and len(code) == 4:
            return f"{code}{self.SUFFIX}"
        return f"{code}{self.SUFFIX}"

    # -- Default symbol list (fallback) ------------------------------------

    def get_default_symbols(self) -> list[str]:
        """Major Nikkei 225 constituents (approx. 25 symbols)."""
        return [
            # Automotive
            "7203.T",  # Toyota Motor
            "7267.T",  # Honda Motor
            "7974.T",  # Nintendo
            # Electronics / Tech
            "6758.T",  # Sony Group
            "6861.T",  # Keyence
            "6501.T",  # Hitachi
            "6902.T",  # Denso
            "6762.T",  # TDK
            "6954.T",  # Fanuc
            "4063.T",  # Shin-Etsu Chemical
            # Finance
            "8306.T",  # Mitsubishi UFJ Financial
            "8316.T",  # Sumitomo Mitsui Financial
            "8411.T",  # Mizuho Financial
            "8766.T",  # Tokio Marine Holdings
            # Trading
            "8058.T",  # Mitsubishi Corporation
            "8031.T",  # Mitsui & Co.
            "8001.T",  # Itochu
            # Telecom / Services
            "9432.T",  # NTT
            "9433.T",  # KDDI
            "9984.T",  # SoftBank Group
            # Pharma / Healthcare
            "4502.T",  # Takeda Pharmaceutical
            "4568.T",  # Daiichi Sankyo
            # Retail / Consumer
            "9983.T",  # Fast Retailing
            "4452.T",  # Kao
            # Industrial
            "6301.T",  # Komatsu
            "7751.T",  # Canon
        ]

    # -- Thresholds --------------------------------------------------------

    def get_thresholds(self) -> dict:
        """Japanese market specific thresholds."""
        return {
            "per_max": 15.0,
            "pbr_max": 1.0,
            "dividend_yield_min": 0.025,  # 2.5%
            "roe_min": 0.08,
            "rf": 0.005,  # 10-year JGB
        }
