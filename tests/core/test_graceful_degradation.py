"""Tests for graceful_degradation decorator (KIK-579)."""

import pytest
from src.core.common import graceful_degradation


class TestGracefulDegradation:
    def test_returns_default_on_exception(self):
        @graceful_degradation(default=[])
        def failing():
            raise ValueError("boom")

        assert failing() == []

    def test_returns_none_by_default(self):
        @graceful_degradation()
        def failing():
            raise RuntimeError("crash")

        assert failing() is None

    def test_returns_normal_value_on_success(self):
        @graceful_degradation(default=[])
        def working():
            return [1, 2, 3]

        assert working() == [1, 2, 3]

    def test_preserves_function_name(self):
        @graceful_degradation()
        def my_func():
            pass

        assert my_func.__name__ == "my_func"

    def test_passes_args_and_kwargs(self):
        @graceful_degradation(default=0)
        def add(a, b, offset=0):
            return a + b + offset

        assert add(1, 2, offset=10) == 13

    def test_catches_import_error(self):
        @graceful_degradation(default=False)
        def import_missing():
            import nonexistent_module  # noqa: F401
            return True

        assert import_missing() is False

    def test_default_false(self):
        @graceful_degradation(default=False)
        def failing():
            raise Exception

        assert failing() is False

    def test_default_empty_dict(self):
        @graceful_degradation(default={})
        def failing():
            raise Exception

        assert failing() == {}

    def test_mutable_list_not_shared(self):
        """Mutable defaults must NOT be shared across calls."""
        @graceful_degradation(default=[])
        def failing():
            raise Exception

        result1 = failing()
        result1.append("modified")
        result2 = failing()
        assert result1 is not result2
        assert result2 == []  # fresh copy, not polluted

    def test_mutable_dict_not_shared(self):
        @graceful_degradation(default={})
        def failing():
            raise Exception

        result1 = failing()
        result1["key"] = "value"
        result2 = failing()
        assert result1 is not result2
        assert result2 == {}
