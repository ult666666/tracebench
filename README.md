# TraceBench

[![Tests](https://github.com/ult666666/tracebench/actions/workflows/ci.yml/badge.svg)](https://github.com/ult666666/tracebench/actions/workflows/ci.yml)

**Inspect recorded AI outputs before a prompt change ships.** TraceBench is a
small offline evaluator: join cases to outputs by ID, apply deterministic checks,
calculate explicitly priced token costs, and stop on baseline regressions. Version
0.5.0 adds paired statistics: an exact McNemar test, bootstrap confidence
intervals and minimum detectable effects, with gates that tell a real regression
from run-to-run noise.

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
    [--gate any-regression|mcnemar|noninferiority|confident-regression]
    [--alpha DECIMAL] [--margin DECIMAL] [--resamples N] [--seed N]
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

Reports do not keep case inputs or expected values, so the HTML view cannot show
them. See [HTML reporting](docs/HTML.md) for sample generation and
browser verification.

| Exit | Meaning and precedence |
| --- | --- |
| `0` | All checks pass; no regression. With a statistical `--gate`: the gate passed |
| `1` | At least one failed case; no pass-to-fail regression (default gate only) |
| `2` | Invalid input, incompatible baseline, usage, or I/O error |
| `3` | At least one pass-to-fail regression against a compatible baseline. With a statistical `--gate`: the gate failed |

A baseline is a prior **JSON report** for the same case suite. Comparison joins
by ID, rejects missing/extra cases, and verifies a canonical suite fingerprint.
Changed prompts, descriptions, or checks require a fresh baseline. With the
default gate, existing failures remain exit 1 and improvements do not cancel a
regression. Reports are written as schema 2; schema 1 reports from 0.4 are still
read as baselines and by `policy`.

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

## Statistical regression gates (0.5.0)

On a nondeterministic system some cases flip between runs even when nothing
changed, so failing on any single regression mostly flags noise. With a baseline,
every report now includes paired statistics: an exact McNemar test on the cases
that changed status, seeded paired bootstrap intervals for the change in pass
rate, check pass rate, mean latency and total cost, and the minimum detectable
effect for the suite's size. `--gate` chooses what exit 3 means:

| `--gate` | Fails (exit 3) when |
| --- | --- |
| `any-regression` | any case passed in the baseline and fails now (default, the 0.4 behaviour) |
| `mcnemar` | the exact two-sided McNemar p-value is below `--alpha` and regressions outnumber improvements |
| `noninferiority` | the pass-rate interval's lower bound is below `-margin`: the candidate has not shown it is within the margin |
| `confident-regression` | the pass-rate interval's upper bound is below `-margin`: the drop is confidently larger than the margin |

The synthetic demo in `fixtures/paired/` has 100 cases. The baseline passes 80
(so its own evaluation exits 1). The noisy candidate swaps 5 passing and 5
failing cases; the regressed candidate breaks 12 and fixes 1.

```sh
.venv/bin/tracebench evaluate --cases fixtures/paired/cases.jsonl --outputs fixtures/paired/baseline.jsonl --pricing fixtures/pricing.json --report reports/paired-baseline.json
.venv/bin/tracebench evaluate --cases fixtures/paired/cases.jsonl --outputs fixtures/paired/noisy.jsonl --pricing fixtures/pricing.json --baseline reports/paired-baseline.json
.venv/bin/tracebench evaluate --cases fixtures/paired/cases.jsonl --outputs fixtures/paired/noisy.jsonl --pricing fixtures/pricing.json --baseline reports/paired-baseline.json --gate mcnemar
.venv/bin/tracebench evaluate --cases fixtures/paired/cases.jsonl --outputs fixtures/paired/regressed.jsonl --pricing fixtures/pricing.json --baseline reports/paired-baseline.json --gate mcnemar --format markdown
```

These exit **1, 3, 0, 3**. The noisy candidate fails the default gate on its 5
regressions, but its McNemar p-value is 1 and its pass-rate interval is -0.06 to
0.06. The regressed candidate's pass rate falls by 0.11 (95% interval -0.18 to
-0.04, McNemar p = 0.00341797); it is also 4.577 ms slower (interval 2.226 to
7.007) and costs 0.00006 USD more in total. Each table row ends with the detectable
change: at 80% power this suite can only detect pass-rate changes of about 0.09,
so `--gate noninferiority --margin 0.05` rejects even the noisy candidate.

[Methodology](docs/METHODOLOGY.md#paired-statistics-and-statistical-gates-050)
gives the formulas, the references and a simulation of each gate's false-failure
rate and power. In short, on synthetic 100-case suites where 10% of cases flip at
random: `any-regression` failed 99.4% of unchanged suites; `mcnemar`, which is
exact, failed 1.1% (nominal at most 2.5%); and `noninferiority` with margin 0.02
accepted 4.95% of candidates whose true drop equalled the margin (nominal 2.5%),
which is why small suites should use `mcnemar`. Cases are assumed independent, and
the gates judge pass/fail only.

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
source-archive builds. The statistics tests compare exact p-values with hand
derivations and brute-force enumeration, check bootstrap invariants (symmetry,
case-order independence, identical runs never failing) over seeded random suites,
and measure gate error rates by exact computation and simulation. CI runs it on Python 3.11 and 3.13, along with the
recorded-evaluation gates and a Chromium browser job; the installed package stays
standard-library Python. See [contributing](CONTRIBUTING.md) and [security](SECURITY.md).
