# Recorded-output CI gate

TraceBench 0.3.0 supplies an actual reusable GitHub Actions workflow at
`.github/workflows/recorded-evaluation.yml`. The repository's `ci.yml` calls it
for both the clean synthetic fixture and a separate expected-regression
verification. The latter explicitly asserts exit **3**; an unexpected clean
result fails verification. A normal consumer gate fails on exits **1** or **3**.
Every input and example in this public repository is synthetic, checked in, and
provider-free. Supplied prices, token counts and latencies are invented.

## Call from another repository

The example pins the 0.3.0 implementation commit
`ce9b77c75887f12fa668db91eb7a8682a8303285`, which contains this workflow, its
`scripts/ci_evaluate.py` runner, and the installed package sources. Review and
trust that code before adopting it. To upgrade, replace **both** occurrences of
the SHA with the same reviewed immutable commit that contains all these files.
Branch names and release tags are rejected by the source-revision input. GitHub
requires a literal reusable-workflow reference, so expressions cannot replace its
`@SHA`. The commit must be available in the upstream repository when the job runs.

```yaml
name: Recorded evaluation
on:
  push:
  pull_request:
permissions:
  contents: read
jobs:
  evaluate:
    uses: ult666666/tracebench/.github/workflows/recorded-evaluation.yml@ce9b77c75887f12fa668db91eb7a8682a8303285
    with:
      tracebench-ref: ce9b77c75887f12fa668db91eb7a8682a8303285
      cases: evaluation/cases.jsonl
      outputs: evaluation/candidate.jsonl
      baseline: evaluation/baseline-report.json
      pricing: evaluation/pricing.json
      artifact-name: recorded-evaluation
```

Omit `pricing` if costs are unavailable and `baseline` if only check failures
should gate the run. The default `expectation: pass` applies the real gate.
`expectation: regression` is reserved for deliberate verification fixtures: it
succeeds only when evaluation exits 3, and must not replace a real release gate.
The only supported expectation strings are `pass` and `regression`. Use a unique
`artifact-name` for each call in a run: `[a-z][a-z0-9-]{0,62}`. There are no
user-selectable commands, output paths, runtime versions, or report formats.

The caller repository is checked out at the event's normal ref; on
`pull_request`, GitHub's default is the pull request merge ref. TraceBench source
is checked out separately from `ult666666/tracebench` at the validated immutable
SHA, then installed with `pip install --no-index` into an isolated environment.
The repository's own calls pass their tested `github.sha`, so upstream PR/push CI
exercises the implementation being reviewed. A standalone fork must point
`tracebench-ref` at a reviewed commit available from the upstream repository,
or adapt the hard-coded source repository when maintaining its own distribution.

The workflow checks out code and installs TraceBench's build backend, which is
executable code. Review and trust the pinned TraceBench revision and your caller
workflow/code. Path checks and read-only tokens do **not** sandbox an untrusted
checkout, workflow modification, dependency, or build backend. The reusable job
requests only `contents: read`, persists no checkout credentials, declares no
secrets, and uses no `pull_request_target`. Do not pass inherited secrets or add
write permissions to this job. Ordinary GitHub fork-PR approval rules still apply.

## Input paths and baseline provenance

`cases` and `outputs` are required; `baseline` and `pricing` are optional. Each
nonempty path must identify a regular file inside the caller checkout:

- At most 1,024 characters and 20 slash-separated components; at most **10 MiB**
  per file, in addition to the evaluator's existing schema/row/depth limits.
- Relative paths only; no empty, `.` or `..` components, backslashes, control
  characters, or symlink components. Hidden paths and components named `venv`,
  `node_modules`, or `__pycache__` are rejected.
- Spaces, leading hyphens, Unicode, and literal shell metacharacters are allowed.
  Inputs enter environment variables and then an argv list; no input becomes
  shell source. Files are read, never used as scripts.

Keep evaluation inputs in a dedicated tracked directory. The runner validates
files and bounds access; it does not prove that arbitrary consumer files were
committed or that their recorded content is true. Do not include secrets or
private outputs in a public report. HTML and JSON retain the full output text.

A baseline is a prior JSON report for exactly the same suite, including prompts,
descriptions and checks. To reproduce this repository's checked-in baseline:

```sh
tracebench evaluate --cases fixtures/cases.jsonl --outputs fixtures/baseline.jsonl --pricing fixtures/pricing.json --report fixtures/baseline-report.json
```

This exits 0. Review and intentionally update baseline reports when adopting
accepted behavior. Updating a baseline to match a regressed candidate defeats
comparison. The suite fingerprint detects incompatible suites; it does not decide
whether a baseline is appropriate.

## Reports, summary, and gate ordering

| Evaluation | Evaluation stage | Artifact upload | Final normal gate |
| --- | --- | --- | --- |
| 0: checks pass | Success with reports | Runs | Passes |
| 1: checks fail without regression | Success with reports | Runs | Fails with 1 |
| 2: invalid input / usage / I/O | Fails with 2, no successful handoff | Skipped | Job remains failed |
| 3: pass-to-fail baseline regression | Success with reports | Runs | Fails with 3 |

The runner creates an exclusive `tracebench-*` directory in `RUNNER_TEMP`, outside
the caller checkout. It generates only `report.json`, `report.md`, `report.html`,
`provenance.json`, and `gate.json`. Reports are limited to **64 MiB each**; every
CLI subprocess has a 60-second timeout and the reusable job a 10-minute timeout.
The 64 MiB allowance applies only to generated report reads. Workflow input files
remain capped at 10 MiB; the direct CLI retains its 16 MiB baseline-JSON input
limit. A larger generated report cannot be reused through those narrower baseline
input interfaces.
Invalid/oversize/unstable evaluation removes the staging directory and emits no
successful upload handoff. Input files are never report destinations.

Download the named artifact from the Actions run. It contains all three report
formats, SHA-256 hashes of the consumed input bytes, suite SHA-256, TraceBench
version/source SHA, original exit code and expectation. `gate.json` binds the
report files to that outcome. Provenance hashes identify bytes and code; they do
not authenticate who generated an output, verify prices/latencies, or establish
model quality. The runner detects inputs changed across its three format runs;
trusted code can still alter files, so this is not a hostile-concurrency sandbox.

The job summary reports the original exit, pass/fail/regression counts, suite hash
and source revision. It embeds no recorded text or caller-provided path. The
artifact is retained for **7 days**. The upload path is only this generated
directory, never the checkout, `.git`, environment files, credentials, virtual
environment, or Node dependencies. The final stage verifies report hashes and
validated JSON outcome before returning the real evaluation exit. It also runs
if upload fails; an upload failure already keeps the job failed. Cancellation
may interrupt reporting. There is no `continue-on-error` to hide regressions.
The reusable workflow exposes `evaluation-exit` when reports were produced;
GitHub's failed-job dependency/output behavior still applies to downstream jobs.

## Reproduce local verification

The runner uses the installed interpreter's `python -m tracebench`. Run it from a
directory outside the source checkout with the following environment values:
`TB_WORKSPACE` (absolute caller checkout), `RUNNER_TEMP` (separate existing absolute
directory), `TB_CASES`, `TB_OUTPUTS`, optional `TB_BASELINE`/`TB_PRICING`,
`TB_EXPECTATION` (`pass` by default), `TB_SOURCE_SHA`, `GITHUB_OUTPUT`, and
`GITHUB_STEP_SUMMARY`. Invoke the pinned `scripts/ci_evaluate.py evaluate`, upload
only the emitted `report_dir`, then invoke `scripts/ci_evaluate.py gate` with
`TB_REPORT_DIR` set to that directory. Do not treat the evaluation stage's success
as the gate result; it intentionally defers valid check failure until reporting.

`python3 -m unittest discover -v` exercises the runner through actual subprocesses:
all valid outcomes, invalid records, missing/nonregular/oversize files, symlinks,
traversal/private/runtime paths, spaces/leading hyphens/metacharacters, unchanged
input bytes, upload handoff, and changed/invalid gate records.

The separate browser job locks development-only Playwright **1.61.1**, runs
**Node 24**, installs Chromium, and invokes `verify_html.py --require-browser`
against the installed CLI. It exercises the existing real browser interactions
and uploads only two explicitly named HTML reports, desktop/mobile screenshots,
and print PDF. It cannot silently pass with skipped browser checks. Python wheels
contain no Node/browser dependency. Pages remains a separate main-only synthetic
sample deployment with per-ref concurrency and exact sample-byte checks.

## Official workflow references and limits

Implementation was cross-checked against GitHub's
[reusable-workflow inputs, calling and SHA pinning](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows),
[step conditions and failure semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax),
[script-injection guidance](https://docs.github.com/en/actions/concepts/security/script-injections),
[output and summary environment files](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands),
[artifact upload action](https://github.com/actions/upload-artifact), and
[Playwright CI setup](https://playwright.dev/docs/ci-intro).

Local runner/browser execution and actionlint do not establish hosted workflow
behavior or release protection. Inspect the actual hosted clean and expected-3
jobs, their artifacts and summaries, and a deliberately failing normal gate before
relying on a required check. Hosted verification and publication are recorded
separately after integration. This is a deterministic recorded-output check, not
a statistical benchmark, security audit, or guarantee about live model behavior.
