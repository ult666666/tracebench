# Verification record

Recorded on **2026-10-23**, locally on macOS. Tests were run with **Python
3.13.7** in an isolated virtual environment and **Python 3.15.0** from the
checkout. These are execution results, not model performance benchmarks.

## Automated suite

```sh
python3 -m unittest discover
.venv/bin/python -m unittest discover -v
```

Both commands completed successfully: **47 tests, zero failures/errors**.

| Area | Tests | Behavior exercised |
| --- | --- | --- |
| Strict input boundaries | 16 | Unicode, duplicate IDs/keys, unknown/missing fields, invalid UTF-8, oversized rows, bad metrics, NaN/Infinity, pricing |
| Evaluation and baselines | 17 | Literal multilingual checks, Boolean/number distinction, arrays, exact ID joins, hand-computed Decimal cost and latency, missing coverage, invalid baselines, deep-output compatibility |
| Serialization and decimal context | 4 | Hostile HTML/link/table/code content, exact JSON decimals, deterministic reports, fixed rounding |
| Real CLI subprocesses | 8 | Exit 0/1/2/3, saved Markdown/JSON, malformed input, missing baseline IDs, input overwrite protection, failed writes, usage/version |
| Packaging | 2 | Wheel/archive contents and actual module execution from the wheel outside checkout |

Tests were introduced before the corresponding modules. Initial runs failed
because implementations were absent. A later deep-output baseline regression
test exposed an overly strict report-wrapper nesting limit; it failed before
the fix and passed afterward. No external test dependencies or providers were
used. These tests do not constitute exhaustive fuzzing or a security audit.

## Actual offline installation

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install --no-index .
.venv/bin/python scripts/verify_demo.py --cli .venv/bin/tracebench
```

Installation built and installed **tracebench 0.1.0** without fetching packages.
After the final code fix, `pip install --no-index --force-reinstall .` was also
run successfully. The verifier invokes the **installed console script** from a
temporary working directory outside the checkout, using absolute fixture paths:

```text
Installed CLI verified outside checkout: baseline=0 clean=0 regression=3 failure=1 invalid=2; clean=6/6, mean=150ms, cost=0.0000327 USD
```

The same process was verified from a source archive in a second fresh venv:

```sh
mkdir -p dist
.venv/bin/python -c 'import build_backend; print(build_backend.build_sdist("dist"))'
python3.13 -m venv .venv-sdist
.venv-sdist/bin/python -m pip install --no-index dist/tracebench-0.1.0.tar.gz
.venv-sdist/bin/python scripts/verify_demo.py --cli .venv-sdist/bin/tracebench
```

Archive installation succeeded, and the same installed-CLI assertions passed.
Virtual environments, archives, and generated reports are ignored by Git.

## Documented demo and API

The README commands were run individually with installed `tracebench`:

| Fixture | Baseline | Exit | Observed result |
| --- | --- | --- | --- |
| `baseline.jsonl` | None | 0 | 6/6 pass, JSON report saved |
| `clean.jsonl` | Saved baseline JSON | 0 | 6/6 pass, 150 ms mean, p50 140 ms, p95 210 ms, 0.0000327 USD known cost |
| `regression.jsonl` | Saved baseline JSON | 3 | 4/6 pass; regressions `en-greeting`, `zh-location`; Markdown saved |

The tracked [sample regression report](sample-regression.md) was generated using:

```sh
.venv/bin/tracebench evaluate --cases fixtures/cases.jsonl --outputs fixtures/regression.jsonl --pricing fixtures/pricing.json --baseline reports/baseline.json --format markdown --report docs/sample-regression.md
```

It exited 3 as expected. The Python code block in [API.md](API.md) was executed
and asserted 6/6 passes, exact cost, no regressions, and JSON/Markdown writes.
The installed verifier additionally checked exit 1 without a baseline and exit 2
for non-finite input, with no traceback or report on invalid input.

All fixture observations and prices are synthetic; no provider was timed or
called. No throughput, production tail-latency, statistical quality, or actual
provider-cost claim follows from these results.

## CI and remaining limits

The checked-in workflow runs tests, a no-index fresh-venv install, and the
installed-CLI verifier on **Python 3.11 and 3.13**, with `contents: read`.
Hosted GitHub Actions runs are verified by the publishing workflow separately;
this local record does not claim a hosted run or a local Python 3.11 run.

No fresh independent security audit, Windows execution, high-volume load test,
or adversarial filesystem race test was performed. The build backend supports
wheels/source archives, not editable installs. Baselines have structural and
suite-compatibility checks, not cryptographic authenticity. Refer to
[architecture](ARCHITECTURE.md), [schemas](SCHEMAS.md), and
[methodology](METHODOLOGY.md) for resource, numeric, provenance, and statistical
limits.
