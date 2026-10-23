"""Exact budgets over supplied recorded observations, independent of evaluation."""

from decimal import Decimal
import hashlib
import re

from .evaluate import _decimal_text, validate_report
from .io import InputError, fields, load_json, validate_json
from .report import render_json

RULES_LIMIT = 64 * 1024
EVALUATION_LIMIT = 64 * 1024 * 1024
_RULES = ("min_pass_rate", "max_p95_latency_ms", "max_total_cost")
_DECIMAL = re.compile(r"([0-9]+)(?:\.([0-9]+))?(?:[eE]([+-]?[0-9]+))?")
NOTICE = ("Budgets use only supplied recorded observations. TraceBench does not measure or authenticate "
          "latency, token counts, prices, or output provenance. Acceptance concerns only selected rules; "
          "evaluation failures and regressions remain unchanged.")


def _threshold(value):
    if not isinstance(value, str) or len(value) > 128:
        raise InputError("policy threshold must be a bounded nonnegative decimal string")
    match = _DECIMAL.fullmatch(value)
    if (match is None or len(match[1]) + len(match[2] or "") > 100
            or abs(int(match[3] or "0")) > 100):
        raise InputError("policy threshold requires <=100 digits and exponent magnitude <=100")
    number = Decimal(value)
    if abs(number.adjusted()) > 100:
        raise InputError("policy threshold adjusted exponent magnitude must be <=100")
    return number


def _rule_text(number):
    text = _decimal_text(number)
    return text if len(text.replace(".", "")) <= 100 and len(text) <= 128 else str(number)


def validate_rules(rules):
    """Validate separate schema 1 rules; return normalized strings without mutation."""
    fields(rules, {"schema_version"}, _RULES, "policy rules")
    validate_json(rules)
    if type(rules["schema_version"]) is not int or rules["schema_version"] != 1:
        raise InputError("unsupported policy rules schema_version")
    if not any(name in rules for name in _RULES):
        raise InputError("policy rules require at least one explicit threshold")
    normalized = {"schema_version": 1}
    for name in _RULES:
        if name not in rules:
            continue
        value = rules[name]
        if name == "max_total_cost":
            fields(value, {"currency", "amount"}, where="policy cost")
            if not isinstance(value["currency"], str) or re.fullmatch(r"[A-Z]{3}", value["currency"]) is None:
                raise InputError("policy currency must be three uppercase letters")
            normalized[name] = {"currency": value["currency"], "amount": _rule_text(_threshold(value["amount"]))}
        else:
            number = _threshold(value)
            if name == "min_pass_rate" and number > 1:
                raise InputError("min_pass_rate must be between 0 and 1")
            normalized[name] = _rule_text(number)
    return normalized


def load_rules(path):
    """Read strict UTF-8 rules JSON, bounded to 64 KiB including whitespace."""
    rules = load_json(path, max_bytes=RULES_LIMIT)
    validate_rules(rules)
    return rules


def _at_most(actual, threshold):
    # Integer ratios avoid floats, Decimal rounding and caller context mutation.
    left_n, left_d = Decimal(actual).as_integer_ratio()
    right_n, right_d = Decimal(threshold).as_integer_ratio()
    return left_n * right_d <= right_n * left_d


def evaluate_policy(report, rules):
    """Validate report schema 1 and require every selected rule to pass exactly."""
    validate_report(report)
    thresholds = validate_rules(rules)
    summary = report["summary"]
    results = []
    for name in _RULES:
        if name not in thresholds:
            continue
        threshold = thresholds[name]
        actual, unavailable = None, None
        if name == "min_pass_rate":
            actual = {"passed": summary["passed"], "cases": summary["cases"]}
            numerator, denominator = Decimal(threshold).as_integer_ratio()
            passed = summary["passed"] * denominator >= summary["cases"] * numerator
        elif name == "max_p95_latency_ms":
            latency = summary["latency_ms"]
            if latency["missing"]:
                unavailable = "Complete supplied latency coverage is required."
            else:
                actual = latency["p95"]
                passed = _at_most(actual, threshold)
        else:
            cost = summary["cost"]
            if cost["priced_cases"] != summary["cases"] or cost["missing_token_cases"]:
                unavailable = "Complete supplied token and pricing coverage is required."
            elif cost["currency"] != threshold["currency"]:
                unavailable = "Supplied cost currency does not match the policy currency."
            else:
                actual = {"currency": cost["currency"], "amount": cost["total"]}
                passed = _at_most(cost["total"], threshold["amount"])
        status = "unavailable" if unavailable else ("pass" if passed else "fail")
        results.append({"rule": name, "threshold": threshold, "actual": actual, "status": status,
                        "reason": unavailable or ("Selected threshold is satisfied." if passed else "Selected threshold is not satisfied.")})
    return {"schema_version": 1, "suite_sha256": report["suite_sha256"],
            "evaluation_sha256": hashlib.sha256(render_json(report).encode("utf-8")).hexdigest(),
            "evaluation": {"cases": summary["cases"], "passed": summary["passed"], "failed": summary["failed"],
                           "regressions": len(report["comparison"]["regressions"]) if report["comparison"] else 0},
            "accepted": all(result["status"] == "pass" for result in results), "rules": results, "notice": NOTICE}


def render_policy_markdown(verdict):
    """Render fixed rule names, validated thresholds and exact observed values."""
    evaluation = verdict["evaluation"]
    text = ["# TraceBench recorded-observation policy", "",
            "Policy accepted: " + ("yes" if verdict["accepted"] else "no"),
            f"Failed cases: {evaluation['failed']} / {evaluation['cases']} · Regressions: {evaluation['regressions']}", "",
            f"Suite fingerprint: `{verdict['suite_sha256']}`",
            f"Evaluation fingerprint: `{verdict['evaluation_sha256']}`", "",
            "| Rule | Threshold | Actual | Status | Reason |", "| --- | --- | --- | --- | --- |"]
    for result in verdict["rules"]:
        def display(value):
            if value is None:
                return "unavailable"
            if isinstance(value, dict):
                if "passed" in value:
                    return f"{value['passed']} / {value['cases']}"
                return f"{value['amount']} {value['currency']}"
            return value
        text.append(f"| {result['rule']} | {display(result['threshold'])} | {display(result['actual'])} | {result['status']} | {result['reason']} |")
    return "\n".join(text + ["", verdict["notice"], ""])
