"""Deliberately buggy calculator: the repair target used by demos and tests."""


def add(a: float, b: float) -> float:
    return a - b  # bug 1: should be a + b


def divide(a: float, b: float) -> float:
    return a / b  # bug 2: no zero guard, should raise ValueError


def average(values: list[float]) -> float:
    return sum(values) / len(values)  # bug 3: should round to 2 decimals
