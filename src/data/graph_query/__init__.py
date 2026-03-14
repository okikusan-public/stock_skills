"""Graph query helpers for enriching skill output (KIK-406/413/420).

All functions return empty/None when Neo4j is unavailable (graceful degradation).
KIK-413 additions: semantic sub-node queries (news, sentiment, catalysts, report trend, events).
KIK-420 additions: vector_search() for semantic similarity across all node types.

Split into submodules in KIK-508.
"""

# --- Common ---
from src.data.graph_query._common import _get_driver  # noqa: F401

# --- Stock/Screen/Report queries ---
from src.data.graph_query.stock import (  # noqa: F401
    get_prior_report,
    get_screening_frequency,
    get_trade_context,
    get_recurring_picks,
    get_report_trend,
    get_recent_sells_batch,
    get_notes_for_symbols_batch,
    get_themes_for_symbols_batch,
)

# --- Research/News/Sentiment/Catalyst queries ---
from src.data.graph_query.research import (  # noqa: F401
    get_research_chain,
    get_stock_news_history,
    get_sentiment_trend,
    get_catalysts,
    get_sector_catalysts,
    get_industry_research_for_sector,
    get_nodes_for_symbol,
    get_industry_research_for_linking,
)

# --- Portfolio/Trade/Forecast queries ---
from src.data.graph_query.portfolio import (  # noqa: F401
    get_current_holdings,
    get_stress_test_history,
    get_forecast_history,
    get_portfolio_holdings_for_linking,
    vector_search,
)

# --- Market/Events queries ---
from src.data.graph_query.market import (  # noqa: F401
    get_recent_market_context,
    get_upcoming_events,
)

# --- ActionItem queries ---
from src.data.graph_query.action_item import (  # noqa: F401
    get_action_item_history,
)

# --- Proactive intelligence helpers ---
from src.data.graph_query.proactive import (  # noqa: F401
    get_last_health_check_date,
    get_old_thesis_notes,
    get_concern_notes,
)

# --- Community detection (KIK-547) ---
from src.data.graph_query.community import (  # noqa: F401
    detect_communities,
    get_communities,
    get_stock_community,
    get_similar_stocks,
)

# --- nl_query.py: Natural language → graph query dispatcher (KIK-409, KIK-517) ---
from src.data.graph_query.nl_query import (  # noqa: F401
    query,
    format_result,
)
