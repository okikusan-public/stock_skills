"""AlphaScreener: value + change quality + pullback multi-axis screening."""

from src.core.screening.alpha import compute_change_score
from src.core.screening.indicators import calculate_value_score
from src.core.screening.query_builder import build_query, load_preset
from src.core.screening.query_screener import QueryScreener
from src.core.screening.technicals import detect_pullback_in_uptrend


class AlphaScreener:
    """Alpha signal screener: value + change quality + pullback.

    4-step pipeline:
      Step 1: EquityQuery for fundamental filtering (value preset)
      Step 2: Change quality check (alpha.py) - 3/4 conditions must pass
      Step 3: Pullback-in-uptrend technical filter (optional enrichment)
      Step 4: 2-axis scoring (value_score + change_score = 200pt max)
    """

    def __init__(self, yahoo_client):
        self.yahoo_client = yahoo_client

    def screen(
        self,
        region: str = "jp",
        top_n: int = 20,
    ) -> list[dict]:
        # Step 1: EquityQuery with value preset criteria
        criteria = load_preset("value")
        query = build_query(criteria, region=region)

        raw_quotes = self.yahoo_client.screen_stocks(
            query,
            size=250,
            max_results=max(top_n * 5, 250),
            sort_field="intradaymarketcap",
            sort_asc=False,
        )

        if not raw_quotes:
            return []

        # Normalize and score
        fundamentals = []
        for quote in raw_quotes:
            normalized = QueryScreener._normalize_quote(quote)
            normalized["value_score"] = calculate_value_score(normalized)
            fundamentals.append(normalized)

        # Step 2: Change quality check (requires get_stock_detail)
        quality_passed = []
        for stock in fundamentals:
            symbol = stock.get("symbol")
            if not symbol:
                continue

            detail = self.yahoo_client.get_stock_detail(symbol)
            if detail is None:
                continue

            change_result = compute_change_score(detail)

            # 3/4 conditions must pass (quality_pass)
            if not change_result.get("quality_pass"):
                continue

            # Attach change score data
            stock["change_score"] = change_result["change_score"]
            stock["accruals_score"] = change_result["accruals"]["score"]
            stock["accruals_raw"] = change_result["accruals"]["raw"]
            stock["rev_accel_score"] = change_result["revenue_acceleration"]["score"]
            stock["rev_accel_raw"] = change_result["revenue_acceleration"]["raw"]
            stock["fcf_yield_score"] = change_result["fcf_yield"]["score"]
            stock["fcf_yield_raw"] = change_result["fcf_yield"]["raw"]
            stock["roe_trend_score"] = change_result["roe_trend"]["score"]
            stock["roe_trend_raw"] = change_result["roe_trend"]["raw"]
            stock["quality_passed_count"] = change_result["passed_count"]
            quality_passed.append(stock)

        if not quality_passed:
            return []

        # Step 3: Pullback check (optional enrichment, not a hard filter)
        for stock in quality_passed:
            symbol = stock["symbol"]
            try:
                hist = self.yahoo_client.get_price_history(symbol)
                if hist is not None and not hist.empty:
                    tech_result = detect_pullback_in_uptrend(hist)
                    if tech_result is not None:
                        all_conditions = tech_result.get("all_conditions")
                        bounce_score = tech_result.get("bounce_score", 0)

                        if all_conditions:
                            stock["pullback_match"] = "full"
                        elif (
                            bounce_score >= 30
                            and tech_result.get("uptrend")
                            and tech_result.get("is_pullback")
                        ):
                            stock["pullback_match"] = "partial"
                        else:
                            stock["pullback_match"] = "none"

                        stock["pullback_pct"] = tech_result.get("pullback_pct")
                        stock["rsi"] = tech_result.get("rsi")
                        stock["bounce_score"] = bounce_score
                    else:
                        stock["pullback_match"] = "none"
                else:
                    stock["pullback_match"] = "none"
            except Exception:
                stock["pullback_match"] = "none"

        # Step 4: 2-axis scoring
        results = []
        for stock in quality_passed:
            value_score = stock.get("value_score", 0)
            change_score = stock.get("change_score", 0)
            total_score = value_score + change_score  # 200pt max

            # Pullback bonus: full=+10, partial=+5
            pullback_match = stock.get("pullback_match", "none")
            if pullback_match == "full":
                total_score += 10
            elif pullback_match == "partial":
                total_score += 5

            stock["total_score"] = total_score
            results.append(stock)

        # Sort by total_score descending
        results.sort(key=lambda r: r.get("total_score", 0), reverse=True)
        return results[:top_n]
