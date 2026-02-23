"""Tests for src.core.ticker_utils (KIK-473: extract_all_symbols)."""

from src.core.ticker_utils import extract_all_symbols


class TestExtractAllSymbols:
    def test_single_symbol(self):
        result = extract_all_symbols("NVDAが急騰した")
        assert result == ["NVDA"]

    def test_multiple_symbols(self):
        result = extract_all_symbols("NVDAとAAPLが上がった。7203.Tは下落")
        assert set(result) == {"NVDA", "AAPL", "7203.T"}

    def test_no_symbols(self):
        result = extract_all_symbols("今日はトレードしない")
        assert result == []

    def test_duplicate_removal(self):
        result = extract_all_symbols("NVDAが上がった。NVDAの決算も良い")
        assert result == ["NVDA"]

    def test_suffix_symbols(self):
        result = extract_all_symbols("D05.SIとSINT.SIを買った")
        assert set(result) == {"D05.SI", "SINT.SI"}

    def test_empty_string(self):
        result = extract_all_symbols("")
        assert result == []
