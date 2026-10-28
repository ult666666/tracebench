# Verification

GitHub Actions runs every check below on each push and pull request. The
[tests workflow page](https://github.com/ult666666/tracebench/actions/workflows/ci.yml)
shows the latest results. Every input is a synthetic fixture from `fixtures/`, and
no model provider is called or timed.

## What CI runs

[`ci.yml`](../.github/workflows/ci.yml) has seven jobs:

| Job | What it checks |
| --- | --- |
| `test (3.11)`, `test (3.13)` | The full `unittest` suite. Then an offline `pip install --no-index .` into a fresh virtual environment, the installed CLI's four exit codes from a directory outside the checkout (`scripts/verify_demo.py`), and the HTML output plus the exact bytes of the committed HTML sample (`scripts/verify_html.py`). |
| Synthetic clean evaluation gate | Calls the [reusable workflow](CI.md) on the clean fixtures and applies the real gate. |
| Verify synthetic regression exits 3 | Runs the regressed fixtures and asserts evaluation exit 3. |
| Synthetic budget accepted by real combined gate | Runs the clean fixtures with `fixtures/budget-pass.json` through the real gate. |
| Verify synthetic budget failure | Runs `fixtures/budget-fail.json` and asserts evaluation exit 0 and policy exit 1. |
| Real HTML browser interactions | Installs the locked Playwright 1.61.1 and Chromium, then checks the HTML report in a real browser. This job fails if the browser checks cannot run. |

[`pages.yml`](../.github/workflows/pages.yml) runs on `main` only. It repeats the
tests and the installed-CLI checks, then publishes the committed synthetic sample
as the [HTML report preview](https://ult666666.github.io/tracebench/).

## Run the same checks locally

```sh
python3 -m unittest discover -v
python3 -m venv .venv
.venv/bin/python -m pip install --no-index .
.venv/bin/python scripts/verify_demo.py --cli .venv/bin/tracebench
.venv/bin/python scripts/verify_html.py --cli .venv/bin/tracebench
```

The browser checks need Node 24 and the locked Playwright in `browser/`:

```sh
npm ci --ignore-scripts --prefix browser
browser/node_modules/.bin/playwright install --with-deps chromium
.venv/bin/python scripts/verify_html.py --cli .venv/bin/tracebench --require-browser --browser-module browser/node_modules/playwright
```

Without Node or the Playwright module, `verify_html.py` skips the browser checks
and says so, unless `--require-browser` is set.

## What the checks cover

- **Inputs:** Unicode, duplicate IDs and keys, unknown or missing fields, invalid
  UTF-8, oversized rows, non-finite numbers, bad metrics and pricing.
- **Evaluation and baselines:** literal checks in English and Mandarin, exact ID
  joins, hand-computed `Decimal` cost and latency, partial coverage, incompatible
  or malformed baselines.
- **Reports:** hostile HTML, link, table and code content stays inert text; exact
  JSON decimals; deterministic output.
- **CLI:** real subprocess runs for evaluation exits 0, 1, 2 and 3 and policy exits
  0, 1 and 2, atomic report writes, and refusal to overwrite an input.
- **Budgets:** inclusive pass-rate, p95-latency and cost boundaries, missing or
  partial observations, wrong currency, and malformed rule files.
- **CI runner:** every gate outcome, path and size limits, symlinks, shell
  metacharacters in paths, and tampered handoff files.
- **Packaging:** wheel and source-archive contents, and the installed console
  script run from outside the checkout.
- **Browser (Chromium):** layouts at 1280, 390 and 320 px, search, every status
  filter, keyboard use, JavaScript turned off, print, hostile markup, and zero
  HTTP(S) requests.

## Not covered

- Real model behavior. Outputs, token counts, latencies and prices are
  caller-supplied numbers; TraceBench does not measure or verify them.
- Windows, Firefox or Safari, a screen-reader audit, load testing and an
  independent security audit.
- Baseline authenticity. Baselines get structural and suite-fingerprint checks,
  not cryptographic signatures.

See [architecture](ARCHITECTURE.md), [schemas](SCHEMAS.md) and
[methodology](METHODOLOGY.md) for resource, numeric and statistical limits.

## Bugs found by review and fixed

New behavior in each version started as a failing test. Code reviews of each
version also found these bugs, which were reproduced with a failing test and then
fixed:

- **0.1.0:** historical comparison IDs could contradict current case statuses,
  and mixed non-string keys in the library API raised an unintended exception.
- **0.2.0:** the HTML sample check normalized CRLF, so it did not prove byte
  equality; a valid latency of `1e100` was rejected when a report was
  revalidated; manual Pages runs lacked a `main`-only guard.
- **0.3.0:** the CI runner read generated reports with a 16 MiB limit while
  advertising 64 MiB, so large valid reports failed.
- **0.4.0:** a CI handoff with its whole policy file set removed could pass as a
  run without budgets; some 100-digit thresholds normalized to a string longer
  than the rules schema allows.

Release notes for each version are on the
[releases page](https://github.com/ult666666/tracebench/releases).
