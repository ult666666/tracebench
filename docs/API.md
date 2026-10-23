# Library API

The public entry points are small and synchronous. No API key or network
connection is involved. Run this example from the source checkout after install:

```python
from pathlib import Path

from tracebench.evaluate import compare_baseline, evaluate
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

`InputError`, a `ValueError` subclass, indicates schema, numeric, compatibility,
or file-read errors. The CLI maps these and report I/O errors to exit 2.
Library users handle exceptions directly. The renderer expects a valid report;
it is not a replacement for input or baseline validation.

You may construct mappings directly rather than loading files, using the same
record schema. Supply prices as decimal strings or the normalized `Decimal`
rates returned by `load_pricing`. Avoid binary floats when constructing precise
expectations; JSON parsing retains fractional numbers as `Decimal`.

The returned dictionary may contain `Decimal` values inside recorded structured
outputs. Use `render_json`, rather than ordinary `json.dumps`, to preserve exact
numeric values. Normalized metric summaries and costs are plain strings. There
are no timestamps or generated run IDs, so identical inputs yield identical
serialized output on supported Python versions.
