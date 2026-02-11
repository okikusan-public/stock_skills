"""ASEAN stock markets (Singapore, Thailand, Malaysia, Indonesia, Philippines)."""

from .base import Market


# Exchange suffix mapping (kept for format_ticker backward compatibility)
EXCHANGE_SUFFIXES = {
    "SGX": ".SI",   # Singapore Exchange
    "SET": ".BK",   # Stock Exchange of Thailand
    "KLSE": ".KL",  # Bursa Malaysia
    "IDX": ".JK",   # Indonesia Stock Exchange
    "PSE": ".PS",   # Philippine Stock Exchange
}

# Mapping from legacy exchange name to EquityQuery region code
_REGION_MAP = {
    "SGX": "sg",
    "SET": "th",
    "KLSE": "my",
    "IDX": "id",
    "PSE": "ph",
}

# Mapping from legacy exchange name to EquityQuery exchange code
_EXCHANGE_CODE_MAP = {
    "SGX": "SES",
    "SET": "SET",
    "KLSE": "KLS",
    "IDX": "JKT",
    "PSE": "PHP",
}


class ASEANMarket(Market):
    """ASEAN equities across multiple exchanges.

    EquityQuery regions: ``sg``, ``th``, ``my``, ``id``, ``ph``
    EquityQuery exchanges: ``SES``, ``SET``, ``KLS``, ``JKT``, ``PHP``
    """

    name = "ASEAN株"

    # -- EquityQuery support ------------------------------------------------

    def get_region(self) -> list[str]:
        """Return all ASEAN region codes for yfinance EquityQuery.

        Returns a list because ASEAN spans multiple yfinance regions:
        sg (Singapore), th (Thailand), my (Malaysia), id (Indonesia),
        ph (Philippines).
        """
        return ["sg", "th", "my", "id", "ph"]

    def get_exchanges(self) -> list[str]:
        """Return all ASEAN exchange codes for yfinance EquityQuery.

        SES = Singapore Exchange, SET = Stock Exchange of Thailand,
        KLS = Bursa Malaysia, JKT = Indonesia Stock Exchange,
        PHP = Philippine Stock Exchange.
        """
        return ["SES", "SET", "KLS", "JKT", "PHP"]

    def get_equity_query(self) -> dict:
        """Return a base EquityQuery filter dict for ASEAN markets.

        Overrides the base implementation to provide multi-region support.
        The ``region`` key contains a list of region codes and ``exchanges``
        contains the corresponding exchange codes.  The caller / EquityQuery
        builder should OR these together.
        """
        return {
            "region": self.get_region(),
            "exchanges": self.get_exchanges(),
        }

    # -- Ticker formatting --------------------------------------------------

    def format_ticker(self, code: str) -> str:
        """Format a ticker, adding exchange suffix if not already present.

        Accepts formats like:
          - 'D05.SI'       -> returned as-is
          - 'D05:SGX'      -> converted to 'D05.SI'
          - 'D05'          -> returned as-is (caller must include suffix)
        """
        code = code.strip()

        # Already has a recognised suffix
        if any(code.endswith(suffix) for suffix in EXCHANGE_SUFFIXES.values()):
            return code

        # Exchange specified via colon notation, e.g. 'D05:SGX'
        if ":" in code:
            ticker_part, exchange = code.split(":", 1)
            suffix = EXCHANGE_SUFFIXES.get(exchange.upper(), "")
            return f"{ticker_part}{suffix}"

        # No suffix and no exchange hint -- return as-is
        return code

    # ------------------------------------------------------------------
    # Default symbols per country (fallback)
    # ------------------------------------------------------------------

    @staticmethod
    def _singapore_symbols() -> list[str]:
        """Major SGX-listed stocks."""
        return [
            "D05.SI",   # DBS Group
            "O39.SI",   # OCBC Bank
            "U11.SI",   # United Overseas Bank
            "Z74.SI",   # Singapore Telecommunications
            "C6L.SI",   # Singapore Airlines
            "A17U.SI",  # CapitaLand Ascendas REIT
            "BN4.SI",   # Keppel Corporation
        ]

    @staticmethod
    def _thailand_symbols() -> list[str]:
        """Major SET-listed stocks."""
        return [
            "PTT.BK",    # PTT Public Company
            "AOT.BK",    # Airports of Thailand
            "SCC.BK",    # Siam Cement
            "ADVANC.BK", # Advanced Info Service
            "CPALL.BK",  # CP ALL
            "KBANK.BK",  # Kasikornbank
            "SCB.BK",    # SCB X
        ]

    @staticmethod
    def _malaysia_symbols() -> list[str]:
        """Major KLSE-listed stocks."""
        return [
            "1155.KL",  # Malayan Banking (Maybank)
            "1295.KL",  # Public Bank
            "6888.KL",  # Axiata Group
            "4707.KL",  # Nestle Malaysia
            "5183.KL",  # Petronas Chemicals
            "3182.KL",  # Genting
        ]

    @staticmethod
    def _indonesia_symbols() -> list[str]:
        """Major IDX-listed stocks."""
        return [
            "BBCA.JK",  # Bank Central Asia
            "BBRI.JK",  # Bank Rakyat Indonesia
            "TLKM.JK",  # Telkom Indonesia
            "ASII.JK",  # Astra International
            "UNVR.JK",  # Unilever Indonesia
            "BMRI.JK",  # Bank Mandiri
        ]

    @staticmethod
    def _philippines_symbols() -> list[str]:
        """Major PSE-listed stocks."""
        return [
            "SM.PS",    # SM Investments
            "ALI.PS",   # Ayala Land
            "BDO.PS",   # BDO Unibank
            "TEL.PS",   # PLDT
            "JFC.PS",   # Jollibee Foods
            "AC.PS",    # Ayala Corporation
        ]

    def get_default_symbols(self) -> list[str]:
        """All default ASEAN symbols across the five exchanges."""
        return (
            self._singapore_symbols()
            + self._thailand_symbols()
            + self._malaysia_symbols()
            + self._indonesia_symbols()
            + self._philippines_symbols()
        )

    # -- Thresholds --------------------------------------------------------

    def get_thresholds(self) -> dict:
        """ASEAN market specific thresholds."""
        return {
            "per_max": 15.0,
            "pbr_max": 1.5,
            "dividend_yield_min": 0.03,  # 3%
            "roe_min": 0.08,
            "rf": 0.03,  # Blended ASEAN govies
        }
