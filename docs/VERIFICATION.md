# Verification record

Recorded on **2026-10-23**, locally on macOS. Tests were run with **Python
3.13.7** in an isolated virtual environment and **Python 3.15.0** from the
checkout. These are execution results, not model performance benchmarks.

## Automated suite

```sh
python3 -m unittest discover
.venv/bin/python -m unittest discover -v
```

Both commands completed successfully after review fixes: **49 tests, zero failures/errors**.

| Area | Tests | Behavior exercised |
| --- | --- | --- |
| Strict input boundaries | 16 | Unicode, duplicate IDs/keys, unknown/missing fields, invalid UTF-8, oversized rows, bad metrics, NaN/Infinity, pricing |
| Evaluation and baselines | 19 | Literal multilingual checks, Boolean/number distinction, arrays, exact ID joins, hand-computed Decimal cost and latency, missing coverage, invalid baselines, deep-output compatibility, contradictory comparison metadata and malformed library keys |
| Serialization and decimal context | 4 | Hostile HTML/link/table/code content, exact JSON decimals, deterministic reports, fixed rounding |
| Real CLI subprocesses | 8 | Exit 0/1/2/3, saved Markdown/JSON, malformed input, missing baseline IDs, input overwrite protection, failed writes, usage/version |
| Packaging | 2 | Wheel/archive contents and actual module execution from the wheel outside checkout |

Tests were introduced before the corresponding modules. Initial runs failed
because implementations were absent. A later deep-output baseline regression
test exposed an overly strict report-wrapper nesting limit; it failed before
the fix and passed afterward. No external test dependencies or providers were
used. These tests do not constitute exhaustive fuzzing or a security audit.

An independent code review found two additional validation gaps: historical
comparison IDs could contradict current case statuses, and mixed non-string
library keys could raise an unintended exception. Both were reproduced with
failing regression tests, repaired, and followed by the full 49-test suite on
Python 3.13.7 and 3.15.0. The installed CLI verifier was rerun after reinstalling
the final source and source archive.

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

## Version 0.2.0: standalone HTML reports

The preceding record describes the historical **0.1.0** verification. On
**2026-10-23**, the HTML feature release **0.2.0** was additionally verified on
macOS with **Python 3.13.7**, **Python 3.15.0**, and real **Chromium
149.0.7827.55** using an already available Playwright installation. No provider
was called or timed, and no Node dependency was added to TraceBench.

```sh
python3.13 -m unittest discover
python3 -m unittest discover
python3 scripts/verify_html.py --require-browser --artifacts reports/html-verification
git diff --check
```

Both Python suite runs completed with **61 tests, zero failures/errors**: the
historical 49 plus 12 HTML tests. Tests cover hostile output/IDs/reasons, exact
Decimal serialization, full string/control preservation, missing measurements,
absent comparison, regressions and improvements, accessible control structure,
determinism/no mutation, consistency validation, real HTML CLI exits 0/1/2/3,
atomic replacement and input protection. Wheel/source-archive tests explicitly
check inclusion of the new module; the source archive also contains the sample.

The initial HTML test run failed because the renderer was missing and the CLI
rejected `--format html`. Browser regression checks then exposed two issues before
their fixes: HTML parsing discarded/normalized leading newlines, CR and NUL in raw
`pre` text; parsing full structured outputs through JavaScript numbers could
invent rounded numeric search matches. Full JSON output/reason text now preserves
control characters, and search decodes only JSON string tokens while keeping
numeric text exact. The failing wheel-version test was also observed before
raising the release version to 0.2.0.

The bounded verifier compares renderer output to real CLI stdout and atomically
saved files, checks known exits and overwrite refusal, and asserts exact bytes of
the committed synthetic sample. Chromium checks exercised:

- Desktop 1280 px and mobile 390/320 px, with expanded outputs and no horizontal
  overflow, including a long hostile output with an unbroken 2048-character token.
- Case ID and full output searches (Unicode, literal markup, structured text,
  exact large decimals, no-match state), every status filter, and live counts.
- Tab navigation, native keyboard selection, and Enter expansion of case content.
- All cases and native expansion with JavaScript disabled.
- Print media: hidden controls, all filtered-out cases restored, full outputs and
  check reasons visible even when blocks were closed; this also passed without JS.
- Hostile `</script><img onerror=...>` content and malicious IDs remained text;
  no injected image/SVG/frame/link/form appeared, no execution marker was set,
  no page errors occurred, and **zero HTTP(S) requests** were observed.

Desktop/mobile screenshots were visually inspected. The verifier saved those
images and an A4 print PDF under ignored `reports/html-verification/`.

Fresh Python 3.13 environments installed **0.2.0** successfully via all three
routes, using `pip install --no-index`: source checkout, generated
`dist/tracebench-0.2.0.tar.gz`, and generated
`dist/tracebench-0.2.0-py3-none-any.whl`. These environments were
`reports/venv-html-final-source`, `reports/venv-html-final-sdist`, and
`reports/venv-html-final-wheel`. Each returned `tracebench 0.2.0`, passed
`scripts/verify_demo.py --cli PATH`, and passed
`scripts/verify_html.py --cli PATH --require-browser` with real Chromium. Both
verifiers launch the installed console script from a temporary directory outside
the checkout. The installed results preserved the clean fixture's 6/6 pass count,
150 ms mean, and exact known cost 0.0000327 USD; known regressions remained exit 3.

The [API example](API.md) was executed including the HTML write. The new
[sample-report.html](sample-report.html) is deterministically regenerated by:

```sh
python3 scripts/verify_html.py --write-sample
```

Its document title and visible banner identify a synthetic recorded-output demo.
The existing CI workflow now also runs the HTML verifier for installed-CLI and
sample-byte checks. It clearly reports optional browser checks as skipped when
the existing tooling is absent; no hosted CI result or Pages publication is
claimed by this local verification record.

Remaining limits: no local Python 3.11 execution, Firefox/Safari/Windows run,
screen-reader audit, high-volume browser benchmark or independent security audit
was performed. Modern Chromium print behavior was verified; older print engines
may need manual expansion. Case inputs and expected values remain unavailable in
schema v1, and observations/prices remain caller-supplied with no provenance claim.
