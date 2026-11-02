"""Self-contained, inert HTML reports; no assets, providers, or dependencies."""

import base64
import hashlib
from html import escape

from .evaluate import validate_report
from .report import describe_statistics, render_json


# These constants never include report data. CSP permits exactly their bytes.
_STYLE = """
:root { color-scheme: light; --bg:#fbfbfa; --ink:#1f1f1d; --muted:#5b5a55; --line:#e2e0da;
  --field:#87857e; --code:#f2f1ec; --green:#1d6a43; --red:#b0312b; --accent:#1f4fa3; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
  font:16px/1.55 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
main { max-width:1040px; margin:0 auto; padding:40px 32px 32px; }
h1,h2,h3,p,dl,dd { margin:0; }
h1 { font-size:1.75rem; line-height:1.25; font-weight:650; }
h2 { font-size:1.2rem; line-height:1.3; font-weight:650; }
h3 { font-size:1rem; font-weight:600; overflow-wrap:anywhere; white-space:pre-wrap; }
code,pre { font-family:ui-monospace,SFMono-Regular,Consolas,monospace; }
code { font-size:.85rem; overflow-wrap:anywhere; }
.title-row { display:flex; justify-content:space-between; align-items:baseline; flex-wrap:wrap; gap:8px 24px; }
.verdict { font-weight:650; font-variant-numeric:tabular-nums; }
.passed { color:var(--green); }
.failed { color:var(--red); }
.muted { color:var(--muted); }
.small { font-size:.875rem; }
.fingerprint { margin-top:6px; overflow-wrap:anywhere; }
.summary { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:24px; margin-top:28px;
  padding:20px 0; border-top:1px solid var(--line); border-bottom:1px solid var(--line); }
.summary div { min-width:0; }
.summary dt { color:var(--muted); font-size:.875rem; }
.summary .value { margin:2px 0 4px; font-size:1.5rem; font-weight:600; line-height:1.3;
  font-variant-numeric:tabular-nums; overflow-wrap:anywhere; }
.summary .detail { color:var(--muted); font-size:.875rem; font-variant-numeric:tabular-nums; overflow-wrap:anywhere; }
.note { margin-top:12px; max-width:780px; }
section { margin-top:40px; }
.counts { display:flex; flex-wrap:wrap; gap:6px 28px; margin:10px 0 4px; font-variant-numeric:tabular-nums; }
.counts strong { font-weight:650; }
.gate { margin-top:16px; }
.table-wrap { overflow-x:auto; margin:12px 0 10px; }
table { border-collapse:collapse; width:100%; font-size:.875rem; font-variant-numeric:tabular-nums; }
th,td { padding:7px 10px; border-bottom:1px solid var(--line); text-align:right; white-space:nowrap; }
th:first-child,td:first-child { padding-left:0; text-align:left; }
thead th { color:var(--muted); font-weight:600; }
tbody th { font-weight:500; }
.stats-notes p + p { margin-top:2px; }
.section-head { display:flex; justify-content:space-between; align-items:baseline; flex-wrap:wrap; gap:8px; }
.controls { display:flex; flex-wrap:wrap; gap:12px 16px; align-items:end; margin:16px 0 4px; }
.controls[hidden],article[hidden] { display:none; }
.control { display:flex; flex-direction:column; gap:4px; flex:1 1 260px; }
.control.filter { flex:0 1 220px; }
label { font-size:.875rem; font-weight:600; }
input,select { width:100%; min-height:42px; padding:8px 10px; border:1px solid var(--field); border-radius:6px;
  background:#fff; color:var(--ink); font:inherit; }
:focus-visible { outline:3px solid var(--accent); outline-offset:2px; }
article { min-width:0; padding:16px 0; border-top:1px solid var(--line); }
.case-head { display:flex; justify-content:space-between; align-items:baseline; gap:16px; }
.status { flex-shrink:0; font-size:.875rem; font-weight:600; }
.case-metrics { margin:2px 0 6px; color:var(--muted); font-size:.875rem; font-variant-numeric:tabular-nums; overflow-wrap:anywhere; }
details { margin-top:4px; }
summary { cursor:pointer; font-size:.875rem; font-weight:600; }
pre { margin:8px 0 4px; padding:10px 12px; background:var(--code); border-radius:6px; white-space:pre-wrap;
  overflow-wrap:anywhere; word-break:break-word; font-size:.84rem; line-height:1.6; tab-size:4; }
.checks { margin:8px 0 0; padding-left:20px; }
.checks li + li { margin-top:10px; }
.checks strong { font-size:.875rem; font-weight:600; }
footer { margin-top:40px; padding-top:14px; border-top:1px solid var(--line); color:var(--muted); font-size:.8rem; }
.demo-label { padding:10px 24px; background:#efe9da; color:#463a1f; text-align:center; font-size:.875rem; }
@media(max-width:700px) {
  main { padding:24px 16px; } .summary { grid-template-columns:1fr; gap:14px; }
  .case-head { flex-direction:column; gap:2px; } .control.filter { flex:1 1 220px; }
}
@media print {
  body { background:white; color:#111; font-size:10pt; } main { max-width:none; padding:0; }
  .controls,#visible-count { display:none !important; } article[hidden] { display:block !important; }
  pre { padding:0; background:none; } section { margin-top:20px; }
  details::details-content { display:block; content-visibility:visible; }
  details > :not(summary) { display:block !important; } pre { white-space:pre-wrap; overflow:visible; }
  .case-head,summary { break-after:avoid; } .summary,table { break-inside:avoid; }
}
"""

_SCRIPT = """
(() => {
  'use strict';
  const controls = document.getElementById('controls');
  const search = document.getElementById('case-search');
  const filter = document.getElementById('case-filter');
  const count = document.getElementById('visible-count');
  const cases = Array.from(document.querySelectorAll('article'));
  // Cache only text already in the DOM; recorded content is never parsed as HTML.
  const searchable = cases.map(card => {
    const serialized = card.querySelector('.output').textContent;
    // Decode JSON string tokens only. Parsing numbers through JavaScript would
    // round exact decimals and could create matches absent from recorded data.
    const readable = (serialized.match(/"(?:\\\\.|[^"\\\\])*"/g) || [])
      .map(value => JSON.parse(value)).join('\\n');
    return (card.querySelector('.case-id').textContent + '\\n' + serialized + '\\n' + readable).toLocaleLowerCase();
  });
  function update() {
    const query = search.value.toLocaleLowerCase();
    let visible = 0;
    cases.forEach((card, index) => {
      const match = filter.value === 'all' || card.dataset.status === filter.value || card.dataset.change === filter.value;
      card.hidden = !(match && searchable[index].includes(query));
      if (!card.hidden) visible += 1;
    });
    count.textContent = visible + ' / ' + cases.length + ' cases visible';
  }
  search.addEventListener('input', update);
  filter.addEventListener('change', update);
  controls.hidden = false;
  update();
})();
"""


def _hash(text):
    return base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode("ascii")


def _text(value):
    return escape(str(value), quote=True)


def _cases(count):
    return f"{count} case" if count == 1 else f"{count} cases"


def _case(result, regressions, improvements, currency):
    status = "passed" if result["passed"] else "failed"
    change = "regressions" if result["id"] in regressions else "improvements" if result["id"] in improvements else "unchanged"
    label = ("Passed" if result["passed"] else "Failed") + {"regressions": " · regression", "improvements": " · improvement"}.get(change, "")
    metrics = result["metrics"]
    latency = _text(metrics["latency_ms"]) + " ms" if metrics["latency_ms"] is not None else "unavailable"
    tokens = f'{metrics["input_tokens"]} in, {metrics["output_tokens"]} out' if metrics["input_tokens"] is not None else "unavailable"
    cost = _text(result["cost"]) + " " + _text(currency) if result["cost"] is not None else "unavailable"
    # JSON text also preserves leading newlines, CR and NUL which HTML parsers
    # would otherwise normalize or discard even after ordinary HTML escaping.
    output = render_json(result["output"]).rstrip("\n")
    checks = []
    for check in result["checks"]:
        outcome = "passed" if check["passed"] else "failed"
        reason = render_json(check["reason"]).rstrip("\n")
        checks.append(f'<li><strong>{_text(check["type"])}: {outcome}</strong><pre class="reason">{_text(reason)}</pre></li>')
    return (f'<article data-status="{status}" data-change="{change}">'
            '<div class="case-head"><h3 class="case-id">' + _text(result["id"]) + '</h3>'
            f'<p class="status {status}">{label}</p></div>'
            f'<p class="case-metrics">Latency {latency} · tokens {tokens} · cost {cost}</p>'
            '<details><summary>Output (JSON)</summary><pre class="output">' + _text(output) + '</pre></details>'
            '<details><summary>Checks: ' + str(sum(check["passed"] for check in result["checks"])) + ' of ' + str(len(checks)) + ' passed</summary><ol class="checks">'
            + "".join(checks) + '</ol></details></article>')


def _comparison(comparison, cases, regressions, improvements):
    if not comparison:
        return '<p class="note">No baseline supplied. Regression and improvement status is unavailable.</p>'
    html = ('<div class="counts"><span>Regressions <strong>' + str(len(regressions)) + '</strong></span><span>Improvements <strong>'
            + str(len(improvements)) + '</strong></span><span>Unchanged <strong>' + str(comparison["unchanged"]) + '</strong></span></div>'
            f'<p class="muted small">Baseline passed {comparison["baseline_passed"]} / {cases} · Current passed {comparison["current_passed"]} / {cases}. '
            'Cases are matched by ID.</p>')
    described = describe_statistics(comparison)
    if described is None:
        return html
    outcome = "failed" if comparison["gate"]["failed"] else "passed"
    rows = []
    for label, row in described["rows"]:
        if row is None:
            rows.append(f'<tr><th scope="row">{_text(label)}</th><td colspan="6">unavailable</td></tr>')
        else:
            rows.append(f'<tr><th scope="row">{_text(label)}</th>' + "".join(f"<td>{_text(value)}</td>" for value in (*row[1:], row[0])) + "</tr>")
    notes = "".join(f'<p>{_text(line)}</p>' for line in [described["method"], *described["tests"]])
    return (html + f'<p class="gate"><strong class="{outcome}">{_text(described["gate"])}</strong> {_text(described["reason"])}</p>'
            '<div class="table-wrap"><table><thead><tr><th scope="col">Metric</th><th scope="col">Baseline</th><th scope="col">Current</th>'
            f'<th scope="col">Change</th><th scope="col">{_text(described["level"])}% interval</th><th scope="col">Detectable change</th>'
            '<th scope="col">Pairs</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>'
            f'<div class="stats-notes muted small">{notes}</div>')


def render_html(report: dict) -> str:
    """Validate and render a deterministic standalone report with full inert text.

    Input/expected values are not retained in report schemas 1 or 2 and are not reconstructed.
    Existing input bounds and report validation apply; outputs are never truncated.
    All dynamic values occupy escaped text nodes, never attributes, CSS or script.
    """
    validate_report(report)
    summary = report["summary"]
    latency, cost = summary["latency_ms"], summary["cost"]
    cases = summary["cases"]
    comparison = report["comparison"]
    regressions = set(comparison["regressions"]) if comparison else set()
    improvements = set(comparison["improvements"]) if comparison else set()
    status = "failed" if summary["failed"] else "passed"
    verdict = f'Failed: {summary["failed"]} of {_cases(cases)}' if summary["failed"] else f'Passed: {summary["passed"]} of {_cases(cases)}'
    if latency["observed"]:
        latency_value = _text(latency["mean"]) + " ms"
        latency_detail = (f'p50 {_text(latency["p50"])} ms · p95 {_text(latency["p95"])} ms<br>'
                          f'min {_text(latency["min"])} ms · max {_text(latency["max"])} ms<br>')
    else:
        latency_value, latency_detail = "Latency unavailable", "No measurements supplied.<br>"
    cost_value = _text(cost["total"]) + " " + _text(cost["currency"]) if cost["total"] is not None else "Cost unavailable"
    csp = ("default-src 'none'; script-src 'sha256-" + _hash(_SCRIPT) + "'; style-src 'sha256-" + _hash(_STYLE)
           + "'; script-src-attr 'none'; style-src-attr 'none'; connect-src 'none'; img-src 'none'; font-src 'none'; "
           "object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'")
    return ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="' + escape(csp, quote=True) + '">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>TraceBench evaluation report</title><style>' + _STYLE + '</style></head><body><main>'
            f'<header><div class="title-row"><h1>TraceBench evaluation report</h1><p class="verdict {status}">{verdict}</p></div>'
            '<p class="fingerprint muted small">Suite fingerprint (SHA-256) <code>' + _text(report["suite_sha256"]) + '</code></p></header>'
            '<dl class="summary" aria-label="Evaluation summary">'
            f'<div><dt>Cases passed</dt><dd class="value {status}">{summary["passed"]} / {cases}</dd><dd class="detail">{summary["failed"]} failed</dd></div>'
            '<div><dt>Mean latency</dt><dd class="value">' + latency_value + '</dd><dd class="detail">' + latency_detail
            + f'Measured in {latency["observed"]} / {cases} cases</dd></div>'
            '<div><dt>Token cost</dt><dd class="value">' + cost_value + '</dd>'
            f'<dd class="detail">Priced cases {cost["priced_cases"]} / {cases}<br>Missing token counts {cost["missing_token_cases"]} / {cases}</dd></div></dl>'
            '<p class="note muted small">Latency and token counts are supplied by the caller, and percentiles use the nearest-rank method. '
            'Cost covers priced cases only, so partial coverage is not a total bill. A case passes only when every check passes, '
            'and checks compare text literally, not meaning.</p>'
            '<section aria-labelledby="comparison-heading"><h2 id="comparison-heading">Compared with the baseline</h2>'
            + _comparison(comparison, cases, regressions, improvements) + '</section>'
            '<section class="case-section" aria-labelledby="case-heading"><div class="section-head"><h2 id="case-heading">Cases</h2>'
            f'<p id="visible-count" class="muted small" role="status" aria-live="polite" aria-atomic="true">{cases} / {cases} cases visible</p></div>'
            '<p class="muted small">Case inputs and expected values are not retained in the report. Outputs and check reasons are shown as JSON, '
            'so every character is preserved.</p>'
            '<div class="controls" id="controls" hidden><div class="control"><label for="case-search">Search case ID or recorded output</label>'
            '<input id="case-search" type="search" autocomplete="off" placeholder="Type to narrow the cases"></div>'
            '<div class="control filter"><label for="case-filter">Case status</label><select id="case-filter">'
            '<option value="all">All cases</option><option value="passed">Passed</option><option value="failed">Failed</option>'
            '<option value="regressions">Regressions</option><option value="improvements">Improvements</option></select></div></div>'
            '<noscript><p class="muted small">JavaScript is off, so search and filters are hidden. Every case is listed below.</p></noscript>'
            + "".join(_case(result, regressions, improvements, cost["currency"]) for result in report["results"])
            + f'</section><footer>TraceBench · report schema {report["schema_version"]}</footer></main><script>'
            + _SCRIPT + '</script></body></html>\n')
