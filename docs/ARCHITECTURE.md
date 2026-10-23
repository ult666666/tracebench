# Architecture

TraceBench is a local file-to-report pipeline. It never executes a prompt or
connects to a provider. The caller records outputs and observations elsewhere.

```text
cases.jsonl ── strict schema ─┐
                            ├─ exact ID join ─ literal checks ─ per-case results
outputs.jsonl ─ strict schema┘                                  │
pricing.json ── Decimal rates ─────────────── metrics and cost ──┤
prior report ── structural validation ─ suite fingerprint ──────┤
                                                               ▼
                                             JSON / escaped Markdown / HTML
                                                               │
                                                   stdout or atomic file
```

## Module boundaries

| Module | Responsibility |
| --- | --- |
| `io.py` | Bounded UTF-8 reads, duplicate keys/IDs, finite numbers, record validation |
| `checks.py` | Exact string, literal substring, recursive JSON subset checks |
| `evaluate.py` | ID joins, case/check results, cost/latency coverage, suite fingerprint, baseline compatibility |
| `report.py` | Exact-number JSON serialization and escaped Markdown previews |
| `html_report.py` | Validated standalone HTML, full inert JSON outputs/reasons, hashed CSP, optional search/filter and print CSS |
| `cli.py` | Argument parsing, exit-code precedence, protected atomic report replacement |
| `build_backend.py` | Dependency-free wheel, metadata, and source archive construction |

The library accepts ID-keyed dictionaries. Readers preserve case order, and
the evaluator emits results in that order. Output order never controls matching.
The evaluator revalidates API inputs, so calling it directly cannot bypass
finite-number or schema checks. It does not modify caller-owned input values.

## Ambiguity fails early

A duplicate object key is rejected before schema interpretation. Duplicate IDs
are errors, even when their contents are identical. Candidate IDs must equal
case IDs exactly: missing and extra IDs are reported together. There is no
partial scoring mode. Blank lines, unknown fields, invalid Unicode, and unknown
check types are rejected. Both token fields must be supplied together.

Numbers are parsed as `int` or `Decimal`; JSON `NaN` and infinities are errors.
The evaluator uses its own fixed decimal context with 512-digit precision and
round-half-even, independent of a library caller's current decimal context.
Cost remains decimal through multiplication, division, summation, and rendering.

## Baseline compatibility

A baseline is a prior JSON report with schema version 1. Its IDs, booleans,
check results, metric types, costs, summary counts, and optional comparison
must be internally consistent. Duplicate report IDs and inconsistent summary
totals are rejected. Comparison also validates the current report.

The suite fingerprint is SHA-256 over a typed canonical representation of all
case records sorted by ID. Object keys are sorted; numeric representation is
canonicalized without rounding. Type tags distinguish numbers from strings and
booleans. Case-file ordering is irrelevant, while prompt, check, description,
ID, and expected-value changes invalidate the baseline. Equivalent JSON numbers
such as `2` and `2.0` share a representation.

Comparison checks exact ID sets before fingerprints, then detects pass-to-fail
regressions and fail-to-pass improvements. Regression and improvement ID arrays
are sorted. A failure that already existed in the baseline is still a failure,
but is not a new regression. A net-neutral pass count can contain both a
regression and an improvement; regressions still return exit 3.

Baseline validation establishes structure and consistency, not authenticity.
A caller can fabricate observations or alter a report and recompute its summary.
The hash identifies the case suite; it is not a signed provenance mechanism.
Baseline prices and observations may differ from the candidate's. The gate
compares pass/fail only, not latency or budget thresholds.

## Output safety and writes

JSON strings escape `<`, `>`, `&`, and Unicode line/paragraph separators, while
preserving exact decimal numeric values. Markdown converts untrusted punctuation,
symbols, control/format characters, and non-space separators to numeric entities.
Raw HTML, inline links, code spans, and table separators from inputs therefore
remain content. Markdown output previews are limited to 300 characters; complete
recorded outputs remain in JSON and HTML. Reports are not a redaction mechanism.

HTML validates report consistency, renders dynamic data only as escaped text,
and uses only fixed status values in attributes. Outputs and reasons are full
JSON text so HTML parsing cannot drop leading newlines or normalize control
characters. The fixed inline script and stylesheet are allowed by exact SHA-256
CSP hashes, with all network sources, frames, forms and base URLs blocked.
Search operates on existing DOM text and safely decoded JSON; it never parses
recorded content as HTML. Native details expose content without JavaScript, while
print CSS reveals filtered cases and closed blocks. See [HTML reporting](HTML.md).

`--report` checks resolved paths and existing file identities to protect inputs,
writes a temporary file in the destination directory, flushes it, and replaces
the destination with `os.replace`. Parents must already exist. Input validation
finishes before any report write. The CLI does not protect against a malicious
process racing filesystem paths, and does not guarantee directory-entry
durability after power loss. Stdout can be partial if its consumer fails.

## Packaging and tradeoffs

The package has no runtime or build dependencies. The project-specific PEP 517
backend writes a pure-Python wheel, its entry point and RECORD hashes, and a
source archive. Standard pip installation works with `--no-index`. Tests run a
built wheel outside the source checkout; installation is verified separately in
an isolated environment. The backend deliberately omits editable installs,
extension compilation, and general-purpose packaging configuration.

All cases and outputs are held in memory, and percentiles sort observed latency.
This favors a short, reviewable implementation over streaming or distributed
execution. Per-file row limits are safety rails, not a practical capacity claim.
See [methodology](METHODOLOGY.md) and [schemas](SCHEMAS.md) for numeric and size
limits. The code has local test evidence, not a formal security audit.
