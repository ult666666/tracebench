"""Literal checks: no network, model judge, case folding, or normalization."""

from decimal import Decimal
import json


def _subset(expected, actual, path="$ "):
    path = path.rstrip()
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return f"{path}: expected an object"
        for key, value in expected.items():
            child = f"{path}[{json.dumps(key, ensure_ascii=False)}]"
            if key not in actual:
                return f"{child}: missing key"
            reason = _subset(value, actual[key], child)
            if reason:
                return reason
        return None
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            return f"{path}: array type or length differs"
        for index, (left, right) in enumerate(zip(expected, actual)):
            reason = _subset(left, right, f"{path}[{index}]")
            if reason:
                return reason
        return None
    if isinstance(expected, bool) or isinstance(actual, bool):
        equal = type(expected) is type(actual) and expected == actual
    elif isinstance(expected, (int, float, Decimal)) and isinstance(actual, (int, float, Decimal)):
        equal = Decimal(str(expected)) == Decimal(str(actual))
    else:
        equal = type(expected) is type(actual) and expected == actual
    return None if equal else f"{path}: value or type differs"


def run_check(check, actual):
    """Return a machine boolean and human reason for a validated check."""
    kind, expected = check["type"], check["expected"]
    if kind == "exact":
        passed = isinstance(actual, str) and actual == expected
        reason = "exact match" if passed else "exact string differs (case and whitespace are significant)"
    elif kind == "contains":
        passed = isinstance(actual, str) and expected in actual
        reason = "substring found" if passed else "required literal substring not found in string output"
    else:
        mismatch = _subset(expected, actual)
        passed = mismatch is None
        reason = "JSON subset matches" if passed else mismatch
    return {"type": kind, "passed": passed, "reason": reason}
