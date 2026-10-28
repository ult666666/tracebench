# TraceBench

[![Tests](https://github.com/ult666666/tracebench/actions/workflows/ci.yml/badge.svg)](https://github.com/ult666666/tracebench/actions/workflows/ci.yml)

**Inspect recorded AI outputs before a prompt change ships.** TraceBench is a
small offline evaluator: join cases to outputs by ID, apply deterministic checks,
calculate explicitly priced token costs, and stop on baseline regressions.

Python 3.11+ · standard library only · no provider calls or credentials · MIT

The bundled English/Mandarin dataset is synthetic: its outputs, token counts,
latencies and prices are invented, not model benchmarks or real prices. This is an
educational portfolio project, built with AI assistance and not used in production.

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

Open the [HTML report preview](https://ult666666.github.io/tracebench/) to search,
filter and expand every case of the regression example. Without installing
anything, you can also read the [sample regression report](docs/sample-regression.md)
or open the standalone [HTML sample](docs/sample-report.html).

The clean candidate passes **6/6**, with a mean latency of **150 ms**, a
nearest-rank p95 of **210 ms** and a token cost of **0.0000327 USD** across all six
cases. Its output file lists the cases in reverse order, to show that outputs are
joined to cases by ID.

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
tracebench policy --evaluation REPORT_JSON --rules RULES_JSON
    [--format json|markdown] [--report PATH]
tracebench --version
```

- Reports go to stdout. `--report` writes a file instead: it atomically replaces
  a file in an existing directory and refuses to overwrite an input.
- Errors go to stderr, and invalid input produces no report.
- JSON keeps exact decimal numbers and escapes HTML-sensitive characters.
- Markdown escapes untrusted content (HTML, table separators, links, control
  characters and formatting) and truncates long outputs. JSON and HTML keep the
  full recorded outputs.

For a self-contained report that can be saved, reviewed offline, and printed:

```sh
.venv/bin/tracebench evaluate --cases fixtures/cases.jsonl --outputs fixtures/regression.jsonl --pricing fixtures/pricing.json --baseline reports/baseline.json --format html --report reports/regression.html
```

This example exits **3** for the two known regressions. Omit `--report` to write
HTML to stdout. The HTML report:

- shows exact cost and coverage, nearest-rank latency, comparison counts, and each
  case's full output and check reasons;
- lets you search by case ID or output and filter by status, with
  keyboard-accessible controls;
- works without JavaScript, and printing expands every case, even ones hidden by
  a filter;
- loads no external assets. Recorded content is escaped text, and a strict
  Content Security Policy blocks network access, forms and frames.

Schema v1 reports do not keep case inputs or expected values, so the HTML view
cannot show them. See [HTML reporting](docs/HTML.md) for sample generation and
browser verification.

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

The [reusable recorded-evaluation workflow](docs/CI.md) uploads JSON, Markdown and
HTML reports, then applies the regression gate. This repository's CI calls it with
clean and deliberately regressed fixtures, and asserts exit 3 for the regression.
Callers pin the workflow and the TraceBench source to the same commit SHA.

## Budgets for recorded observations

Version 0.4.0 adds `tracebench policy`, which checks a saved JSON evaluation
against a budget:

- **Rules file:** strict, versioned JSON with at least one threshold: a minimum
  pass rate, a maximum p95 latency or a maximum total cost. Every threshold in the
  file must pass.
- **Example:** both bundled rule files require a pass rate of 1 and a total cost
  of at most 0.0000327 USD. `budget-pass.json` allows a p95 latency of 210 ms and
  `budget-fail.json` allows 209.999 ms, so the commands below exit **0** and **1**.
- **Exit codes:** **0** accepted; **1** rejected, or a threshold could not be
  checked (missing latencies, token counts or prices, or a currency mismatch);
  **2** invalid rules or report, usage or I/O error.

```sh
.venv/bin/tracebench policy --evaluation reports/clean.json --rules fixtures/budget-pass.json --report reports/policy.json
.venv/bin/tracebench policy --evaluation reports/clean.json --rules fixtures/budget-fail.json --format markdown --report reports/policy-fail.md
```

A policy verdict never changes the evaluation's exit code, and it judges only the
numbers you supplied. The reusable workflow takes an optional `rules` input; see
[CI integration](docs/CI.md), [rules and verdict schemas](docs/SCHEMAS.md) and
[methodology](docs/METHODOLOGY.md).

## Reviewer path

- [Architecture](docs/ARCHITECTURE.md): data flow, validation, baseline compatibility, packaging.
- [Methodology and limitations](docs/METHODOLOGY.md): exact formulas, coverage, and statistical limits.
- [Library API](docs/API.md): a complete offline example.
- [Recorded evaluation CI](docs/CI.md): reusable consumer gate, artifacts, trust and path boundaries.
- [HTML reporting](docs/HTML.md): offline inspection, security, printing, and sample reproduction.
- [中文指南](docs/README.zh-CN.md): 快速运行与结果解释。
- [Verification](docs/VERIFICATION.md): what CI runs on every push, and how to run it locally.

```sh
python3 -m unittest discover -v
```

The suite covers file boundaries, multilingual checks, hand-computed metrics,
malformed baselines, report escaping, real subprocess exit codes, and wheel and
source-archive builds. CI runs it on Python 3.11 and 3.13, along with the
recorded-evaluation gates and a Chromium browser job; the installed package stays
standard-library Python. See [contributing](CONTRIBUTING.md) and [security](SECURITY.md).
