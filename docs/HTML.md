# Standalone HTML reports

The `html` format presents the existing evaluation report as one offline file.
It needs Python 3.11+ to generate and a modern browser to view. No provider,
JavaScript package, font service, external stylesheet, or network connection is
needed by TraceBench. The [committed sample](sample-report.html) contains only
synthetic recorded outputs, observations and prices; its title and visible banner
make that provenance explicit. Arbitrary reports are not assumed to be synthetic.

```sh
python3 -m tracebench evaluate --cases fixtures/cases.jsonl --outputs fixtures/baseline.jsonl --pricing fixtures/pricing.json --report reports/baseline.json
python3 -m tracebench evaluate --cases fixtures/cases.jsonl --outputs fixtures/regression.jsonl --pricing fixtures/pricing.json --baseline reports/baseline.json --format html --report reports/regression.html
```

Create `reports/` first. These commands exit 0 and 3 respectively. An HTML report
cannot serve as a baseline: baselines remain validated JSON reports. HTML stdout,
atomic `--report` replacement, input overwrite protection, and exits 0/1/2/3 have
the same semantics as JSON and Markdown.

The summary shows the suite fingerprint, pass/fail counts, known token cost and
currency, priced/missing-token coverage, and observed/missing latency coverage.
Latency includes supplied mean, minimum, maximum and nearest-rank p50/p95. Baseline
comparisons show regressions, improvements and unchanged counts. No baseline means
comparison is unavailable; missing measurements are labelled unavailable, never
replaced by zero. Partial known cost is not a total bill, and recorded observations
have no independently verified provider provenance.

Each case has a precise PASS/FAIL label, a regression/improvement badge when
applicable, supplied metrics, expandable output, and individual check results and
reasons. Report schema v1 does not retain case inputs or expected values; these are
not invented. Outputs are full JSON values and reasons are JSON strings, preserving
exact decimals, Unicode, leading newlines and control characters. Nothing is
truncated. Quotes and JSON escapes are part of that representation.

Search matches case IDs, full JSON output and decoded recorded string content;
filters include all, passed, failed, regressions and improvements. The labelled
native input/select controls support the keyboard, and a live count announces
visible cases. Without JavaScript, controls stay hidden and every case is available
through native expandable blocks. Print CSS hides controls, reveals filtered cases,
and shows full output and reasons even when blocks are closed. This was exercised
in Chromium; older browser print engines may require manually opening blocks.

## Untrusted-content boundary

`render_html` validates the existing report and HTML-escapes every dynamic text
value. Dynamic data never enters script, CSS, element IDs or other attributes.
Status attributes come only from fixed internal values. Recorded text cannot create
links, forms, images, scripts or other elements. The optional vanilla script reads
text from the DOM, safely parses JSON for searching, and updates visibility and a
text-only count. It uses no `innerHTML`, inline event handlers or `eval`.

A meta Content Security Policy appears before styles/content. It permits exactly
the SHA-256 hashes of the fixed embedded script and stylesheet; all network sources,
connections, images, fonts, objects, frames, base URLs and form submissions are
blocked. The hashes are recomputed deterministically from those constants when
rendering. This is defense in depth alongside escaping, not a substitute for it.
The existing loader limits apply (1 MiB per JSONL row, 100,000 rows, bounded nesting,
200-character IDs, at most 100 checks per case); the renderer does not fetch assets
or introduce unbounded additional input channels. Large valid suites still produce
large HTML files because all records are included. No high-volume browser benchmark
or independent security audit is claimed.

## Reproduce and verify

From the checkout, regenerate the exact committed synthetic sample:

```sh
python3 scripts/verify_html.py --write-sample
```

The script rebuilds the report from `fixtures/cases.jsonl`, `baseline.jsonl`,
`regression.jsonl` and `pricing.json`, adds a fixed synthetic-demo banner/title,
and asserts exact sample bytes. Every run without `--write-sample` verifies those
same committed bytes, so it is suitable for a prepublication CI check. The script
reads and writes explicit UTF-8 bytes; changing LF line endings to CRLF is a
verification failure even if the text appears identical. The script
also compares renderer output to real CLI stdout and atomic files, checks all exit
codes, and checks input protection. It bounds every subprocess with a timeout.

If Node and an existing Playwright installation are available, it also launches
real Chromium. It first looks for `../impact-ledger/node_modules/playwright` and
otherwise prints a clear browser-check skip. It never installs Node dependencies.
Require explicit browser evidence and retain screenshots/print output with:

```sh
python3 scripts/verify_html.py --require-browser --browser-module /absolute/path/to/node_modules/playwright --artifacts reports/html-verification
```

The browser verifier checks desktop 1280 px and mobile 390/320 px overflow, search,
every status filter, live counts, keyboard controls, no-JavaScript expansion, print
visibility, exact hostile text round-trip, no executable injected elements, and no
HTTP(S) requests. It saves desktop/mobile screenshots and an A4 print PDF. Browser
checks are optional local tooling; the installed Python package has no Node runtime
dependency. To verify a freshly installed CLI from a temporary directory outside
the checkout:

```sh
python3 scripts/verify_html.py --cli /absolute/path/to/venv/bin/tracebench --require-browser --browser-module /absolute/path/to/node_modules/playwright
```

## Hosted synthetic example

The [GitHub Pages preview](https://ult666666.github.io/tracebench/) contains only the
committed synthetic example, copied to `index.html` after the full test suite,
no-index package installation, installed CLI verification and exact sample-byte
check. The workflow deploys only that staging directory. It does not accept files,
call providers, store user records or publish arbitrary local reports. Repository
Pages must use GitHub Actions. The hosted bytes are checked separately after
deployment; a configured workflow alone is not evidence that publication passed.

Both the Pages build and deploy jobs require `github.ref == 'refs/heads/main'`,
including manual workflow dispatches. A manual run selected from another branch
or tag skips the publish path. Deployment still consumes the same staged artifact
that passed the main build's tests, installation checks and exact sample-byte check.
