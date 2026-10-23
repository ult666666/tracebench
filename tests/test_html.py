"""Behavioral checks for the standalone, inert HTML report and real CLI."""

from copy import deepcopy
from decimal import Decimal
import base64
import hashlib
from html.parser import HTMLParser
import importlib.util
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from tracebench.evaluate import compare_baseline, evaluate
from tracebench.io import InputError, load_cases, load_outputs, load_pricing
from tracebench.report import render_json

ROOT = Path(__file__).resolve().parents[1]
HOSTILE = '</script><img src="https://evil.invalid/x" onerror="globalThis.pwned=1">&你好\n' + 'long output ' * 100


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.tags, self.text = [], []
        self.capture, self.outputs, self.reasons = None, [], []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag == "pre" and dict(attrs).get("class") in {"output", "reason"}:
            self.capture = self.outputs if dict(attrs)["class"] == "output" else self.reasons
            self.capture.append("")

    def handle_endtag(self, tag):
        if tag == "pre":
            self.capture = None

    def handle_data(self, data):
        self.text.append(data)
        if self.capture is not None:
            self.capture[-1] += data


def fixture_report(name="regression.jsonl"):
    cases = load_cases(ROOT / "fixtures/cases.jsonl")
    pricing = load_pricing(ROOT / "fixtures/pricing.json")
    report = evaluate(cases, load_outputs(ROOT / "fixtures" / name), pricing=pricing)
    report["comparison"] = compare_baseline(report, evaluate(cases, load_outputs(ROOT / "fixtures/baseline.jsonl"), pricing=pricing))
    return report


class HtmlTests(unittest.TestCase):
    def render(self, report):
        self.assertIsNotNone(importlib.util.find_spec("tracebench.html_report"), "HTML renderer is missing")
        from tracebench.html_report import render_html
        return render_html(report)

    def test_complete_metrics_and_comparison_are_inspectable(self):
        document = Document(self.render(fixture_report()))
        text = " ".join(document.text)
        for value in ["FAIL", "4 / 6", "Regressions", "Improvements", "2", "0",
                      "nearest-rank", "0.0000327", "USD", "6 / 6", "en-greeting", "zh-location",
                      "Suite fingerprint", "supplied by the caller", "not retained"]:
            self.assertIn(value, text)
        self.assertEqual(sum(tag == "article" for tag, _ in document.tags), 6)

    def test_hostile_text_never_becomes_markup_or_attributes(self):
        key = '<svg/onload="globalThis.pwned=2">'
        report = evaluate({key: {"id": key, "input": "unretained", "checks": [{"type": "exact", "expected": "ok"}]}},
                          {key: {"id": key, "output": HOSTILE}})
        report["results"][0]["checks"][0]["reason"] = HOSTILE
        html = self.render(report)
        document = Document(html)
        from tracebench.io import strict_json
        self.assertEqual(strict_json(document.outputs[0]), HOSTILE)
        self.assertTrue(document.reasons, "Full check reasons must be individually inspectable")
        self.assertEqual(strict_json(document.reasons[0]), HOSTILE)
        self.assertIn(key, "".join(document.text))
        self.assertNotIn("unretained", "".join(document.text))
        self.assertFalse(any(tag in {"img", "svg", "iframe", "a", "form"} for tag, _ in document.tags))
        self.assertFalse(any(name.startswith("on") for _, attrs in document.tags for name in attrs))
        self.assertFalse(any(key in value or "evil.invalid" in value for _, attrs in document.tags for value in attrs.values() if value))
        self.assertEqual(sum(tag == "script" for tag, _ in document.tags), 1)

    def test_csp_hashes_only_fixed_script_and_style(self):
        html = self.render(fixture_report())
        document = Document(html)
        csp = next(attrs["content"] for tag, attrs in document.tags if tag == "meta" and attrs.get("http-equiv") == "Content-Security-Policy")
        for tag in ["script", "style"]:
            contents = re.findall(fr"<{tag}>(.*?)</{tag}>", html, re.S)
            self.assertEqual(len(contents), 1)
            digest = base64.b64encode(hashlib.sha256(contents[0].encode()).digest()).decode()
            self.assertIn(f"{tag}-src 'sha256-{digest}'", csp)
        for directive in ["default-src 'none'", "connect-src 'none'", "base-uri 'none'", "form-action 'none'", "frame-src 'none'"]:
            self.assertIn(directive, csp)
        self.assertNotIn("unsafe-inline", csp)
        self.assertNotIn("unsafe-eval", csp)

    def test_exact_decimal_and_full_output_are_preserved(self):
        report = evaluate({"precise": {"id": "precise", "input": "", "checks": [{"type": "json_subset", "expected": {}}]}},
                          {"precise": {"id": "precise", "output": {"n": Decimal("0.12345678901234567890123456789")},
                                       "metrics": {"input_tokens": 1, "output_tokens": 1, "latency_ms": Decimal("0.0000001")}}},
                          pricing={"currency": "USD", "input_per_million": "0.0000001", "output_per_million": "0.0000002"})
        text = "".join(Document(self.render(report)).text)
        for exact in ["0.12345678901234567890123456789", "0.0000000000003", "0.0000001"]:
            self.assertIn(exact, text)

    def test_string_output_json_retains_controls_and_leading_newline(self):
        from tracebench.io import strict_json
        output = '\n\r\n\x00</script>\\literal"你好'
        report = evaluate({"x": {"id": "x", "input": "", "checks": [{"type": "exact", "expected": "ok"}]}},
                          {"x": {"id": "x", "output": output}})
        document = Document(self.render(report))
        self.assertTrue(document.outputs[0].startswith('"'), "String outputs must use an exact JSON representation")
        self.assertEqual(strict_json(document.outputs[0]), output)

    def test_missing_coverage_and_absent_comparison_are_honest(self):
        report = evaluate({"x": {"id": "x", "input": "", "checks": [{"type": "exact", "expected": "ok"}]}},
                          {"x": {"id": "x", "output": "ok"}})
        text = " ".join(Document(self.render(report)).text)
        for value in ["PASS", "0 / 1", "Latency unavailable", "Cost unavailable", "No baseline supplied", "not a total bill"]:
            self.assertIn(value, text)

    def test_every_comparison_status_and_accessible_controls(self):
        cases = {key: {"id": key, "input": "", "checks": [{"type": "exact", "expected": "ok"}]} for key in ["regressed", "improved", "still-pass", "still-fail"]}
        baseline = evaluate(cases, {key: {"id": key, "output": out} for key, out in zip(cases, ["ok", "bad", "ok", "bad"])})
        current = evaluate(cases, {key: {"id": key, "output": out} for key, out in zip(cases, ["bad", "ok", "ok", "bad"])})
        current["comparison"] = compare_baseline(current, baseline)
        document = Document(self.render(current))
        articles = [attrs for tag, attrs in document.tags if tag == "article"]
        self.assertEqual([attrs["data-change"] for attrs in articles], ["regressions", "improvements", "unchanged", "unchanged"])
        self.assertEqual([attrs["data-status"] for attrs in articles], ["failed", "passed", "passed", "failed"])
        self.assertFalse(any("hidden" in attrs for attrs in articles))
        self.assertTrue(any(tag == "label" and attrs.get("for") == "case-search" for tag, attrs in document.tags))
        self.assertTrue(any(attrs.get("role") == "status" and attrs.get("aria-live") == "polite" for _, attrs in document.tags))
        self.assertEqual([attrs["value"] for tag, attrs in document.tags if tag == "option"], ["all", "passed", "failed", "regressions", "improvements"])

    def test_render_is_deterministic_and_does_not_mutate_report(self):
        report = fixture_report()
        original = deepcopy(report)
        self.assertEqual(self.render(report), self.render(original))
        self.assertEqual(report, original)

    def test_rejects_inconsistent_report_instead_of_presenting_false_metrics(self):
        report = fixture_report()
        report["summary"]["passed"] = 6
        with self.assertRaises(InputError):
            self.render(report)


class HtmlCliTests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run([sys.executable, "-m", "tracebench", *map(str, args)], cwd=ROOT,
                              capture_output=True, text=True, encoding="utf-8", timeout=10)

    def args(self, name="clean.jsonl"):
        return ["evaluate", "--cases", ROOT / "fixtures/cases.jsonl", "--outputs", ROOT / "fixtures" / name,
                "--pricing", ROOT / "fixtures/pricing.json", "--format", "html"]

    def test_html_stdout_exit_zero_and_failure_exit_one(self):
        for name, code in [("clean.jsonl", 0), ("regression.jsonl", 1)]:
            with self.subTest(name=name):
                result = self.cli(*self.args(name))
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertTrue(result.stdout.startswith("<!doctype html>"))
                self.assertEqual(result.stderr, "")

    def test_atomic_report_regression_exit_three_and_no_temporary_files(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline, destination = Path(directory) / "baseline.json", Path(directory) / "report.html"
            baseline.write_text(render_json(fixture_report("baseline.jsonl")), encoding="utf-8")
            destination.write_text("old report", encoding="utf-8")
            result = self.cli(*self.args("regression.jsonl"), "--baseline", baseline, "--report", destination)
            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertIn("Regressions", destination.read_text(encoding="utf-8"))
            self.assertEqual(sorted(path.name for path in Path(directory).iterdir()), ["baseline.json", "report.html"])

    def test_html_errors_preserve_inputs_and_existing_report(self):
        with tempfile.TemporaryDirectory() as directory:
            cases, destination = Path(directory) / "cases.jsonl", Path(directory) / "report.html"
            original = (ROOT / "fixtures/cases.jsonl").read_bytes()
            cases.write_bytes(original)
            overwrite = self.cli("evaluate", "--cases", cases, "--outputs", ROOT / "fixtures/clean.jsonl", "--format", "html", "--report", cases)
            self.assertEqual(overwrite.returncode, 2)
            self.assertIn("must not overwrite", overwrite.stderr)
            self.assertEqual(cases.read_bytes(), original)
            destination.write_text("keep me", encoding="utf-8")
            bad = self.cli("evaluate", "--cases", cases, "--outputs", Path(directory) / "missing", "--format", "html", "--report", destination)
            self.assertEqual(bad.returncode, 2)
            self.assertEqual(destination.read_text(encoding="utf-8"), "keep me")
            self.assertEqual(bad.stdout, "")


if __name__ == "__main__":
    unittest.main()
