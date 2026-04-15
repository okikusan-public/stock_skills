"""Tests for rebalance_formatter (KIK-597: lot-size annotations)."""

from src.output.rebalance_formatter import format_rebalance_report


def _base_proposal(**overrides):
    """Create a minimal rebalance proposal dict."""
    proposal = {
        "strategy": "balanced",
        "before": {"base_return": 0.10, "sector_hhi": 0.50, "region_hhi": 0.40},
        "after": {"base_return": 0.08, "sector_hhi": 0.45, "region_hhi": 0.38},
        "freed_cash_jpy": 0,
        "additional_cash_jpy": 0,
        "actions": [],
        "constraints": {},
    }
    proposal.update(overrides)
    return proposal


class TestRebalanceFormatterLotAnnotation:
    def test_reduce_action_has_lot_annotation(self):
        proposal = _base_proposal(
            freed_cash_jpy=200_000,
            actions=[{
                "action": "reduce",
                "symbol": "7203.T",
                "name": "Toyota",
                "ratio": 0.30,
                "reason": "比率 25% → 15%",
                "value_jpy": 200_000,
                "current_price": 2000.0,
                "priority": 3,
            }],
        )
        output = format_rebalance_report(proposal)
        # 200000 / 2000 = 100 shares, lot=100 → "≒ 100株（100株単位）"
        assert "100株" in output
        assert "100株単位" in output

    def test_increase_action_has_lot_annotation(self):
        proposal = _base_proposal(
            additional_cash_jpy=300_000,
            actions=[{
                "action": "increase",
                "symbol": "7203.T",
                "name": "Toyota",
                "amount_jpy": 300_000,
                "reason": "ベース期待値 +5%",
                "current_price": 2000.0,
                "priority": 6,
            }],
        )
        output = format_rebalance_report(proposal)
        # 300000 / 2000 = 150 → round_to_lot_size(150, "7203.T") = 200
        assert "200株" in output

    def test_us_stock_no_lot_annotation(self):
        proposal = _base_proposal(
            additional_cash_jpy=50_000,
            actions=[{
                "action": "increase",
                "symbol": "AAPL",
                "name": "Apple",
                "amount_jpy": 50_000,
                "reason": "reason",
                "current_price": 250.0,
                "priority": 6,
            }],
        )
        output = format_rebalance_report(proposal)
        assert "株単位" not in output

    def test_no_price_no_annotation(self):
        """When current_price is missing, skip annotation gracefully."""
        proposal = _base_proposal(
            additional_cash_jpy=300_000,
            actions=[{
                "action": "increase",
                "symbol": "7203.T",
                "name": "Toyota",
                "amount_jpy": 300_000,
                "reason": "reason",
                "priority": 6,
                # no current_price key
            }],
        )
        output = format_rebalance_report(proposal)
        assert "株単位" not in output

    def test_sell_action_no_annotation(self):
        """Sell actions show '全株' — no share count annotation needed."""
        proposal = _base_proposal(
            freed_cash_jpy=500_000,
            actions=[{
                "action": "sell",
                "symbol": "7203.T",
                "name": "Toyota",
                "ratio": 1.0,
                "reason": "撤退シグナル",
                "value_jpy": 500_000,
                "priority": 1,
            }],
        )
        output = format_rebalance_report(proposal)
        assert "全株" in output
        assert "株単位" not in output
