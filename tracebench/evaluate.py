"""Evaluation, honest metric coverage, and compatible baseline comparison."""

from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
import hashlib
import json
import re

from .checks import run_check
from .io import InputError, fields, valid_id, validate_case, validate_json, validate_output, validate_pricing

_ARITHMETIC = Context(prec=512, rounding=ROUND_HALF_EVEN)


def _decimal_text(value):
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _canonical(value):
    if value is None:
        return ["null"]
    if isinstance(value, bool):
        return ["bool", value]
    if isinstance(value, (int, float, Decimal)):
        return ["number", _decimal_text(Decimal(str(value)))]
    if isinstance(value, str):
        return ["string", value]
    if isinstance(value, list):
        return ["array", [_canonical(v) for v in value]]
    return ["object", [[k, _canonical(value[k])] for k in sorted(value)]]


def _fingerprint(cases):
    encoded = json.dumps(_canonical([cases[k] for k in sorted(cases)]), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _summarize(results, currency):
    count = len(results)
    passed = sum(r["passed"] for r in results)
    observations = sorted(Decimal(r["metrics"]["latency_ms"]) for r in results if r["metrics"]["latency_ms"] is not None)
    observed = len(observations)
    latency = {"observed": observed, "missing": count - observed,
               "min": None, "max": None, "mean": None, "p50": None, "p95": None}
    with localcontext(_ARITHMETIC):
        if observations:
            latency.update(min=_decimal_text(observations[0]), max=_decimal_text(observations[-1]),
                           mean=_decimal_text((sum(observations) / observed).quantize(Decimal("0.000001"))),
                           p50=_decimal_text(observations[(observed * 50 + 99) // 100 - 1]),
                           p95=_decimal_text(observations[(observed * 95 + 99) // 100 - 1]))
        costs = [Decimal(r["cost"]) for r in results if r["cost"] is not None]
        cost = {"currency": currency, "total": _decimal_text(sum(costs)) if costs else None,
                "priced_cases": len(costs),
                "missing_token_cases": sum(r["metrics"]["input_tokens"] is None for r in results)}
        pass_rate = format(Decimal(passed) / count, ".6f")
    return {"cases": count, "passed": passed, "failed": count - passed,
            "pass_rate": pass_rate, "latency_ms": latency, "cost": cost}


def evaluate(cases, outputs, *, pricing=None):
    """Evaluate ID-keyed mappings from load_cases/load_outputs. Does not mutate inputs.

    Returned reports contain JSON values plus finite Decimal output values;
    use render_json for exact numeric serialization. Metric summaries and costs
    are decimal strings with explicit units in their field names.
    """
    if not isinstance(cases, dict) or not cases or not isinstance(outputs, dict):
        raise InputError("cases must be a nonempty ID mapping and outputs an ID mapping")
    for mapping, validator in ((cases, validate_case), (outputs, validate_output)):
        for key, row in mapping.items():
            validator(row)
            if key != row["id"]:
                raise InputError("mapping key must match record id")
    missing, extra = sorted(cases.keys() - outputs.keys()), sorted(outputs.keys() - cases.keys())
    if missing or extra:
        raise InputError(f"output IDs differ: missing={missing!r}; extra={extra!r}")
    rates = validate_pricing(pricing, normalized=True) if pricing is not None else None
    results = []
    with localcontext(_ARITHMETIC):
        for case_id, case in cases.items():
            row = outputs[case_id]
            checks = [run_check(check, row["output"]) for check in case["checks"]]
            source_metrics = row.get("metrics", {})
            metrics = {"latency_ms": _decimal_text(Decimal(str(source_metrics["latency_ms"]))) if "latency_ms" in source_metrics else None,
                       "input_tokens": source_metrics.get("input_tokens"), "output_tokens": source_metrics.get("output_tokens")}
            cost = None
            if rates is not None and metrics["input_tokens"] is not None:
                cost = _decimal_text((metrics["input_tokens"] * rates["input_per_million"]
                                      + metrics["output_tokens"] * rates["output_per_million"]) / 1_000_000)
            results.append({"id": case_id, "passed": all(c["passed"] for c in checks), "checks": checks,
                            "output": row["output"], "metrics": metrics, "cost": cost})
    return {"schema_version": 1, "suite_sha256": _fingerprint(cases), "results": results,
            "summary": _summarize(results, rates["currency"] if rates else None), "comparison": None}


def _report_decimal(value, field):
    if not isinstance(value, str) or len(value) > 512:
        raise InputError(f"report {field} must be a finite decimal string")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise InputError(f"report {field} is not decimal") from exc
    if not number.is_finite() or number < 0 or abs(number.adjusted()) > 300 or len(number.as_tuple().digits) > 512:
        raise InputError(f"report {field} must be finite and nonnegative")
    return number


def validate_report(report):
    """Reject malformed or internally inconsistent baseline reports."""
    fields(report, {"schema_version", "suite_sha256", "results", "summary", "comparison"}, where="report")
    validate_json(report, max_depth=128)
    if type(report["schema_version"]) is not int or report["schema_version"] != 1:
        raise InputError("unsupported report schema_version")
    if not isinstance(report["suite_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", report["suite_sha256"]):
        raise InputError("report suite fingerprint must be a SHA-256 hex string")
    if not isinstance(report["results"], list) or not report["results"]:
        raise InputError("report results must be a nonempty list")
    seen = set()
    for result in report["results"]:
        fields(result, {"id", "passed", "checks", "output", "metrics", "cost"}, where="report result")
        valid_id(result["id"])
        if result["id"] in seen:
            raise InputError(f"duplicate baseline id {result['id']!r}")
        seen.add(result["id"])
        if type(result["passed"]) is not bool:
            raise InputError("report passed must be boolean")
        if not isinstance(result["checks"], list) or not 1 <= len(result["checks"]) <= 100:
            raise InputError("report checks must contain 1 to 100 results")
        for check in result["checks"]:
            fields(check, {"type", "passed", "reason"}, where="report check")
            if check["type"] not in ("exact", "contains", "json_subset") or type(check["passed"]) is not bool or not isinstance(check["reason"], str):
                raise InputError("invalid report check")
        if result["passed"] != all(c["passed"] for c in result["checks"]):
            raise InputError("report case status disagrees with checks")
        metrics = result["metrics"]
        fields(metrics, {"latency_ms", "input_tokens", "output_tokens"}, where="report metrics")
        restored = {k: v for k, v in metrics.items() if v is not None}
        if metrics["latency_ms"] is not None:
            # Fixed notation can add coefficient zeros (1e100 becomes 101
            # digits). Remove them exactly before reapplying input bounds.
            # Report decimals have at most 512 digits, so this fixed context
            # cannot round or depend on the caller's Decimal settings.
            restored["latency_ms"] = _report_decimal(metrics["latency_ms"], "latency_ms").normalize(context=_ARITHMETIC)
        validate_output({"id": result["id"], "output": result["output"], "metrics": restored})
        if result["cost"] is not None:
            _report_decimal(result["cost"], "cost")
            if metrics["input_tokens"] is None:
                raise InputError("report cost requires observed token counts")
    summary = report["summary"]
    fields(summary, {"cases", "passed", "failed", "pass_rate", "latency_ms", "cost"}, where="report summary")
    for key in ("cases", "passed", "failed"):
        if type(summary[key]) is not int or summary[key] < 0:
            raise InputError("report summary counts must be nonnegative integers")
    fields(summary["cost"], {"currency", "total", "priced_cases", "missing_token_cases"}, where="report cost summary")
    currency = summary["cost"]["currency"]
    if currency is not None and (not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency)):
        raise InputError("invalid report currency")
    if currency is None and any(r["cost"] is not None for r in report["results"]):
        raise InputError("report cost requires currency")
    for section, keys in [(summary["cost"], ("priced_cases", "missing_token_cases")),
                          (summary["latency_ms"], ("observed", "missing"))]:
        if not isinstance(section, dict) or any(type(section.get(k)) is not int for k in keys):
            raise InputError("report metric counts must be integers")
    if summary != _summarize(report["results"], currency):
        raise InputError("report summary disagrees with results")
    comparison = report["comparison"]
    if comparison is not None:
        fields(comparison, {"baseline_passed", "current_passed", "regressions", "improvements", "unchanged"}, where="comparison")
        for key in ("baseline_passed", "current_passed", "unchanged"):
            if type(comparison[key]) is not int or not 0 <= comparison[key] <= len(seen):
                raise InputError("invalid comparison count")
        for key in ("regressions", "improvements"):
            ids = comparison[key]
            if not isinstance(ids, list) or any(not isinstance(i, str) or i not in seen for i in ids) or len(ids) != len(set(ids)):
                raise InputError("invalid comparison IDs")
        regressions, improvements = set(comparison["regressions"]), set(comparison["improvements"])
        statuses = {result["id"]: result["passed"] for result in report["results"]}
        if any(statuses[key] for key in regressions) or any(not statuses[key] for key in improvements):
            raise InputError("comparison IDs disagree with current case statuses")
        if regressions & improvements or comparison["unchanged"] != len(seen) - len(regressions) - len(improvements):
            raise InputError("inconsistent comparison IDs")
        if comparison["current_passed"] != summary["passed"] or comparison["baseline_passed"] - len(regressions) + len(improvements) != summary["passed"]:
            raise InputError("inconsistent comparison counts")
    return report


def compare_baseline(current, baseline):
    """Join by case ID; incompatible suites are input errors, never silent skips."""
    validate_report(current)
    validate_report(baseline)
    current_map = {r["id"]: r["passed"] for r in current["results"]}
    baseline_map = {r["id"]: r["passed"] for r in baseline["results"]}
    missing = sorted(current_map.keys() - baseline_map.keys())
    extra = sorted(baseline_map.keys() - current_map.keys())
    if missing or extra:
        raise InputError(f"baseline IDs differ: missing={missing!r}; extra={extra!r}")
    if current["suite_sha256"] != baseline["suite_sha256"]:
        raise InputError("baseline suite fingerprint differs; regenerate a baseline for these cases")
    regressions = sorted(k for k in current_map if baseline_map[k] and not current_map[k])
    improvements = sorted(k for k in current_map if not baseline_map[k] and current_map[k])
    return {"baseline_passed": baseline["summary"]["passed"], "current_passed": current["summary"]["passed"],
            "regressions": regressions, "improvements": improvements,
            "unchanged": len(current_map) - len(regressions) - len(improvements)}
