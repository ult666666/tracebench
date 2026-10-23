"""Bounded offline HTML/CLI verification, with optional existing Playwright tooling."""

import argparse
from decimal import Decimal
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tracebench.evaluate import compare_baseline, evaluate
from tracebench.html_report import render_html
from tracebench.io import load_cases, load_outputs, load_pricing
from tracebench.report import render_json

DEMO_NOTICE = '<aside class="demo-label">Synthetic recorded-output demo · All outputs, latency observations, token counts and prices are invented fixtures. No provider was called.</aside>'


def sample_report():
    cases, pricing = load_cases(ROOT / "fixtures/cases.jsonl"), load_pricing(ROOT / "fixtures/pricing.json")
    report = evaluate(cases, load_outputs(ROOT / "fixtures/regression.jsonl"), pricing=pricing)
    report["comparison"] = compare_baseline(report, evaluate(cases, load_outputs(ROOT / "fixtures/baseline.jsonl"), pricing=pricing))
    # The example's provenance notice is fixed, not inferred for arbitrary reports.
    return (render_html(report).replace("<body>", "<body>" + DEMO_NOTICE, 1)
            .replace("<title>TraceBench evaluation report</title>", "<title>TraceBench · Synthetic recorded-output demo</title>", 1))


def browser_fixture(directory):
    hostile_id = '<svg/onload="globalThis.pwned=2">'
    hostile = '\n</script><img src="https://evil.invalid/x" onerror="globalThis.pwned=1">&你好\r\n\u0000' + "Long full output " * 100 + "X" * 2048
    keys = ["regressed", "improved", "stable-pass", "stable-fail", hostile_id]
    cases = {key: {"id": key, "input": "synthetic", "checks": [{"type": "exact", "expected": "ok"}]} for key in keys}
    cases["stable-pass"]["checks"] = [{"type": "json_subset", "expected": {}}]
    recorded = {"exact": Decimal("9007199254740993"), "markup": "<b>structured search</b>"}
    baseline = evaluate(cases, {key: {"id": key, "output": output} for key, output in zip(keys, ["ok", "bad", recorded, "bad", "bad"])})
    report = evaluate(cases, {key: {"id": key, "output": output} for key, output in zip(keys, ["bad", "ok", recorded, "bad", hostile])})
    report["comparison"] = compare_baseline(report, baseline)
    (directory / "hostile.html").write_text(render_html(report), encoding="utf-8")
    (directory / "expected.json").write_text(json.dumps({"hostile": hostile, "hostile_id": hostile_id}, ensure_ascii=False), encoding="utf-8")


def verify(directory, executable):
    cases, pricing = load_cases(ROOT / "fixtures/cases.jsonl"), load_pricing(ROOT / "fixtures/pricing.json")
    baseline = evaluate(cases, load_outputs(ROOT / "fixtures/baseline.jsonl"), pricing=pricing)
    baseline_path = directory / "baseline.json"
    baseline_path.write_text(render_json(baseline), encoding="utf-8")
    common = executable + ["evaluate", "--cases", str(ROOT / "fixtures/cases.jsonl"), "--pricing", str(ROOT / "fixtures/pricing.json"), "--format", "html"]
    cwd = directory if len(executable) == 1 else ROOT
    for name, compared, code in [("clean.jsonl", False, 0), ("regression.jsonl", False, 1), ("regression.jsonl", True, 3)]:
        report = evaluate(cases, load_outputs(ROOT / "fixtures" / name), pricing=pricing)
        args = common + ["--outputs", str(ROOT / "fixtures" / name)]
        if compared:
            report["comparison"] = compare_baseline(report, baseline)
            args += ["--baseline", str(baseline_path)]
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=15)
        assert result.returncode == code, (result.returncode, result.stderr)
        assert result.stdout == render_html(report) and not result.stderr
        saved = directory / ("regression.html" if compared else name + ".html")
        saved.write_text("previous content", encoding="utf-8")
        written = subprocess.run(args + ["--report", str(saved)], cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=15)
        assert written.returncode == code and not written.stdout and not written.stderr
        assert saved.read_text(encoding="utf-8") == result.stdout
        assert not list(directory.glob(".tracebench-*"))
    copied_cases = directory / "cases.jsonl"
    copied_cases.write_bytes((ROOT / "fixtures/cases.jsonl").read_bytes())
    refused = subprocess.run(executable + ["evaluate", "--cases", str(copied_cases), "--outputs", str(ROOT / "fixtures/clean.jsonl"),
                             "--format", "html", "--report", str(copied_cases)], cwd=cwd, capture_output=True, text=True, timeout=15)
    assert refused.returncode == 2 and "must not overwrite" in refused.stderr and not refused.stdout
    assert copied_cases.read_bytes() == (ROOT / "fixtures/cases.jsonl").read_bytes()
    missing = subprocess.run(common + ["--outputs", str(directory / "missing.jsonl")], cwd=cwd, capture_output=True, text=True, timeout=15)
    assert missing.returncode == 2 and not missing.stdout and "Traceback" not in missing.stderr
    sample = sample_report()
    assert (ROOT / "docs/sample-report.html").read_text(encoding="utf-8") == sample, "Regenerate sample with --write-sample"
    (directory / "sample.html").write_text(sample, encoding="utf-8")
    browser_fixture(directory)
    print("HTML generation and real CLI verified: stdout=files=renderer, exits=0/1/2/3, atomic replacement, input protection, reproducible synthetic sample.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", type=Path, help="installed CLI; run it outside checkout")
    parser.add_argument("--write-sample", action="store_true", help="regenerate docs/sample-report.html from committed fixtures")
    parser.add_argument("--browser-module", type=Path, help="existing Playwright module directory; no installation is attempted")
    parser.add_argument("--require-browser", action="store_true", help="fail if optional local browser tooling is unavailable")
    parser.add_argument("--artifacts", type=Path, help="keep generated HTML and desktop/mobile screenshots in this directory")
    args = parser.parse_args()
    if args.write_sample:
        (ROOT / "docs/sample-report.html").write_text(sample_report(), encoding="utf-8")
    browser_module = args.browser_module or ROOT.parent / "impact-ledger/node_modules/playwright"
    node = shutil.which("node")
    available = node is not None and (browser_module / "package.json").is_file()
    if args.require_browser and not available:
        parser.error("Existing Node/Playwright tooling was not found; use --browser-module PATH")
    executable = [str(args.cli.resolve())] if args.cli else [sys.executable, "-m", "tracebench"]
    with tempfile.TemporaryDirectory() as temporary:
        directory = args.artifacts.resolve() if args.artifacts else Path(temporary)
        directory.mkdir(parents=True, exist_ok=True)
        verify(directory, executable)
        if available:
            subprocess.run([node, str(ROOT / "scripts/verify_html_browser.cjs"), str(directory), str(browser_module.resolve())],
                           check=True, cwd=directory, timeout=60)
        else:
            print("Browser checks SKIPPED: no existing Node/Playwright tooling. Python/CLI checks ran.")


if __name__ == "__main__":
    main()
