# Command-line reference

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

Without installing, `python3 -m tracebench` runs the same CLI from a checkout. Installation uses
a project-specific standard-library build backend, so `pip install --no-index .` downloads
nothing. Editable installation is not supported. On Windows, use `.venv\Scripts\python` and
`.venv\Scripts\tracebench`, and create `reports` with your shell's equivalent of `mkdir -p`.

## Inputs

Cases and outputs are UTF-8 JSONL files with one object per line. A trailing newline is
allowed; blank rows are not. Pricing is a separate JSON document with both rates as decimal
strings per million tokens. TraceBench does not retrieve prices or infer token counts.

Unknown fields, duplicate keys or IDs, mismatched ID sets, non-finite values, invalid UTF-8 or
surrogates, negative observations and fractional token counts are errors. Metrics are optional,
but the two token counts must appear together. [SCHEMAS.md](SCHEMAS.md) has the full contracts
and size limits.

A `json_subset` check compares a structured `output` value, not a string that contains JSON.
No implicit parsing, case folding, Unicode normalization or semantic grading happens.

## Outputs

- Reports go to stdout. `--report` writes a file instead: it atomically replaces a file in an
  existing directory and refuses to overwrite an input.
- Errors go to stderr, and invalid input produces no report.
- JSON keeps exact decimal numbers and escapes HTML-sensitive characters.
- Markdown escapes untrusted content (HTML, table separators, links, control characters and
  formatting) and truncates long outputs. JSON and HTML keep the full recorded outputs.
- HTML is one offline file with search and status filters. It works without JavaScript, prints
  every case, loads no external assets, and blocks network access with a strict Content Security
  Policy. [HTML.md](HTML.md) covers its security boundary and how the sample is verified.

Reports do not keep case inputs or expected values, so no format can show them.

## Exit codes

| Exit | Meaning and precedence |
| --- | --- |
| `0` | All checks pass and there is no regression. With a statistical `--gate`: the gate passed |
| `1` | At least one failed case, and no pass-to-fail regression (default gate only) |
| `2` | Invalid input, incompatible baseline, usage error or I/O error |
| `3` | At least one pass-to-fail regression against a compatible baseline. With a statistical `--gate`: the gate failed |

## Baselines

A baseline is a prior JSON report for the same case suite. The comparison joins cases by ID,
rejects missing or extra cases, and checks a canonical suite fingerprint, so changed prompts,
descriptions or checks need a fresh baseline. With the default gate, existing failures stay exit
1, and improvements do not cancel a regression. Reports are written as schema 2; schema 1
reports from 0.4 are still read as baselines and by `policy`.

## Budgets for recorded observations

`tracebench policy` (added in 0.4.0) checks a saved JSON evaluation against a budget. The rules
file is strict, versioned JSON with at least one threshold: a minimum pass rate, a maximum p95
latency or a maximum total cost. Every threshold in the file must pass.

Both bundled rule files require a pass rate of 1 and a total cost of at most 0.0000327 USD.
`budget-pass.json` allows a p95 latency of 210 ms, the clean candidate's p95. `budget-fail.json`
allows 209.999 ms, so the second command below fails:

```sh
.venv/bin/tracebench policy --evaluation reports/clean.json --rules fixtures/budget-pass.json --report reports/policy.json
.venv/bin/tracebench policy --evaluation reports/clean.json --rules fixtures/budget-fail.json --format markdown --report reports/policy-fail.md
```

`policy` exits 0 when the budget is accepted, 1 when it is rejected or a threshold could not be
checked (missing latencies, token counts or prices, or a currency mismatch), and 2 for invalid
rules or reports, usage errors and I/O errors. A policy verdict never changes the evaluation's
exit code, and it judges only the numbers you supplied. See [METHODOLOGY.md](METHODOLOGY.md) for
the arithmetic and [SCHEMAS.md](SCHEMAS.md) for the rules and verdict formats.
