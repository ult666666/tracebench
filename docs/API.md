# Library API

The public entry points are small and synchronous. No API key or network
connection is involved. Run this example from the source checkout after install:

```python
from pathlib import Path

from tracebench.evaluate import compare_baseline, evaluate
from tracebench.html_report import render_html
from tracebench.io import InputError, load_cases, load_json, load_outputs, load_pricing
from tracebench.report import render_json, render_markdown

cases = load_cases("fixtures/cases.jsonl")
pricing = load_pricing("fixtures/pricing.json")
baseline = evaluate(cases, load_outputs("fixtures/baseline.jsonl"), pricing=pricing)
candidate = evaluate(cases, load_outputs("fixtures/clean.jsonl"), pricing=pricing)
candidate["comparison"] = compare_baseline(candidate, baseline)

assert candidate["summary"]["passed"] == 6
assert candidate["summary"]["cost"]["total"] == "0.0000327"
assert candidate["comparison"]["regressions"] == []

Path("reports").mkdir(exist_ok=True)
Path("reports/api.json").write_text(render_json(candidate), encoding="utf-8")
Path("reports/api.md").write_text(render_markdown(candidate), encoding="utf-8")
Path("reports/api.html").write_text(render_html(candidate), encoding="utf-8")
```

| Function | Contract |
| --- | --- |
| `load_cases(path)` | Validate JSONL and return an insertion-ordered dictionary keyed by ID |
| `load_outputs(path)` | Validate output JSONL and return an ID-keyed dictionary |
| `load_pricing(path)` | Validate pricing JSON and return currency plus `Decimal` rates |
| `load_json(path)` | Read a bounded strict JSON document; semantic report validation happens during comparison |
| `evaluate(cases, outputs, *, pricing=None)` | Revalidate mappings, require exact ID sets, return report with null comparison |
| `compare_baseline(current, baseline)` | Validate both reports and suite compatibility, return comparison dictionary without mutating either report |
| `render_json(report)` | Exact-number JSON with HTML-sensitive strings escaped and trailing newline |
| `render_markdown(report)` | Escaped readable report with 300-character output previews |
| `render_html(report: dict) -> str` | Validated standalone HTML with full escaped JSON outputs/reasons, fixed hashed CSP, optional search/filter script and print CSS |

`InputError`, a `ValueError` subclass, indicates schema, numeric, compatibility,
or file-read errors. The CLI maps these and report I/O errors to exit 2.
Library users handle exceptions directly. JSON/Markdown renderers expect valid
reports; the HTML renderer also calls `validate_report` before presenting metrics.
Rendering is not a replacement for validating case and output inputs.

You may construct mappings directly rather than loading files, using the same
record schema. Supply prices as decimal strings or the normalized `Decimal`
rates returned by `load_pricing`. Avoid binary floats when constructing precise
expectations; JSON parsing retains fractional numbers as `Decimal`.

The returned dictionary may contain `Decimal` values inside recorded structured
outputs. Use `render_json`, rather than ordinary `json.dumps`, to preserve exact
numeric values. Normalized metric summaries and costs are plain strings. There
are no timestamps or generated run IDs, so identical inputs yield identical
serialized output on supported Python versions.

`render_html` does not mutate the report or change schema v1. It preserves exact
Decimal serialization through the existing JSON serializer. Outputs are full JSON
values; reasons are JSON strings, which avoids HTML parser normalization of leading
newlines, CR and NUL. Case inputs and expected values are absent from report v1 and
are explicitly labelled as unavailable. All supplied dynamic values occupy escaped
text nodes; only fixed status values appear in attributes. No report data is embedded
in JavaScript or CSS. See [HTML reporting](HTML.md) for the optional browser verifier.

## Recorded-observation policy (0.4.0)

```python
from tracebench.policy import evaluate_policy, load_rules, render_policy_markdown, validate_rules

verdict = evaluate_policy(candidate, load_rules("fixtures/budget-pass.json"))
assert verdict["accepted"] is True
assert verdict["evaluation"]["failed"] == 0
Path("reports/policy.json").write_text(render_json(verdict), encoding="utf-8")
Path("reports/policy.md").write_text(render_policy_markdown(verdict), encoding="utf-8")
```

`evaluate_policy(report, rules)` first runs the existing schema 1 report validator,
then validates the separate versioned rules. It returns a separate version 1
verdict without mutating either argument. `validate_rules(rules)` returns reusable
normalized rule strings that obey the original bounds and can be passed back to
`validate_rules`, `evaluate_policy`, or saved for the CLI. Equal numeric thresholds
normalize identically without ambient Decimal rounding. `load_rules(path)`
validates strict JSON up to 64 KiB and
returns the parsed rules. `render_policy_markdown(verdict)` expects a verdict from
`evaluate_policy`; `render_json` also serializes verdicts.

All selected rules must pass. Missing/partial latency or token/pricing coverage,
and a cost-currency mismatch, yield `unavailable` and reject the policy. A selected
minimum pass rate uses exact integer counts rather than the rounded display.
Comparisons use integer ratios and cross-products, with no floats or caller
Decimal-context changes. Equal thresholds pass. Cost and latency remain supplied
observations. A policy can accept selected budgets while evaluation cases still
fail; the verdict always shows those failure and regression counts.

`evaluation_sha256` hashes UTF-8 bytes from `render_json(report)`, including its
trailing newline. This identifies that deterministic report serialization, not
the original input file's whitespace, a semantic canonicalization of arbitrary
JSON, or authenticated provenance. The suite fingerprint remains unchanged.
