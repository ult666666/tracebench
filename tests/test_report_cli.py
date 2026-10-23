from copy import deepcopy
from decimal import Decimal, localcontext, ROUND_DOWN
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tracebench.evaluate import evaluate
from tracebench.io import strict_json
from tracebench.report import render_json, render_markdown

ROOT = Path(__file__).resolve().parents[1]


class ReportTests(unittest.TestCase):
    def report(self):
        case_id = '<img src=x onerror="alert(1)">|[x](https://evil)'
        return evaluate({case_id: {"id": case_id, "input": "synthetic", "checks": [{"type": "exact", "expected": "ok"}]}},
                        {case_id: {"id": case_id, "output": "<script>\n|**oops** & `x`"}})

    def test_markdown_escapes_raw_html_links_tables_newlines_and_code(self):
        markdown = render_markdown(self.report())
        for forbidden in ["<img", "<script", "[x](", "**oops**", "`x`", "\n|**"]:
            self.assertNotIn(forbidden, markdown)
        self.assertIn("&#x3C;", markdown)
        self.assertIn("&#x7C;", markdown)
        self.assertIn("1 / 1", markdown)

    def test_json_escapes_html_but_round_trips_exact_decimal_numbers(self):
        report = self.report()
        report["results"][0]["output"] = {"html": "<>&\u2028\u2029", "number": Decimal("0.12345678901234567890123456789")}
        encoded = render_json(report)
        self.assertNotIn("<", encoded)
        self.assertIn("\\u003c", encoded)
        self.assertEqual(strict_json(encoded), report)

    def test_report_is_deterministic_and_missing_metrics_are_labeled(self):
        report = self.report()
        self.assertEqual(render_json(report), render_json(deepcopy(report)))
        markdown = render_markdown(report)
        self.assertIn("unavailable", markdown)
        self.assertIn("0 / 1", markdown)

    def test_ambient_rounding_does_not_change_latency_mean(self):
        cases = {str(i): {"id": str(i), "input": "", "checks": [{"type": "exact", "expected": "x"}]} for i in range(3)}
        outputs = {str(i): {"id": str(i), "output": "x", "metrics": {"latency_ms": value}} for i, value in enumerate([0, 0, 2])}
        with localcontext() as ctx:
            ctx.rounding = ROUND_DOWN
            report = evaluate(cases, outputs)
        self.assertEqual(report["summary"]["latency_ms"]["mean"], "0.666667")


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)

    def cli(self, *args):
        return subprocess.run([sys.executable, "-m", "tracebench", *map(str, args)], cwd=ROOT,
                              capture_output=True, text=True, encoding="utf-8", timeout=10)

    def evaluate_args(self, outputs="clean.jsonl"):
        return ["evaluate", "--cases", ROOT / "fixtures/cases.jsonl", "--outputs", ROOT / "fixtures" / outputs,
                "--pricing", ROOT / "fixtures/pricing.json"]

    def test_clean_candidate_exit_zero_and_machine_report(self):
        result = self.cli(*self.evaluate_args())
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["summary"]["cases"], 6)
        self.assertEqual(report["summary"]["passed"], 6)
        self.assertEqual(result.stderr, "")

    def test_failing_candidate_without_baseline_exit_one(self):
        result = self.cli(*self.evaluate_args("regression.jsonl"))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)["summary"]["failed"], 2)

    def test_baseline_join_exit_three_and_markdown_report(self):
        baseline = self.dir / "baseline.json"
        created = self.cli(*self.evaluate_args("baseline.jsonl"), "--report", baseline)
        self.assertEqual(created.returncode, 0, created.stderr)
        self.assertEqual(created.stdout, "")
        candidate = self.dir / "candidate.md"
        result = self.cli(*self.evaluate_args("regression.jsonl"), "--baseline", baseline,
                          "--format", "markdown", "--report", candidate)
        self.assertEqual(result.returncode, 3, result.stderr)
        markdown = candidate.read_text(encoding="utf-8")
        self.assertIn("Regressions: 2", markdown)
        clean = self.cli(*self.evaluate_args(), "--baseline", baseline)
        self.assertEqual(clean.returncode, 0, clean.stderr)

    def test_invalid_json_and_missing_file_exit_two_without_traceback(self):
        bad = self.dir / "bad.jsonl"
        bad.write_text('{"id":"en-greeting","output":NaN}', encoding="utf-8")
        for path in [bad, self.dir / "absent"]:
            result = self.cli("evaluate", "--cases", ROOT / "fixtures/cases.jsonl", "--outputs", path)
            self.assertEqual(result.returncode, 2)
            self.assertIn("error", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(result.stdout, "")

    def test_baseline_missing_ids_exit_two(self):
        baseline = self.dir / "baseline.json"
        self.assertEqual(self.cli(*self.evaluate_args(), "--report", baseline).returncode, 0)
        value = json.loads(baseline.read_text(encoding="utf-8"))
        value["results"][0]["id"] = "different"
        baseline.write_text(json.dumps(value), encoding="utf-8")
        result = self.cli(*self.evaluate_args(), "--baseline", baseline)
        self.assertEqual(result.returncode, 2)
        self.assertIn("missing=", result.stderr)
        self.assertIn("extra=", result.stderr)

    def test_refuses_to_overwrite_inputs(self):
        cases = self.dir / "cases.jsonl"
        original = (ROOT / "fixtures/cases.jsonl").read_bytes()
        cases.write_bytes(original)
        result = self.cli("evaluate", "--cases", cases, "--outputs", ROOT / "fixtures/clean.jsonl", "--report", cases)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(cases.read_bytes(), original)

    def test_write_error_exit_two_without_partial_report(self):
        report = self.dir / "does-not-exist/report.json"
        result = self.cli(*self.evaluate_args(), "--report", report)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(report.exists())
        self.assertNotIn("Traceback", result.stderr)

    def test_usage_and_version(self):
        self.assertEqual(self.cli().returncode, 2)
        self.assertEqual(self.cli("--version").returncode, 0)
        help_result = self.cli("evaluate", "--help")
        self.assertEqual(help_result.returncode, 0)
        self.assertIn("--baseline", help_result.stdout)


if __name__ == "__main__":
    unittest.main()
