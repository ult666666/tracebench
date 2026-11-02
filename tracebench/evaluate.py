"""Evaluation, honest metric coverage, and compatible baseline comparison."""

from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
import hashlib
import json
import math
import re

from .checks import run_check
from .io import InputError, fields, valid_id, validate_case, validate_json, validate_output, validate_pricing
from .paired import (GATES, POWER_TEXT, REASONS, critical_regressions, detectable_effect, gate_fails,
                     gate_options, mcnemar, min_discordant, percentile_interval, resample_sums)

_ARITHMETIC = Context(prec=512, rounding=ROUND_HALF_EVEN)
# p-values and detectable effects keep six significant digits at any magnitude.
_SIGNIFICANT = Context(prec=6, rounding=ROUND_HALF_EVEN, Emin=-999999999, Emax=999999999)
REPORT_VERSION = 2
_COMPARISON_V1 = {"baseline_passed", "current_passed", "regressions", "improvements", "unchanged"}
_COMPARISON_V2 = _COMPARISON_V1 | {"statistics", "gate"}
_METRIC = {"pairs", "baseline", "current", "delta", "ci_lower", "ci_upper", "mde"}
_PASS_RATE = _METRIC | {"discordant", "mcnemar_p", "mcnemar_regression_p", "critical_regressions", "min_discordant"}
_SIGNED = re.compile(r"-?[0-9]+(?:\.[0-9]+)?")


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
    return {"schema_version": REPORT_VERSION, "suite_sha256": _fingerprint(cases), "results": results,
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


def _quotient(value):
    """Exact Decimal quotient of a Fraction; call inside a fixed context."""
    return Decimal(value.numerator) / Decimal(value.denominator)


def _rate_text(value):
    with localcontext(_ARITHMETIC):
        return format(_quotient(value), ".6f")


def _mean_text(value):
    with localcontext(_ARITHMETIC):
        return _decimal_text(_quotient(value).quantize(Decimal("0.000001")))


def _total_text(value):
    with localcontext(_ARITHMETIC):
        return _decimal_text(_quotient(value))


def _significant_text(value, fixed=False):
    """Six significant digits, half-even. p-values keep E notation below 1e-6."""
    with localcontext(_SIGNIFICANT):
        rounded = +value if isinstance(value, Decimal) else _quotient(value)
    return _decimal_text(rounded) if fixed else str(rounded)


_TEXT = {"rate": _rate_text, "mean": _mean_text, "total": _total_text}


def _scaled(values):
    """Exact integers value * 10**scale for one shared scale, plus 10**scale."""
    parsed = [Decimal(value).as_tuple() for value in values]
    scale = max([0] + [-exponent for _, _, exponent in parsed])
    integers = []
    for sign, digits, exponent in parsed:
        number = int("".join(map(str, digits)) or "0") * 10 ** (exponent + scale)
        integers.append(-number if sign else number)
    return integers, 10 ** scale


def _metric(before, after, denominator, kind, sums, alpha):
    """Render one paired metric. Rates and means divide by pairs; cost totals do not."""
    pairs = len(before)
    divisor = denominator * (1 if kind == "total" else pairs)
    lower, upper = percentile_interval(sums, alpha)
    effect = detectable_effect([b - a for a, b in zip(before, after)], alpha)
    if effect is not None:
        with localcontext(_ARITHMETIC):
            effect = effect * (pairs if kind == "total" else 1) / denominator
    text = _TEXT[kind]
    block = {"pairs": pairs, "baseline": text(Fraction(sum(before), divisor)), "current": text(Fraction(sum(after), divisor)),
             "delta": text(Fraction(sum(after) - sum(before), divisor)),
             "ci_lower": text(Fraction(lower, divisor)), "ci_upper": text(Fraction(upper, divisor)),
             "mde": None if effect is None else _significant_text(effect, fixed=True)}
    return block, (Fraction(lower, divisor), Fraction(upper, divisor))


def _pass_rate(before, after, options, sums=None):
    """Pass-rate block from 0/1 columns sorted by case ID; also returns exact gate inputs."""
    if sums is None:
        sums = resample_sums([[b - a for a, b in zip(before, after)]], options["resamples"], options["seed"])[0]
    regressions = sum(a > b for a, b in zip(before, after))
    improvements = sum(a < b for a, b in zip(before, after))
    block, (lower, upper) = _metric(before, after, 1, "rate", sums, options["alpha"])
    two_sided, regression_side = mcnemar(regressions, improvements)
    ordered = {"pairs": block["pairs"], "discordant": regressions + improvements}
    ordered.update((key, block[key]) for key in ("baseline", "current", "delta", "ci_lower", "ci_upper"))
    ordered.update(mcnemar_p=_significant_text(two_sided), mcnemar_regression_p=_significant_text(regression_side),
                   critical_regressions=critical_regressions(regressions + improvements, options["alpha"]),
                   min_discordant=min_discordant(options["alpha"]), mde=block["mde"])
    exact = {"regressions": regressions, "improvements": improvements, "two_sided_p": two_sided,
             "lower": lower, "upper": upper}
    return ordered, exact


def _gate(options, exact):
    failed = gate_fails(options["gate"], options["alpha"], options["margin"], exact["regressions"],
                        exact["improvements"], exact["two_sided_p"], exact["lower"], exact["upper"])
    return {"policy": options["gate"], "margin": options["margin"], "failed": failed,
            "reason": REASONS[(options["gate"], failed)]}


def _statistics(current, baseline, options):
    """Paired statistics for validated reports with equal case IDs, sorted by ID."""
    ids = sorted(result["id"] for result in current["results"])
    now = {result["id"]: result for result in current["results"]}
    before = {result["id"]: result for result in baseline["results"]}
    if any(len(now[key]["checks"]) != len(before[key]["checks"]) for key in ids):
        raise InputError("baseline check results differ from the current suite")
    weight = math.lcm(*(len(now[key]["checks"]) for key in ids))

    def score(result):
        return sum(check["passed"] for check in result["checks"]) * (weight // len(result["checks"]))

    columns = {"pass_rate": (tuple(ids), [int(before[k]["passed"]) for k in ids], [int(now[k]["passed"]) for k in ids], 1, "rate"),
               "check_pass_rate": (tuple(ids), [score(before[k]) for k in ids], [score(now[k]) for k in ids], weight, "rate")}
    latency = [k for k in ids if now[k]["metrics"]["latency_ms"] is not None and before[k]["metrics"]["latency_ms"] is not None]
    currency = current["summary"]["cost"]["currency"]
    priced = [k for k in ids if now[k]["cost"] is not None and before[k]["cost"] is not None] \
        if currency is not None and currency == baseline["summary"]["cost"]["currency"] else []
    for name, keys, read, kind in [("latency_ms", latency, lambda r: r["metrics"]["latency_ms"], "mean"),
                                   ("cost", priced, lambda r: r["cost"], "total")]:
        if len(keys) >= 2:
            values, denominator = _scaled([read(before[k]) for k in keys] + [read(now[k]) for k in keys])
            columns[name] = (tuple(keys), values[:len(keys)], values[len(keys):], denominator, kind)
    # Metrics over the same cases share one resampling pass (same seed, same indices).
    groups = {}
    for name, column in columns.items():
        groups.setdefault(column[0], []).append(name)
    sums = {}
    for names in groups.values():
        differences = [[b - a for a, b in zip(columns[name][1], columns[name][2])] for name in names]
        sums.update(zip(names, resample_sums(differences, options["resamples"], options["seed"])))
    pass_block, exact = _pass_rate(columns["pass_rate"][1], columns["pass_rate"][2], options, sums["pass_rate"])
    statistics = {"alpha": options["alpha"], "resamples": options["resamples"], "seed": options["seed"],
                  "power": POWER_TEXT, "pass_rate": pass_block}
    for name in ("check_pass_rate", "latency_ms", "cost"):
        if name not in columns:
            statistics[name] = None
            continue
        _, first, second, denominator, kind = columns[name]
        block, _ = _metric(first, second, denominator, kind, sums[name], options["alpha"])
        statistics[name] = {"currency": currency, **block} if name == "cost" else block
    return statistics, exact


def validate_report(report):
    """Reject malformed or internally inconsistent reports of schema 1 or 2.

    Schema 2 adds paired statistics and a gate verdict to comparisons. Every
    value that the report itself determines is recomputed and must match:
    counts, McNemar p-values, the pass-rate bootstrap interval and the gate.
    """
    fields(report, {"schema_version", "suite_sha256", "results", "summary", "comparison"}, where="report")
    validate_json(report, max_depth=128)
    if type(report["schema_version"]) is not int or report["schema_version"] not in (1, REPORT_VERSION):
        raise InputError("unsupported report schema_version; this version reads schema 1 and 2")
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
        fields(comparison, _COMPARISON_V1 if report["schema_version"] == 1 else _COMPARISON_V2, where="comparison")
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
        if report["schema_version"] == REPORT_VERSION:
            _validate_statistics(report)
    return report


def _signed(value, where):
    if not isinstance(value, str) or _SIGNED.fullmatch(value) is None:
        raise InputError(f"report {where} must be a signed decimal string")
    _report_decimal(value.lstrip("-"), where)
    return Fraction(value)


def _validate_metric(block, where, cases, kind):
    keys = _METRIC | ({"currency"} if where == "cost" else set()) | (_PASS_RATE if where == "pass_rate" else set())
    fields(block, keys, where=f"statistics {where}")
    pairs = block["pairs"]
    if type(pairs) is not int or not (pairs == cases if kind == "rate" else 2 <= pairs <= cases):
        raise InputError(f"invalid statistics {where} pair count")
    for key in ("baseline", "current"):
        value = Fraction(_report_decimal(block[key], f"{where} {key}"))
        if kind == "rate" and (value > 1 or re.fullmatch(r"[01]\.[0-9]{6}", block[key]) is None):
            raise InputError(f"statistics {where} {key} must be a six-decimal rate")
    lower, upper = (_signed(block[key], f"{where} {key}") for key in ("ci_lower", "ci_upper"))
    delta = _signed(block["delta"], f"{where} delta")
    if lower > upper or (kind == "rate" and not (-1 <= lower and upper <= 1 and -1 <= delta <= 1)):
        raise InputError(f"statistics {where} interval is inconsistent")
    if block["mde"] is not None and Fraction(_report_decimal(block["mde"], f"{where} mde")) <= 0:
        raise InputError(f"statistics {where} mde must be positive or null")


def _validate_statistics(report):
    """Check schema 2 statistics; recompute everything the report alone determines."""
    comparison = report["comparison"]
    statistics, gate = comparison["statistics"], comparison["gate"]
    fields(statistics, {"alpha", "resamples", "seed", "power", "pass_rate", "check_pass_rate", "latency_ms", "cost"},
           where="statistics")
    fields(gate, {"policy", "margin", "failed", "reason"}, where="gate")
    if gate["policy"] not in GATES or type(gate["failed"]) is not bool:
        raise InputError("invalid report gate")
    options = gate_options(gate["policy"], statistics["alpha"], gate["margin"], statistics["resamples"], statistics["seed"])
    if (options["alpha"], options["margin"]) != (statistics["alpha"], gate["margin"]) or statistics["power"] != POWER_TEXT:
        raise InputError("report statistics options must be normalized")
    results = sorted(report["results"], key=lambda result: result["id"])
    cases = len(results)
    regressions, improvements = set(comparison["regressions"]), set(comparison["improvements"])
    after = [int(result["passed"]) for result in results]
    before = [state + (result["id"] in regressions) - (result["id"] in improvements) for state, result in zip(after, results)]
    expected, exact = _pass_rate(before, after, options)
    _validate_metric(statistics["pass_rate"], "pass_rate", cases, "rate")
    if {k: v for k, v in statistics["pass_rate"].items() if k != "mde"} != {k: v for k, v in expected.items() if k != "mde"}:
        raise InputError("report pass-rate statistics disagree with the comparison")
    if gate != _gate(options, exact):
        raise InputError("report gate disagrees with the recomputed decision")
    _validate_metric(statistics["check_pass_rate"], "check_pass_rate", cases, "rate")
    weight = math.lcm(*(len(result["checks"]) for result in results))
    scored = sum(sum(check["passed"] for check in result["checks"]) * (weight // len(result["checks"])) for result in results)
    if statistics["check_pass_rate"]["current"] != _rate_text(Fraction(scored, weight * cases)):
        raise InputError("report check pass rate disagrees with check results")
    for name, kind in (("latency_ms", "mean"), ("cost", "total")):
        if statistics[name] is not None:
            _validate_metric(statistics[name], name, cases, kind)
    cost = statistics["cost"]
    if cost is not None and (report["summary"]["cost"]["currency"] is None or cost["currency"] != report["summary"]["cost"]["currency"]):
        raise InputError("report cost statistics currency disagrees with the summary")


def compare_baseline(current, baseline, *, gate=None, alpha=None, margin=None, resamples=None, seed=None):
    """Join by case ID and add paired statistics and a gate verdict (report schema 2).

    Incompatible suites are input errors, never silent skips. Options are
    validated by tracebench.paired.gate_options; defaults keep the any-regression
    gate. The current report must come from evaluate (schema 2); baselines may be
    schema 1 or 2.
    """
    options = gate_options(gate, alpha, margin, resamples, seed)
    validate_report(current)
    validate_report(baseline)
    if current["schema_version"] != REPORT_VERSION:
        raise InputError("the current report must be schema 2; re-run evaluate")
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
    statistics, exact = _statistics(current, baseline, options)
    return {"baseline_passed": baseline["summary"]["passed"], "current_passed": current["summary"]["passed"],
            "regressions": regressions, "improvements": improvements,
            "unchanged": len(current_map) - len(regressions) - len(improvements),
            "statistics": statistics, "gate": _gate(options, exact)}


def outcome(report):
    """Exit status of a validated report: 0 accepted, 1 failed cases, 3 gate failure.

    Without a baseline, or with the default any-regression gate, the 0.4 rules
    hold: 3 for any pass-to-fail regression, else 1 for any failed case. A
    statistical gate replaces both: 3 when it fails and 0 when it passes, even
    if some cases fail, because the gate judges change against the baseline.
    """
    comparison = report["comparison"]
    if comparison is not None:
        gate = comparison.get("gate")
        if gate is not None and gate["policy"] != "any-regression":
            return 3 if gate["failed"] else 0
        if comparison["regressions"]:
            return 3
    return 1 if report["summary"]["failed"] else 0
