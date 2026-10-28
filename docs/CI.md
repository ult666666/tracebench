# Recorded-output CI gate

TraceBench 0.4.0 supplies an actual reusable GitHub Actions workflow at
`.github/workflows/recorded-evaluation.yml`. The repository's `ci.yml` calls it
for both the clean synthetic fixture and a separate expected-regression
verification. The latter explicitly asserts exit **3**; an unexpected clean
result fails verification. A normal consumer gate fails on exits **1** or **3**.
Every input and example in this public repository is synthetic, checked in, and
provider-free. Supplied prices, token counts and latencies are invented.

## Call from another repository

The example pins the complete 0.4.0 implementation ancestor
`8c168e5c3b4f4ee68e298086291bdb7ac9b2992a`, which contains this workflow, its
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
    uses: ult666666/tracebench/.github/workflows/recorded-evaluation.yml@8c168e5c3b4f4ee68e298086291bdb7ac9b2992a
    with:
      tracebench-ref: 8c168e5c3b4f4ee68e298086291bdb7ac9b2992a
      cases: evaluation/cases.jsonl
      outputs: evaluation/candidate.jsonl
      baseline: evaluation/baseline-report.json
      pricing: evaluation/pricing.json
      rules: evaluation/budget.json
      artifact-name: recorded-evaluation
```

Omit `rules` to retain the original evaluation-only gate. Omit `pricing` if costs
are unavailable and `baseline` if only check failures should gate the evaluation.
A selected cost rule with unavailable pricing will reject the policy. The default `expectation: pass` applies the real gate.
`expectation: regression` is reserved for deliberate verification fixtures: it
succeeds only when evaluation exits 3, and must not replace a real release gate.
The supported expectation strings are `pass`, `regression`, and the optional
`policy-failure` fixture assertion described below. Use a unique
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

`cases` and `outputs` are required; `baseline`, `pricing`, and `rules` are optional
(the stricter rules cap is described below). Each
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
the caller checkout. Without rules it generates only `report.json`, `report.md`, `report.html`,
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
validated JSON outcome before returning the real evaluation exit, or the
combined evaluation/policy result when rules are selected. It also runs
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

This repository's own CI runs the clean, expected-regression and budget jobs on
every push and pull request (see [Verification](VERIFICATION.md)). Before you make
the gate a required check in your own repository, run it once with a deliberately
failing input and confirm that the job fails and the reports are uploaded. This is
a deterministic recorded-output check, not a statistical benchmark, security
audit, or guarantee about live model behavior.

## Optional recorded-observation budgets (0.4.0)

A reviewed 0.4.0 workflow/source revision accepts optional `rules`, a caller-relative
strict schema 1 policy JSON path. It uses the same path restrictions above and a
stricter **64 KiB** file cap. Thresholds are explicit decimal strings; at least
one is required. Use `fixtures/budget-pass.json` or `fixtures/budget-fail.json`
with the checked-in clean fixture and explicit pricing to reproduce policy 0/1.
The example above pins a commit that contains this workflow, the runner, the
policy module and the fixtures. Both SHAs in the example must match.

With rules, the exact artifact set is `report.json`, `report.md`, `report.html`,
`provenance.json`, `gate.json`, **`policy.json`, `policy.md`, `rules.json`**.
The additional files are capped at 64 KiB each. `rules.json` is a byte-for-byte
snapshot of the validated caller-selected thresholds; review it as public report
content when using public CI. No other caller files are copied. Without rules,
the exact original five-file set, evaluation report bytes, summary/handoff shape
and normal gate behavior remain unchanged (apart from the reported package version).

The runner invokes the installed policy CLI for JSON and Markdown, retaining
valid policy exits 0/1 for upload. Invalid rules/report or I/O remains exit 2,
removes staging and produces no successful handoff. `gate.json` adds `policy_exit`
and hashes all seven other artifacts. The final gate validates the exact optional
set, verifies hashes, validates the evaluation, and recomputes both verdict and
Markdown from the saved rules/report. The generated-report reader retains its
64 MiB repair; evaluate baseline inputs retain their separate narrower limit.
Copied artifacts can be verified after the caller's rules file is removed.
Hashes do not authenticate recorded observations or protect against trusted code
that deliberately rewrites the complete artifact set and metadata.

Provenance records original `evaluation_exit` and separate `policy_exit`, and
hashes the original rules input. The summary shows both statuses without embedding
caller text or paths. The workflow exposes `policy-exit` (0/1), empty without
rules, in addition to original `evaluation-exit`. Failed-job output/dependency
semantics still apply. Artifacts are uploaded before the combined gate:

| Evaluation | Policy | Normal combined gate |
| --- | --- | --- |
| 0 | 0 | 0 |
| 0 | 1 (failed or unavailable) | 1 |
| 1 | 0 or 1 | 1 |
| 3 | 0 or 1 | 3 |
| Invalid report or rules | No valid verdict | Stage fails 2; no upload handoff |

Missing/partial supplied latency or token/pricing coverage and mismatched currency
are `unavailable`, not zero or exclusions. Policy acceptance concerns only selected
rules; original failed cases and regressions stay visible and retain gate priority.
There are no provider calls, inferred observations, price feeds or conversions.

Own CI calls the reusable workflow for **Synthetic budget accepted by real combined
gate** and **Verify synthetic budget failure (evaluation 0, policy 1)**. The second
uses finite `expectation: policy-failure`, which succeeds only for evaluation 0
and policy 1; absent rules, policy acceptance or evaluation failure makes the
verification fail. `expectation: regression` still requires evaluation 3 and now
also requires any selected policy to pass. These are explicit fixture assertions;
normal consumers must use the default `expectation: pass`. A normal consumer's
failed budget remains a failing job and is not converted into an assertion.

For local runner reproduction add `TB_RULES` to both stages of the earlier
environment contract. The final stage uses its nonempty value only as the
independent selection marker and requires exactly the optional artifact set; it
does not reopen that caller path. Keep the marker when verifying copied artifacts,
even if the original rules input was removed. This prevents a missing policy set
from silently changing a selected-budget run into a no-policy gate. Computation
uses only the staged snapshot, not a caller-selected executable or output path. Installed-CLI tests cover 0/1/unavailable/invalid policy, exact artifact
sets/hashes and copied handoff, real failure priority, fixture assertions,
recomputed-verdict tamper rejection and no-policy behavior. A normal gate that
fails on a budget is not run in this repository's CI, because it would fail the
build; the policy-failure assertion job covers that path instead.
