"""Standalone JSON and inert Markdown serialization of untrusted records."""

from decimal import Decimal
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
