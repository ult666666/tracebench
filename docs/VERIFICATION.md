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

## 0.2.0 review repair: numeric boundaries, sample bytes and publish ref

Independent review of the HTML feature and Pages workflow found that a valid
latency input `1e100` became a 101-digit fixed string and was then rejected when
report validation reapplied the input coefficient limit. It also found that the
sample verifier's `read_text()` normalized CRLF, so its earlier check did not
establish byte equality, and that manual Pages dispatch lacked an explicit main
ref guard. These three findings were repaired together on **2026-10-23**.

Before the repair, new regressions produced **11 failing subtests**: two accepted
numeric boundary reports, eight real CLI format/baseline combinations, and the
CRLF sample-byte check. The input-limit rejection checks already passed.
Report validation now normalizes only a temporary restored latency Decimal using
the explicit fixed 512-digit context, removing coefficient zeros introduced by
fixed notation before applying the unchanged input validator. Report data,
HTML consistency validation, input limits and exact JSON/Markdown serialization
remain unchanged. Tests use precision 7, exponent bounds ±10 and traps for rounded
or inexact operations to guard against ambient Decimal context dependence.

The sample verifier now compares raw bytes with explicit UTF-8 generation bytes,
and both sample writes use `write_bytes()`. The regression executes the real
verifier and CLI with a temporary fixture root: LF passes and changed CRLF bytes
fail. Running `--write-sample` retained the committed sample exactly, with SHA-256
`0f4bad9a7d8e4ae6bcc1a141f058f4562359a44c07527a05eef5643a4e757ddc`.

Both Pages build and deploy jobs now require
`github.ref == 'refs/heads/main'`, including manual dispatch. The deploy job still
depends on the tested build and consumes its staged synthetic-only artifact.
This is a workflow source change; no hosted dispatch/deployment or environment
protection was inferred from the local checks.

Final local repair verification passed the complete **65-test** suite on both
**Python 3.13.7** and **Python 3.15.0**, with zero failures/errors. New coverage
includes accepted adjusted-exponent ±100 boundaries with one and 100 coefficient
digits, zero, a 100-digit integer/token count, JSON report round-trips, compatible
baseline comparison and HTML rendering. Real CLI checks cover all three formats
with and without a baseline. Beyond-boundary exponents, 101 significant digits,
and overlong input representations remain rejected. Validation and rendering do
not mutate either JSON or Markdown output.

Fresh Python 3.13 environments under `reports/venv-html-review-source`,
`reports/venv-html-review-sdist` and `reports/venv-html-review-wheel` each installed
**0.2.0** with `pip install --no-cache-dir --no-index`, from the source checkout,
generated source archive and wheel respectively. Each installed console script
ran outside the checkout and passed the original demo, HTML verifier and real
**Chromium 149.0.7827.55** checks. Each also passed **24 accepted-boundary
format/baseline combinations** and **9 rejected-boundary format checks** through
the installed CLI. The original fixture remains 6/6, 150 ms mean and exactly
0.0000327 USD; all exit-code, atomic-write, escaping, responsive, keyboard,
no-JavaScript, print and zero-HTTP(S)-request checks passed again.

The prior platform, accessibility, high-volume and independent-audit limitations
still apply. The repair was committed locally for scoped independent re-review;
publishing and hosted verification remain separate work.

## 0.3.0: reusable recorded-evaluation CI (local evidence)

On **2026-10-23**, the consumer CI feature was verified locally against the
unchanged 0.2.0 report/schema contracts. The clean base had **65** passing tests.
Seven new runner behavior tests were written first: the positive boundary cases
initially failed because `scripts/ci_evaluate.py` did not exist. After implementing
the runner, the complete **72-test** suite passed on **Python 3.13.7** and
**Python 3.15.0**. Subsequent red/green checks proved clear option diagnostics and
rejection of a changed successful-looking gate status for a regression report.
Version packaging tests failed against 0.2.0 before metadata/runtime moved to
0.3.0, then passed. JSON/Markdown schema and rendering were not changed.

Actual child-process tests cover normal exits 0/1/3, expected-regression assertion,
invalid records, missing/nonregular/oversize files, symlink files/directories,
traversal/private/runtime paths, literal shell metacharacters, spaces and leading
hyphens, preserved input bytes, copied artifact handoff, tampered files/metadata,
and outside-directory gates. The actual embedded pre-checkout Python option block
was additionally executed with **11** controlled valid/invalid cases, verifying
immutable SHA validation, finite expectation choices and artifact-name/output
injection rejection before any source checkout. `actionlint 1.7.7` and
`git diff --check` passed; actionlint was downloaded from its official GitHub
release and matched that release's published checksum.

Fresh Python 3.13 environments installed **0.3.0** from the source checkout,
generated wheel and generated source archive with
`pip install --no-cache-dir --no-index`. Each console script and imported metadata
reported 0.3.0 from outside the checkout. Each installed interpreter ran the new
runner outside the checkout without `PYTHONPATH`, generated all three reports,
handed them off for upload, propagated normal **0/1/3**, and passed only the
explicit expected-3 verification. The original installed demo still produced
baseline=0, clean=0, regression=3, check failure=1, invalid=2; clean results remain
6/6, mean 150 ms and known synthetic cost 0.0000327 USD. The wheel contains only
Python package and dist-info files, with no runtime dependency metadata.

With **Node 24.18.0**, `npm ci --ignore-scripts --prefix browser` installed the
exact **Playwright 1.61.1** lock, and the existing actual browser verifier ran
against all three fresh installed CLIs using `--require-browser`.
**Chromium 149.0.7827.55** passed desktop/mobile 1280/390/320 px layout, search,
all filters, live counts, keyboard operation, no-JavaScript details, print,
hostile text round-trip, markup injection rejection and zero HTTP(S) requests.
Desktop/mobile screenshots and print PDFs were generated as explicit synthetic
artifacts. The committed HTML sample retains SHA-256
`0f4bad9a7d8e4ae6bcc1a141f058f4562359a44c07527a05eef5643a4e757ddc`.
The main-only Pages workflow, including its per-ref concurrency fix, is unchanged.

The reusable workflow's source was cross-checked with the official GitHub and
Playwright references linked in [CI integration](CI.md). Its self-CI callers use
separate clean and expected-regression jobs; the latter explicitly asserts 3 and
does not weaken the normal gate. External usage pins both workflow and package
source to an immutable commit containing the referenced scripts.

This record establishes local runner/CLI/browser and syntax evidence only.
Hosted clean/regression job execution, actual artifact downloads/summaries, a
normal failing regression gate, independent review, merge and publication remain
separate parent-owned verification. Python 3.11 is configured in CI but was not
run locally. Prior browser/platform/accessibility/high-volume/audit limits remain.

The external caller example is pinned to feature implementation ancestor
`ce9b77c75887f12fa668db91eb7a8682a8303285` for both workflow and TraceBench
source. That commit contains every referenced runner/script and declares package
0.3.0; it does not point at the older 0.2.0 release. The documentation pin was
added afterward so its literal SHA identifies an actual existing commit.

## 0.3.0 review repair: generated JSON size bound

Independent review found that both CI runner stages applied `load_json`'s default
16 MiB input bound to generated reports, despite advertising a 64 MiB artifact
bound. Six valid 500,000-character recorded outputs can produce about 18 MB of
JSON after HTML-sensitive character escaping; each real CLI format succeeds,
but the runner previously returned 2 and removed staging, or rejected a correctly
hashed gate handoff.

Five installed-wheel regression/boundary tests now exercise the real CLI from
outside the checkout with no `PYTHONPATH`. Before the repair, the two independent
positive methods produced **six failing subtests**: evaluate/upload handoff and
independently generated gate reports, each with actual outcome **0, 1 and 3**.
Both generated `report.json` reads now explicitly pass `max_bytes=REPORT_LIMIT`.
The helper default, CLI baseline-input limit, schemas, renderer, 10 MiB workflow
input cap and 64 MiB generated-report cap are unchanged.

The new tests also generate a real valid JSON report above 64 MiB from separately
bounded case/output files and prove evaluation rejects it with exit 2, no upload
handoff and removed staging. A sparse 64 MiB + 1 byte report proves the gate
rejects the size before hashing. An installed CLI baseline test verifies that a
valid report over 16 MiB still cannot enter through the unchanged baseline-input
interface. The complete **77-test** suite passes on both **Python 3.13.7** and
**Python 3.15.0**. The large valid reports retain normal gate outcomes 0/1/3 and
are preserved in the upload handoff.

Fresh source, wheel and source-archive environments were rebuilt and installed
again with `pip install --no-cache-dir --no-index` after this repair. Each reports
metadata/runtime/CLI version **0.3.0** outside the checkout, preserves real normal
gates 0/1/3 and explicit expected-3 verification, and passes the original demo,
exact HTML sample and required real Chromium checks. `actionlint 1.7.7` and
`git diff --check` pass; Pages source and sample bytes remain unchanged. Hosted
PR execution and publication are separate parent-owned work.

After the size-bound repair, the external example's workflow and source pins both
point to fixed implementation ancestor `9cfe62a4afd613fc9a15e24018cdf77bc8f65977`.
That actual commit contains the repaired runner, workflow and all referenced
package/browser/fixture files at version 0.3.0. It supersedes the original
`ce9b77c…` example pin above; preserving this ancestor during merge retains the
reviewed source provenance.

## 0.4.0: exact recorded-observation budgets (local evidence)

On **2026-10-23**, the supplied clean base at
`60351fb1342d85a52b2e9ce2ceb6c84a503cfc7d` passed **77 tests** before work.
The complete policy implementation now passes **102 tests**, zero failures/errors,
on **Python 3.13.7** and **Python 3.15.0** on macOS. Runtime dependencies remain
empty; no provider was called or timed. The policy module and CLI use separate
schema 1 rules/verdicts and preserve the existing evaluation schema and gates.

```sh
python3.13 -m unittest discover -v
python3 -m unittest discover -v
reports/t8/tooling/actionlint -color
git diff --check
```

Tests were written before implementation. Ten initial policy methods failed for
the missing module. A further extreme-boundary test exposed that fixed decimal
normalization could produce a rule string beyond its own mantissa bound;
normalization now preserves bounded scientific notation when needed and is
reusable. Six initial installed-wheel CLI methods exposed the absent policy
subcommand while the original evaluate exit-code test already passed. Five
initial installed-runner methods exposed missing optional artifacts, gates and
invalid-rules handling; all were rerun green. Version tests failed against 0.3.0
before metadata/runtime advanced to 0.4.0. The tracked synthetic budget-fixture
check failed before its rule files were added, then passed.

Independent hand-derived numeric checks cover 1/3 passed against `0.3333331`
(pass) and `0.3333334` (fail), inclusive exact cost/latency boundaries including
very small/large values, nearest-rank p95, all selected rules together, complete
supplied zero observations versus absent/partial coverage, missing prices and
wrong currency. Caller Decimal precision, rounding, traps and flags remain
unchanged. Invalid versions, unknown/duplicate keys, numeric/Boolean thresholds,
nonfinite values, malformed/excessive decimal syntax and byte bounds reject.
Reports are revalidated using the unchanged schema 1 validator.

Installed policy CLI tests run outside the checkout without `PYTHONPATH`. They
prove accepted/rejected/unavailable/invalid outcomes 0/1/2, JSON/Markdown output,
64 KiB rules and 64 MiB evaluation limits, actual input aliases/hardlinks/symlinks,
failed atomic replacement cleanup and original evaluate 0/1/2/3. Budget acceptance
can retain visible failed cases. No evaluation report bytes are rewritten.

Real installed-wheel runner tests verify the exact default five-file versus
optional eight-file set, all artifact hashes, original evaluation and separate
policy status in provenance/summary, rules snapshots, copied upload handoffs,
0/1/unavailable/invalid policy, original evaluation 1/3 priority, deliberate
policy-failure assertions and recomputed-verdict tamper rejection. The existing
large-report tests still independently exercise both 64 MiB readers, valid
reports above 16 MiB on outcomes 0/1/3, generated reports above 64 MiB and the
unchanged 16 MiB baseline input bound. A preservation test compares all three
evaluation formats with and without policy and checks default handoff shape.

Author self-review found that inferring policy selection only from staged files
could silently accept a handoff after its entire optional set was removed. The
new regression first observed exit 0; after the fix it receives exit 2. The final
workflow gate independently carries the selected `TB_RULES` marker and requires
the exact corresponding artifact set, then recomputes policy from the snapshot.
It does not reopen the caller path. Copied artifacts remain usable after the
original rules file disappears. All 102 tests were rerun after this repair.
No author-review critical/important findings remain; independent review is
separate parent-owned work.

Fresh **0.4.0** environments under ignored
`reports/observation-budgets/fresh-installs/{source,wheel,sdist}` installed the
source checkout, built wheel and built source archive with
`pip install --no-cache-dir --no-index`. Metadata/runtime/console version all
agree. Each real console script ran outside the checkout and passed the original
demo, installed runner gates (default 0/3, policy 0/1, explicit policy-failure 0,
regression priority 3 and explicit expected-regression 0), and required real
Chromium verification. The source-archive route used its own extracted verifier,
runner and fixtures. The wheel includes `policy.py` and no runtime dependencies.

With **Node 24.18.0**, pinned development-only **Playwright 1.61.1**, and actual
**Chromium 149.0.7827.55**, all three installed environments retained the existing
desktop/mobile 1280/390/320 px layouts, full text, search, all filters, keyboard,
no-JavaScript expansion, print, hostile-markup checks and zero HTTP(S) requests.
The unchanged HTML sample retains SHA-256
`0f4bad9a7d8e4ae6bcc1a141f058f4562359a44c07527a05eef5643a4e757ddc`.
Git diff confirms Pages workflow, sample, existing evaluation/JSON/Markdown/HTML
renderers and input validators are unchanged from the supplied base.

**actionlint 1.7.7** and `git diff --check` pass. The actual workflow's pre-checkout
Python option block was executed: all three finite expectations were accepted,
and invalid/injection-like expectation strings were rejected with no handoff.
Own CI source calls the reusable workflow for real synthetic budget acceptance
and a separately named expected-budget-failure assertion. Local subprocess and
syntax checks do not establish hosted job behavior.

Limits: no local Python 3.11 run, new browser/platform/accessibility/load/security
audit, provider measurement or authenticated-observation claim. Actual hosted
own-CI calls, normal failing-budget probe, retained artifact inspection, Pages,
independent review, merge and release are separate parent-owned evidence. These
observations are caller-supplied data, not measured provider benchmarks, safety
verdicts or spending authorization.

The 0.4.0 consumer example now pins actual fixed implementation ancestor
`22187e91ada6bede9869e95b9314723c54687ba6` for both reusable workflow and source.
That commit was created only after the complete implementation, selection-guard
repair and verification above; it contains all referenced package/runner/workflow/
fixture files and declares 0.4.0. The literal pin is added in this later docs
commit so it names a real ancestor. Preserve it through merge-commit integration;
if independent review changes runtime or workflow code, commit the complete fix
first and update both pins to that newer actual implementation ancestor.
