"""Self-contained, inert HTML reports; no assets, providers, or dependencies."""

import base64
import hashlib
from html import escape

from .evaluate import validate_report
from .report import render_json


# These constants never include report data. CSP permits exactly their bytes.
_STYLE = """
:root { color-scheme: light; --paper:#f7f4ed; --ink:#292820; --muted:#656157;
  --line:#d8d1c4; --green:#226049; --red:#a23d2e; --accent:#9b582c; }
* { box-sizing:border-box; }
body { margin:0; background:var(--paper); color:var(--ink);
  font:16px/1.6 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
main { max-width:1160px; margin:0 auto; padding:52px 32px 36px; }
h1,h2,h3,p { margin:0; }
h1 { font-size:clamp(2.2rem,6vw,3.8rem); line-height:1.1; letter-spacing:-.055em; font-weight:650; }
h2 { font-size:1.45rem; letter-spacing:-.025em; }
h3 { font-size:1.05rem; overflow-wrap:anywhere; white-space:pre-wrap; }
.eyebrow { color:var(--accent); font-size:.75rem; letter-spacing:.15em; text-transform:uppercase; font-weight:750; }
.intro { max-width:680px; margin:18px 0 26px; color:var(--muted); }
.masthead { display:flex; justify-content:space-between; align-items:flex-start; gap:24px; }
.verdict { border:1px solid currentColor; border-radius:99px; padding:8px 18px; font-weight:750; letter-spacing:.06em; white-space:nowrap; }
.passed { color:var(--green); }
.failed { color:var(--red); }
.fingerprint { padding:16px 0 24px; border-top:1px solid var(--line); color:var(--muted); font-size:.8rem; }
code { font-family:ui-monospace,SFMono-Regular,Consolas,monospace; overflow-wrap:anywhere; }
.fingerprint code { display:block; margin-top:4px; color:var(--ink); }
.metrics { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; }
.metric { min-width:0; border:1px solid var(--line); border-radius:14px; background:#fffdf8; padding:24px; }
.metric .value { font-size:clamp(1.6rem,3vw,2.2rem); font-weight:650; line-height:1.3; margin:9px 0; overflow-wrap:anywhere; }
.metric .value.cost { font-size:1.5rem; }
.metric p,.fine { font-size:.86rem; color:var(--muted); overflow-wrap:anywhere; }
.baseline { margin:20px 0; padding:19px 22px; background:#eee8dd; border-radius:12px; }
.baseline .counts { display:flex; flex-wrap:wrap; gap:12px 30px; margin:5px 0; }
.baseline strong { font-variant-numeric:tabular-nums; }
.caveats { color:var(--muted); font-size:.9rem; max-width:900px; }
.case-section { margin-top:40px; }
.section-head { display:flex; justify-content:space-between; align-items:baseline; flex-wrap:wrap; gap:8px; margin-bottom:12px; }
.controls { display:flex; flex-wrap:wrap; gap:16px; align-items:end; padding:18px 0; border-top:1px solid var(--line); }
.controls[hidden],article[hidden] { display:none; }
.control { display:flex; flex-direction:column; gap:5px; flex:1 1 250px; }
.control.filter { flex:0 1 220px; }
label { font-size:.82rem; font-weight:650; }
input,select { width:100%; min-height:44px; padding:10px 12px; border:1px solid #a69d8e; border-radius:8px; background:#fffdf8; color:var(--ink); font:inherit; }
:focus-visible { outline:3px solid var(--accent); outline-offset:3px; }
article { margin:14px 0; border:1px solid var(--line); border-radius:12px; background:#fffdf8; padding:22px; min-width:0; }
.case-head { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; }
.badges { display:flex; flex-wrap:wrap; justify-content:end; gap:7px; flex-shrink:0; }
.badge { font-size:.72rem; font-weight:750; padding:3px 9px; border:1px solid currentColor; border-radius:6px; }
.change { color:var(--accent); }
.case-metrics { margin:9px 0 15px; color:var(--muted); font-size:.8rem; overflow-wrap:anywhere; }
details { border-top:1px solid var(--line); padding-top:12px; margin-top:12px; }
summary { cursor:pointer; font-size:.9rem; font-weight:650; }
pre { white-space:pre-wrap; overflow-wrap:anywhere; word-break:break-word; font: .84rem/1.65 ui-monospace,SFMono-Regular,Consolas,monospace; margin:12px 0 0; tab-size:4; }
.checks { padding-left:22px; margin:14px 0 0; }
.checks li + li { margin-top:18px; }
.checks pre { margin-top:4px; }
footer { border-top:1px solid var(--line); margin-top:36px; padding-top:18px; color:var(--muted); font-size:.8rem; }
.demo-label { padding:12px 24px; background:#ead6af; color:#4c371b; text-align:center; font-size:.85rem; font-weight:600; }
@media(max-width:700px) {
  main { padding:30px 18px; } .metrics { grid-template-columns:1fr; gap:10px; }
  .metric { padding:20px; } .masthead { gap:12px; } .verdict { padding:6px 12px; font-size:.8rem; }
  .case-head { flex-direction:column; gap:10px; } .badges { justify-content:start; flex-shrink:1; }
  article { padding:18px; } .control.filter { flex:1 1 220px; }
}
@media print {
  body { background:white; color:#111; font-size:10pt; } main { max-width:none; padding:0; }
  .controls,#visible-count { display:none !important; } article[hidden] { display:block !important; }
  .metric,article { background:white; } .metric { padding:12px; }
  h1 { font-size:28pt; } .metric .value { font-size:18pt; } .case-section { margin-top:20px; }
  details::details-content { display:block; content-visibility:visible; }
  details > :not(summary) { display:block !important; } pre { white-space:pre-wrap; overflow:visible; }
  .case-head,summary { break-after:avoid; } .metric,.baseline { break-inside:avoid; }
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


def _case(result, regressions, improvements, currency):
    status = "passed" if result["passed"] else "failed"
    change = "regressions" if result["id"] in regressions else "improvements" if result["id"] in improvements else "unchanged"
    badge = '<span class="badge change">' + ("Regression" if change == "regressions" else "Improvement") + "</span>" if change != "unchanged" else ""
    metrics = result["metrics"]
    latency = _text(metrics["latency_ms"]) + " ms" if metrics["latency_ms"] is not None else "unavailable"
    tokens = f'{metrics["input_tokens"]} in / {metrics["output_tokens"]} out' if metrics["input_tokens"] is not None else "unavailable"
    cost = _text(result["cost"]) + " " + _text(currency) if result["cost"] is not None else "unavailable"
    # JSON text also preserves leading newlines, CR and NUL which HTML parsers
    # would otherwise normalize or discard even after ordinary HTML escaping.
    output = render_json(result["output"]).rstrip("\n")
    checks = []
    for check in result["checks"]:
        label = "PASS" if check["passed"] else "FAIL"
        reason = render_json(check["reason"]).rstrip("\n")
        checks.append(f'<li><strong>{_text(check["type"])} · {label}</strong><pre class="reason">{_text(reason)}</pre></li>')
    return (f'<article data-status="{status}" data-change="{change}">'
            '<div class="case-head"><h3 class="case-id">' + _text(result["id"]) + '</h3><div class="badges">'
            f'<span class="badge {status}">{"PASS" if result["passed"] else "FAIL"}</span>{badge}</div></div>'
            f'<p class="case-metrics">Latency: {latency} · Tokens: {tokens} · Known cost: {cost}</p>'
            '<details><summary>Recorded output · full JSON</summary><pre class="output">' + _text(output) + '</pre></details>'
            '<details><summary>Individual checks · ' + str(sum(check["passed"] for check in result["checks"])) + ' / ' + str(len(checks)) + ' passed</summary><ol class="checks">'
            + "".join(checks) + '</ol></details></article>')


def render_html(report: dict) -> str:
    """Validate and render a deterministic standalone report with full inert text.

    Input/expected values are not retained in schema v1 and are not reconstructed.
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
    verdict = "FAIL" if summary["failed"] else "PASS"
    status = "failed" if summary["failed"] else "passed"
    if latency["observed"]:
        latency_value = _text(latency["mean"]) + ' <small>ms mean</small>'
        latency_detail = f'p50 {_text(latency["p50"])} ms · p95 {_text(latency["p95"])} ms<br>Min {_text(latency["min"])} ms · Max {_text(latency["max"])} ms'
    else:
        latency_value, latency_detail = "Latency unavailable", "No measurements supplied."
    cost_value = _text(cost["total"]) + " " + _text(cost["currency"]) if cost["total"] is not None else "Cost unavailable"
    comparison_text = ('<div class="counts"><span>Regressions <strong>' + str(len(regressions)) + '</strong></span><span>Improvements <strong>'
                       + str(len(improvements)) + '</strong></span><span>Unchanged <strong>' + str(comparison["unchanged"]) + '</strong></span></div>'
                       f'<p class="fine">Baseline passed {comparison["baseline_passed"]} / {cases} · Current passed {comparison["current_passed"]} / {cases}. Comparison is by case ID.</p>') if comparison else '<p>No baseline supplied. Regression and improvement status is unavailable.</p>'
    csp = ("default-src 'none'; script-src 'sha256-" + _hash(_SCRIPT) + "'; style-src 'sha256-" + _hash(_STYLE)
           + "'; script-src-attr 'none'; style-src-attr 'none'; connect-src 'none'; img-src 'none'; font-src 'none'; "
           "object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'")
    return ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="' + escape(csp, quote=True) + '">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>TraceBench evaluation report</title><style>' + _STYLE + '</style></head><body><main>'
            '<header><p class="eyebrow">TraceBench / evaluation report</p><div class="masthead"><h1>Recorded outputs.<br>Inspectable results.</h1>'
            f'<span class="verdict {status}">{verdict}</span></div><p class="intro">Offline deterministic checks, exact known costs, and supplied latency observations. Every result is available for inspection.</p>'
            '<p class="fingerprint">Suite fingerprint · SHA-256<code>' + _text(report["suite_sha256"]) + '</code></p></header>'
            '<section class="metrics" aria-label="Evaluation summary"><div class="metric"><p class="eyebrow">Checks passed</p>'
            f'<div class="value {status}">{summary["passed"]} / {cases}</div><p>{summary["failed"]} failed · All checks must pass for a case to pass.</p></div>'
            '<div class="metric"><p class="eyebrow">Supplied latency</p><div class="value">' + latency_value + '</div><p>' + latency_detail + '</p>'
            f'<p>Coverage {latency["observed"]} / {cases} · Missing {latency["missing"]}.<br>Percentiles use nearest-rank.</p></div>'
            '<div class="metric"><p class="eyebrow">Known token cost</p><div class="value cost">' + cost_value + '</div>'
            f'<p>Priced cases {cost["priced_cases"]} / {cases}.<br>Missing token observations {cost["missing_token_cases"]} / {cases}.</p></div></section>'
            '<section class="baseline" aria-label="Baseline comparison"><p class="eyebrow">Baseline comparison</p>' + comparison_text + '</section>'
            '<p class="caveats">Costs use only supplied prices and token observations. Partial coverage is not a total bill. '
            'Recorded latency is supplied by the caller; TraceBench does not time a provider or verify provenance. '
            'Deterministic checks do not establish semantic quality or factual correctness.</p>'
            '<section class="case-section" aria-labelledby="case-heading"><div class="section-head"><h2 id="case-heading">Case inspection</h2>'
            f'<p id="visible-count" class="fine" role="status" aria-live="polite" aria-atomic="true">{cases} / {cases} cases visible</p></div>'
            '<p class="fine">Case inputs and expected values are not retained in this report schema. Recorded outputs are full JSON values; check reasons are JSON strings. Quotes and escapes preserve all text exactly.</p>'
            '<div class="controls" id="controls" hidden><div class="control"><label for="case-search">Search case ID or recorded output</label>'
            '<input id="case-search" type="search" autocomplete="off" placeholder="Type to narrow the cases"></div>'
            '<div class="control filter"><label for="case-filter">Case status</label><select id="case-filter">'
            '<option value="all">All cases</option><option value="passed">Passed</option><option value="failed">Failed</option>'
            '<option value="regressions">Regressions</option><option value="improvements">Improvements</option></select></div></div>'
            '<noscript><p class="fine">JavaScript is disabled. All cases are visible; use the expandable blocks to inspect full text.</p></noscript>'
            + "".join(_case(result, regressions, improvements, cost["currency"]) for result in report["results"])
            + '</section><footer>TraceBench · Offline evaluation · Report schema 1. '
            'Recorded content is displayed as inert text. Print this page to include every case and full output.</footer></main><script>'
            + _SCRIPT + '</script></body></html>\n')
