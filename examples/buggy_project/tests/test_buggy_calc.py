import pytest
from buggy_calc import add, average, divide


def test_add_sums_operands() -> None:
    assert add(2, 3) == 5


def test_divide_by_zero_raises_value_error() -> None:
    with pytest.raises(ValueError):
        divide(1, 0)


def test_average_rounds_to_two_decimals() -> None:
    assert average([1, 2, 4]) == 2.33
