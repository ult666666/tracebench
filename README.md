# TraceBench

[![Tests](https://github.com/ult666666/tracebench/actions/workflows/ci.yml/badge.svg)](https://github.com/ult666666/tracebench/actions/workflows/ci.yml)

**Inspect recorded AI outputs before a prompt change ships.** TraceBench is a
small offline evaluator: join cases to outputs by ID, apply deterministic checks,
calculate explicitly priced token costs, and stop on baseline regressions.

Python 3.11+ · standard library only · no provider calls or credentials · MIT

The included English/Mandarin dataset is synthetic. Its token counts, latency
observations, and prices are invented demonstration inputs, not model benchmarks
or current provider prices. This is an educational engineering portfolio project,
developed with AI assistance and covered by the checks in
[VERIFICATION](docs/VERIFICATION.md); it has no production-use claim.

## Run the bilingual demo

From this checkout, with Python 3.11+ and pip available:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --no-index .
mkdir -p reports
.venv/bin/tracebench evaluate --cases fixtures/cases.jsonl --outputs fixtures/baseline.jsonl --pricing fixtures/pricing.json --report reports/baseline.json
.venv/bin/tracebench evaluate --cases fixtures/cases.jsonl --outputs fixtures/clean.jsonl --pricing fixtures/pricing.json --baseline reports/baseline.json --report reports/clean.json
.venv/bin/tracebench evaluate --cases fixtures/cases.jsonl --outputs fixtures/regression.jsonl --pricing fixtures/pricing.json --baseline reports/baseline.json --format markdown --report reports/regression.md
```

The commands exit **0, 0, 3**, respectively. The last command deliberately fails
the English greeting and the Mandarin location check. Run `echo $?` immediately
after it to see the regression exit. On Windows, use `.venv\Scripts\python` and
`.venv\Scripts\tracebench` and create `reports` with your shell's equivalent.

Read the tracked [sample regression report](docs/sample-regression.md) without
installing anything, or open the standalone [HTML sample](docs/sample-report.html)
in a browser. The HTML sample is clearly labelled as synthetic recorded-output
demonstration data. The clean candidate passes **6/6**, with supplied mean
latency **150 ms**, nearest-rank p95 **210 ms**, and synthetic known token cost
**0.0000327 USD** across all six cases. Output-file order differs deliberately.

Source execution is also supported: replace `.venv/bin/tracebench` with
`python3 -m tracebench`. Installation uses a project-specific standard-library
build backend, so `--no-index` performs no dependency downloads. Editable
installation is not supported.

## Inputs and checks

One UTF-8 JSON object per line; trailing newline is allowed, blank rows are not.

```json
{"id":"greeting","input":"请回答你好","checks":[{"type":"exact","expected":"你好"}]}
```

```json
{"id":"greeting","output":"你好","metrics":{"latency_ms":120.5,"input_tokens":10,"output_tokens":2}}
```

| Check | Meaning |
| --- | --- |
| `exact` | String equality, including case, whitespace, and Unicode code points |
| `contains` | Nonempty literal substring in a string output |
| `json_subset` | Recursive object subset; arrays retain exact length and order; booleans differ from numbers |

Every check must pass for a case to pass. A JSON subset checks a structured
`output` value, not a string containing JSON. No implicit parsing, case folding,
Unicode normalization, or semantic grading happens.

Unknown fields, duplicate keys or IDs, mismatched ID sets, non-finite values,
invalid UTF-8/surrogates, negative observations, and fractional token counts
are errors. Metrics are optional; token counts must appear together. Full
[schemas and limits](docs/SCHEMAS.md) describe the boundary contract.

Pricing is separate and explicit; both rates are decimal strings per million
tokens. TraceBench does not retrieve prices or infer token counts.

```json
{"currency":"USD","input_per_million":"0.10","output_per_million":"0.30"}
```

## CLI and automation

```text
tracebench evaluate --cases PATH --outputs PATH
    [--pricing PATH] [--baseline PATH]
    [--format json|markdown|html] [--report PATH]
tracebench --version
```

Reports go to stdout by default. `--report` atomically replaces a file in an
existing directory and refuses to overwrite any input. Errors go to stderr;
invalid input produces no report. JSON preserves exact decimal numbers and
escapes HTML-sensitive characters. Markdown escapes untrusted content, including
HTML, table separators, links, control characters, and formatting. Preview text
is truncated; JSON and HTML retain full recorded outputs.

For a self-contained report that can be saved, reviewed offline, and printed:

```sh
.venv/bin/tracebench evaluate --cases fixtures/cases.jsonl --outputs fixtures/regression.jsonl --pricing fixtures/pricing.json --baseline reports/baseline.json --format html --report reports/regression.html
```

This example exits **3** for the two known regressions. Omit `--report` to write
HTML to stdout. The report includes exact cost and coverage, nearest-rank latency
metrics, comparison counts, and expandable case outputs and check reasons. Search
by case ID or output and filter by status with keyboard-accessible controls. All
cases remain available without JavaScript; printing expands every case, including
cases hidden by an active filter. Outputs and reasons use full JSON text to retain
quotes, control characters, Unicode and exact decimal numbers without truncation.
Schema v1 reports do not retain case inputs or expected values, so the HTML view
does not reconstruct them.

HTML has no external assets or runtime dependencies. All recorded content is inert
escaped text; a restrictive Content Security Policy allows only the exact embedded
script and stylesheet hashes and blocks network access, forms and frames. The
renderer uses the same validation rules and leaves JSON/Markdown contracts and
all exit codes unchanged. See [HTML reporting](docs/HTML.md) for reproducible
sample generation and optional real-browser verification.

| Exit | Meaning and precedence |
| --- | --- |
| `0` | All checks pass; no regression |
| `1` | At least one failed case; no pass-to-fail regression |
| `2` | Invalid input, incompatible baseline, usage, or I/O error |
| `3` | At least one pass-to-fail regression against a compatible baseline |

A baseline is a prior **JSON report** for the same case suite. Comparison joins
by ID, rejects missing/extra cases, and verifies a canonical suite fingerprint.
Changed prompts, descriptions, or checks require a fresh baseline. Existing
failures remain exit 1; improvements do not cancel a regression.

## Reviewer path

- [Architecture](docs/ARCHITECTURE.md): data flow, validation, baseline compatibility, packaging.
- [Methodology and limitations](docs/METHODOLOGY.md): exact formulas, coverage, and statistical limits.
- [Library API](docs/API.md): a complete offline example.
- [HTML reporting](docs/HTML.md): offline inspection, security, printing, and sample reproduction.
- [中文指南](docs/README.zh-CN.md): 快速运行与结果解释。
- [Verification record](docs/VERIFICATION.md): actual tests and installed CLI checks.

```sh
python3 -m unittest discover -v
```

The suite tests file boundaries, multilingual behavior, hand-computed metrics,
malformed baselines, report escaping, actual subprocess exits, and wheel/source
archive builds. GitHub Actions targets Python 3.11 and 3.13 with read-only
permissions. See [contributing](CONTRIBUTING.md) and [security](SECURITY.md).
