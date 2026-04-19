"""Portfolio, Trade, HealthCheck, Forecast, StressTest node operations (KIK-507).

Handles merge_trade, merge_health, sync_portfolio, is_held, get_held_symbols,
merge_stress_test, merge_forecast, sync_stock_full (KIK-555).
"""

from src.data.graph_store import _common


# ---------------------------------------------------------------------------
# Trade node
# ---------------------------------------------------------------------------

def merge_trade(
    trade_date: str, trade_type: str, symbol: str,
    shares: int, price: float, currency: str, memo: str = "",
    semantic_summary: str = "", embedding: list[float] | None = None,
    sell_price: float | None = None,
    realized_pnl: float | None = None,
    hold_days: int | None = None,
) -> bool:
    """Create a Trade node and BOUGHT/SOLD relationship."""
    if _common._get_mode() == "off":
        return False
    driver = _common._get_driver()
    if driver is None:
        return False
    trade_id = f"trade_{trade_date}_{trade_type}_{symbol}"
    rel_type = "BOUGHT" if trade_type == "buy" else "SOLD"
    try:
        with driver.session() as session:
            session.run(
                "MERGE (t:Trade {id: $id}) "
                "SET t.date = $date, t.type = $type, t.symbol = $symbol, "
                "t.shares = $shares, t.price = $price, t.currency = $currency, "
                "t.memo = $memo, "
                "t.sell_price = $sell_price, t.realized_pnl = $realized_pnl, "
                "t.hold_days = $hold_days",
                id=trade_id, date=trade_date, type=trade_type,
                symbol=symbol, shares=shares, price=price,
                currency=currency, memo=memo,
                sell_price=sell_price, realized_pnl=realized_pnl,
                hold_days=hold_days,
            )
            session.run(
                f"MATCH (t:Trade {{id: $trade_id}}) "
                f"MERGE (s:Stock {{symbol: $symbol}}) "
                f"MERGE (t)-[:{rel_type}]->(s)",
                trade_id=trade_id, symbol=symbol,
            )
            _common._set_embedding(session, "Trade", trade_id, semantic_summary, embedding)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# HealthCheck node
# ---------------------------------------------------------------------------

def merge_health(health_date: str, summary: dict, symbols: list[str],
                  semantic_summary: str = "", embedding: list[float] | None = None,
                  ) -> bool:
    """Create a HealthCheck node and CHECKED relationships."""
    if _common._get_mode() == "off":
        return False
    driver = _common._get_driver()
    if driver is None:
        return False
    health_id = f"health_{health_date}"
    try:
        with driver.session() as session:
            session.run(
                "MERGE (h:HealthCheck {id: $id}) "
                "SET h.date = $date, h.total = $total, "
                "h.healthy = $healthy, h.exit_count = $exit_count",
                id=health_id, date=health_date,
                total=summary.get("total", 0),
                healthy=summary.get("healthy", 0),
                exit_count=summary.get("exit", 0),
            )
            for sym in symbols:
                session.run(
                    "MATCH (h:HealthCheck {id: $health_id}) "
                    "MERGE (s:Stock {symbol: $symbol}) "
                    "MERGE (h)-[:CHECKED]->(s)",
                    health_id=health_id, symbol=sym,
                )
            _common._set_embedding(session, "HealthCheck", health_id, semantic_summary, embedding)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Portfolio sync (KIK-414)
# ---------------------------------------------------------------------------

def sync_portfolio(holdings: list[dict]) -> bool:
    """Sync portfolio CSV holdings to Neo4j HOLDS relationships.

    Creates a Portfolio anchor node and HOLDS relationships to each Stock.
    Removes HOLDS for stocks no longer in the portfolio.
    Cash positions (*.CASH) are excluded.
    """
    if _common._get_mode() == "off":
        return False
    driver = _common._get_driver()
    if driver is None:
        return False
    try:
        from src.data.common import is_cash

        with driver.session() as session:
            session.run("MERGE (p:Portfolio {name: 'default'})")

            current_symbols = []
            for h in holdings:
                symbol = h.get("symbol", "")
                if not symbol or is_cash(symbol):
                    continue
                current_symbols.append(symbol)
                session.run(
                    "MERGE (s:Stock {symbol: $symbol})",
                    symbol=symbol,
                )
                session.run(
                    "MATCH (p:Portfolio {name: 'default'}) "
                    "MATCH (s:Stock {symbol: $symbol}) "
                    "MERGE (p)-[r:HOLDS]->(s) "
                    "SET r.shares = $shares, r.cost_price = $cost_price, "
                    "r.cost_currency = $cost_currency, "
                    "r.purchase_date = $purchase_date",
                    symbol=symbol,
                    shares=int(h.get("shares", 0)),
                    cost_price=float(h.get("cost_price", 0)),
                    cost_currency=h.get("cost_currency", "JPY"),
                    purchase_date=h.get("purchase_date", ""),
                )

            if current_symbols:
                session.run(
                    "MATCH (p:Portfolio {name: 'default'})-[r:HOLDS]->(s:Stock) "
                    "WHERE NOT s.symbol IN $symbols "
                    "DELETE r",
                    symbols=current_symbols,
                )
            else:
                session.run(
                    "MATCH (p:Portfolio {name: 'default'})-[r:HOLDS]->() "
                    "DELETE r",
                )
        return True
    except Exception:
        return False


def is_held(symbol: str) -> bool:
    """Check if a symbol is currently held in the portfolio."""
    driver = _common._get_driver()
    if driver is None:
        return False
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (p:Portfolio {name: 'default'})-[:HOLDS]->(s:Stock {symbol: $symbol}) "
                "RETURN count(*) AS cnt",
                symbol=symbol,
            )
            record = result.single()
            return record["cnt"] > 0 if record else False
    except Exception:
        return False


def get_held_symbols() -> list[str]:
    """Return symbols currently held in portfolio via HOLDS relationship."""
    driver = _common._get_driver()
    if driver is None:
        return []
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (p:Portfolio {name: 'default'})-[:HOLDS]->(s:Stock) "
                "RETURN s.symbol AS symbol"
            )
            return [r["symbol"] for r in result]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# StressTest node (KIK-428)
# ---------------------------------------------------------------------------

def merge_stress_test(
    test_date: str, scenario: str, portfolio_impact: float,
    symbols: list[str], var_95: float = 0, var_99: float = 0,
    semantic_summary: str = "", embedding: list[float] | None = None,
) -> bool:
    """Create a StressTest node and STRESSED relationships to stocks."""
    if _common._get_mode() == "off":
        return False
    driver = _common._get_driver()
    if driver is None:
        return False
    test_id = f"stress_test_{test_date}_{_common._safe_id(scenario)}"
    try:
        with driver.session() as session:
            session.run(
                "MERGE (st:StressTest {id: $id}) "
                "SET st.date = $date, st.scenario = $scenario, "
                "st.portfolio_impact = $impact, "
                "st.var_95 = $var95, st.var_99 = $var99, "
                "st.symbol_count = $cnt",
                id=test_id, date=test_date, scenario=scenario,
                impact=float(portfolio_impact),
                var95=float(var_95), var99=float(var_99),
                cnt=len(symbols),
            )
            for sym in symbols:
                session.run(
                    "MATCH (st:StressTest {id: $test_id}) "
                    "MERGE (s:Stock {symbol: $symbol}) "
                    "MERGE (st)-[:STRESSED]->(s)",
                    test_id=test_id, symbol=sym,
                )
            _common._set_embedding(session, "StressTest", test_id, semantic_summary, embedding)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Forecast node (KIK-428)
# ---------------------------------------------------------------------------

def merge_forecast(
    forecast_date: str, optimistic: float, base: float, pessimistic: float,
    symbols: list[str], total_value_jpy: float = 0,
    semantic_summary: str = "", embedding: list[float] | None = None,
) -> bool:
    """Create a Forecast node and FORECASTED relationships to stocks."""
    if _common._get_mode() == "off":
        return False
    driver = _common._get_driver()
    if driver is None:
        return False
    forecast_id = f"forecast_{forecast_date}"
    try:
        with driver.session() as session:
            session.run(
                "MERGE (f:Forecast {id: $id}) "
                "SET f.date = $date, f.optimistic = $opt, "
                "f.base = $base, f.pessimistic = $pess, "
                "f.total_value_jpy = $total, f.symbol_count = $cnt",
                id=forecast_id, date=forecast_date,
                opt=float(optimistic), base=float(base),
                pess=float(pessimistic),
                total=float(total_value_jpy), cnt=len(symbols),
            )
            for sym in symbols:
                session.run(
                    "MATCH (f:Forecast {id: $forecast_id}) "
                    "MERGE (s:Stock {symbol: $symbol}) "
                    "MERGE (f)-[:FORECASTED]->(s)",
                    forecast_id=forecast_id, symbol=sym,
                )
            _common._set_embedding(session, "Forecast", forecast_id, semantic_summary, embedding)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Full stock sync (KIK-555)
# ---------------------------------------------------------------------------

def sync_stock_full(symbol: str, client=None, csv_path: str = "") -> dict:
    """Single entry point for complete Stock + Trade Neo4j sync (KIK-555).

    Ensures all of the following are present:
    1. Stock metadata (name, sector, country) from yfinance
    2. Trade nodes with embeddings from history JSON
    3. IN_SECTOR relationship (auto from merge_stock when sector set)
    4. Community assignment (incremental)

    Parameters
    ----------
    symbol : str
        Ticker symbol.
    client : module, optional
        yahoo_client module. If None, imports automatically.
    csv_path : str, optional
        Path to portfolio CSV. Used to find trade history.

    Returns
    -------
    dict with keys: stock (bool), trades (int), community (bool)
    """
    result = {"stock": False, "trades": 0, "community": False}

    if _common._get_mode() == "off":
        return result

    # 1. Stock metadata from yfinance
    try:
        if client is None:
            from src.data import yahoo_client as client  # noqa: N811
        info = client.get_stock_info(symbol)
        if info:
            from src.data.graph_store.stock import merge_stock
            result["stock"] = merge_stock(
                symbol=symbol,
                name=info.get("name", ""),
                sector=info.get("sector", ""),
                country=info.get("country", ""),
            )
    except Exception:
        pass

    # 2. Trade records from history JSON
    try:
        import glob
        import json
        from pathlib import Path

        history_dir = Path("data/history/trade")
        if not history_dir.exists():
            history_dir = Path(__file__).resolve().parents[3] / "data" / "history" / "trade"

        if history_dir.exists():
            for fp in sorted(history_dir.glob("*.json")):
                try:
                    with open(fp, encoding="utf-8") as f:
                        rec = json.load(f)
                    if rec.get("symbol") != symbol:
                        continue
                    # Build summary + embedding
                    sem = ""
                    emb = None
                    try:
                        from src.data.context.summary_builder import build_trade_summary
                        from src.data import embedding_client
                        sem = build_trade_summary(
                            rec.get("date", ""), rec.get("trade_type", ""),
                            symbol, rec.get("shares", 0), rec.get("memo", ""),
                        )
                        emb = embedding_client.get_embedding(sem)
                    except Exception:
                        pass
                    ok = merge_trade(
                        trade_date=rec.get("date", ""),
                        trade_type=rec.get("trade_type", "buy"),
                        symbol=symbol,
                        shares=rec.get("shares", 0),
                        price=rec.get("price", 0),
                        currency=rec.get("currency", "JPY"),
                        memo=rec.get("memo", ""),
                        semantic_summary=sem,
                        embedding=emb,
                        sell_price=rec.get("sell_price"),
                        realized_pnl=rec.get("realized_pnl"),
                        hold_days=rec.get("hold_days"),
                    )
                    if ok:
                        result["trades"] += 1
                except Exception:
                    continue
    except Exception:
        pass

    # 3. Community assignment
    try:
        from src.data.graph_query.community import update_stock_community
        comm = update_stock_community(symbol)
        result["community"] = comm is not None
    except Exception:
        pass

    return result
