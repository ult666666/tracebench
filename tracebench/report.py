"""Standalone JSON and inert Markdown serialization of untrusted records."""

from decimal import Context, Decimal, localcontext
import json
import unicodedata

from .io import InputError


def _string(value):
    encoded = json.dumps(value, ensure_ascii=False)
    for char, escaped in [("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"),
                          ("\u2028", "\\u2028"), ("\u2029", "\\u2029")]:
        encoded = encoded.replace(char, escaped)
    return encoded


def _json(value, level=0):
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise InputError("cannot render a non-finite number")
        return str(value)
    if isinstance(value, dict):
        if not value:
            return "{}"
        pad = "  " * (level + 1)
        return "{\n" + ",\n".join(pad + _string(k) + ": " + _json(v, level + 1) for k, v in value.items()) + "\n" + "  " * level + "}"
    if isinstance(value, list):
        if not value:
            return "[]"
        pad = "  " * (level + 1)
        return "[\n" + ",\n".join(pad + _json(v, level + 1) for v in value) + "\n" + "  " * level + "]"
    try:
        return json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise InputError(f"cannot render JSON: {exc}") from exc


def render_json(report):
    """Serialize Decimal numbers exactly and escape HTML-sensitive characters."""
    return _json(report) + "\n"


def escape_markdown(value):
    """Encode punctuation and controls so case content cannot create markup."""
    return "".join(f"&#x{ord(c):X};" if unicodedata.category(c)[0] in {"P", "S", "C", "Z"} and c != " " else c
                   for c in str(value))


_PERCENT = Context(prec=60)


def _percent(value):
    """Decimal fraction as a percentage without trailing zeros; call inside _PERCENT."""
    text = format(value * 100, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


_METRICS = (("pass_rate", "Pass rate"), ("check_pass_rate", "Check pass rate"),
             ("latency_ms", "Mean latency (ms)"), ("cost", "Total cost"))


def _count(number, noun):
    return f"{number} {noun}" + ("" if number == 1 else "s")


def describe_statistics(comparison):
    """Fixed-text pieces describing schema 2 paired statistics; None for schema 1.

    Returns the gate sentence, the method sentence, one row per metric (None
    when unavailable) and the McNemar sentences. Every number is a validated
    decimal string or integer from the report, so the pieces contain no
    recorded case content.
    """
    if comparison is None or "statistics" not in comparison:
        return None
    statistics, gate = comparison["statistics"], comparison["gate"]
    with localcontext(_PERCENT):
        level, power = (_percent(value) for value in (1 - Decimal(statistics["alpha"]), Decimal(statistics["power"])))
    margin = f" (margin {gate['margin']})" if gate["margin"] is not None else ""
    method = (f"Paired statistics: {level}% bootstrap percentile intervals from {statistics['resamples']} resamples "
              f"(seed {statistics['seed']}); detectable change is the smallest true change found with {power}% power.")
    rows = []
    for key, label in _METRICS:
        block = statistics[key]
        if key == "cost" and block is not None:
            label = f"{label} ({block['currency']})"
        rows.append((label, None if block is None else
                     (str(block["pairs"]), block["baseline"], block["current"], block["delta"],
                      f"{block['ci_lower']} to {block['ci_upper']}", block["mde"] or "unavailable")))
    rate = statistics["pass_rate"]
    tests = [f"Exact McNemar test: {_count(len(comparison['regressions']), 'regression')} and "
             f"{_count(len(comparison['improvements']), 'improvement')} among {_count(rate['discordant'], 'discordant pair')}; "
             f"p = {rate['mcnemar_p']} two-sided, "
             f"{rate['mcnemar_regression_p']} in the regression direction.",
             f"A two-sided p below {statistics['alpha']} needs at least {rate['min_discordant']} discordant pairs."]
    if rate["critical_regressions"] is not None:
        tests.append(f"With {_count(rate['discordant'], 'discordant pair')}, the McNemar gate fails only at "
                     f"{rate['critical_regressions']} or more regressions.")
    return {"gate": f"Gate {gate['policy']}{margin}: {'failed' if gate['failed'] else 'passed'}.",
            "reason": gate["reason"], "method": method, "level": level, "rows": rows, "tests": tests}


def render_markdown(report):
    """Render human-readable metrics and inert, truncated output previews."""
    summary = report["summary"]
    latency, cost = summary["latency_ms"], summary["cost"]
    text = ["# TraceBench evaluation", "", "Offline deterministic checks of recorded outputs.", "",
            f"Passed: {summary['passed']} / {summary['cases']} · Failed: {summary['failed']} / {summary['cases']}", "",
            f"Suite fingerprint: `{report['suite_sha256']}`", "",
            f"Latency observations: {latency['observed']} / {summary['cases']} (milliseconds; nearest-rank percentiles)."]
    if latency["observed"]:
        text.append("Mean: " + latency["mean"] + " ms · p50: " + latency["p50"] + " ms · p95: " + latency["p95"] + " ms.")
    else:
        text.append("Latency unavailable; no measurements supplied.")
    if cost["total"] is not None:
        text.append(f"Known token cost: {cost['total']} {cost['currency']} · priced cases: {cost['priced_cases']} / {summary['cases']}.")
    else:
        text.append(f"Token cost unavailable · priced cases: 0 / {summary['cases']}.")
    text.append(f"Cases missing token observations: {cost['missing_token_cases']} / {summary['cases']}.")
    comparison = report["comparison"]
    if comparison is not None:
        text += ["", f"Regressions: {len(comparison['regressions'])} · Improvements: {len(comparison['improvements'])} · Unchanged: {comparison['unchanged']}."]
        for label, key in [("Regression IDs", "regressions"), ("Improvement IDs", "improvements")]:
            if comparison[key]:
                text.append(label + ": " + ", ".join(escape_markdown(i) for i in comparison[key]) + ".")
        described = describe_statistics(comparison)
        if described is not None:
            text += ["", described["gate"] + " " + described["reason"], "", described["method"], "",
                     f"| Metric | Pairs | Baseline | Current | Change | {described['level']}% interval | Detectable change |",
                     "| --- | --- | --- | --- | --- | --- | --- |"]
            for label, row in described["rows"]:
                text.append(f"| {label} | " + (" | ".join(row) if row else "unavailable | | | | | ") + " |")
            text += [""] + described["tests"] + ["Latency and cost need at least two cases observed in both reports; cost also needs one currency."]
    text += ["", "| Case ID | Status | Check results | Recorded output preview |", "| --- | --- | --- | --- |"]
    for result in report["results"]:
        details = "; ".join(f"{c['type']}: {'PASS' if c['passed'] else 'FAIL'} — {c['reason']}" for c in result["checks"])
        output = _json(result["output"])
        if len(output) > 300:
            output = output[:300] + "… (truncated)"
        text.append(f"| {escape_markdown(result['id'])} | {'PASS' if result['passed'] else 'FAIL'} | {escape_markdown(details)} | {escape_markdown(output)} |")
    text += ["", "Costs use only supplied prices and token observations. Partial coverage is not a total bill.",
             "Recorded latency is supplied by the caller; TraceBench does not time a provider or verify provenance.", ""]
    return "\n".join(text)
