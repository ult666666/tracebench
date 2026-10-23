"""Real installed CLI outside the checkout: policy outcomes and safe output."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import venv

ROOT = Path(__file__).resolve().parents[1]


class InstalledPolicyCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import build_backend
        cls.temporary = tempfile.TemporaryDirectory(prefix="tracebench-policy-installed-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        wheel = cls.root / build_backend.build_wheel(cls.root)
        environment = cls.root / "installed"
        venv.EnvBuilder(with_pip=True).create(environment)
        cls.python, cls.cli = environment / "bin/python", environment / "bin/tracebench"
        result = subprocess.run([str(cls.python), "-m", "pip", "install", "--no-index", str(wheel)],
                                cwd=cls.root, capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise AssertionError(result.stderr)

    def setUp(self):
        self.working = tempfile.TemporaryDirectory(dir=self.root)
        self.addCleanup(self.working.cleanup)
        self.directory = Path(self.working.name)
        self.env = dict(os.environ)
        self.env.pop("PYTHONPATH", None)
        self.report = self.directory / "evaluation.json"
        self.rules = self.directory / "rules.json"
        self.rules.write_text('{"schema_version":1,"min_pass_rate":"1"}')
        result = self.run_cli("evaluate", "--cases", ROOT / "fixtures/cases.jsonl", "--outputs", ROOT / "fixtures/clean.jsonl",
                              "--pricing", ROOT / "fixtures/pricing.json", "--report", self.report)
        self.assertEqual(result.returncode, 0, result.stderr)

    def run_cli(self, *args):
        return subprocess.run([str(self.cli), *map(str, args)], cwd=self.directory,
                              env=self.env, capture_output=True, text=True, timeout=30)

    def policy(self, *extra):
        return self.run_cli("policy", "--evaluation", self.report, "--rules", self.rules, *extra)

    def test_policy_accepts_fails_unavailable_invalid_and_markdown_from_installed_cli(self):
        result = self.policy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["accepted"])
        self.rules.write_text('{"schema_version":1,"max_p95_latency_ms":"0"}')
        result = self.policy()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)["rules"][0]["status"], "fail")
        self.rules.write_text('{"schema_version":1,"max_total_cost":{"currency":"EUR","amount":"100"}}')
        destination = self.directory / "policy.md"
        result = self.policy("--format", "markdown", "--report", destination)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn("unavailable", destination.read_text())
        self.rules.write_text('{"schema_version":1,"min_pass_rate":1}')
        result = self.policy()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertNotIn("Traceback", result.stderr)

    def test_policy_output_cannot_overwrite_inputs_through_paths_hardlinks_or_symlinks(self):
        before = {path: path.read_bytes() for path in (self.report, self.rules)}
        for source in (self.report, self.rules):
            for kind in ("direct", "hardlink", "symlink"):
                with self.subTest(source=source, kind=kind):
                    alias = self.directory / (source.stem + "-" + kind)
                    if kind == "direct":
                        alias = source
                    elif kind == "hardlink":
                        os.link(source, alias)
                    else:
                        alias.symlink_to(source)
                    result = self.policy("--report", alias)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn("must not overwrite", result.stderr)
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertEqual(list(self.directory.glob(".tracebench-*")), [])

    def test_failed_atomic_replace_cleans_temporary_file_and_preserves_destination(self):
        destination = self.directory / "existing-directory"
        destination.mkdir()
        result = self.policy("--report", destination)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertTrue(destination.is_dir())
        self.assertEqual(list(destination.iterdir()), [])
        self.assertEqual(list(self.directory.glob(".tracebench-*")), [])
        result = self.policy("--report", self.directory / "missing" / "verdict.json")
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.directory / "missing").exists())

    def test_policy_limits_rules_to_64_kib_and_evaluation_to_64_mib(self):
        self.report.write_bytes(self.report.read_bytes() + b" " * (16 * 1024 * 1024))
        self.assertEqual(self.policy().returncode, 0)
        with self.report.open("wb") as stream:
            stream.truncate(64 * 1024 * 1024 + 1)
        result = self.policy()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("67108864", result.stderr)
        # Restore an evaluation so only the rules reader's bound is tested.
        result = self.run_cli("evaluate", "--cases", ROOT / "fixtures/cases.jsonl", "--outputs", ROOT / "fixtures/clean.jsonl", "--report", self.report)
        self.assertEqual(result.returncode, 0)
        self.rules.write_text('{"schema_version":1,"min_pass_rate":"1"}' + " " * 65536)
        result = self.policy()
        self.assertEqual(result.returncode, 2)
        self.assertIn("65536", result.stderr)

    def test_policy_invalid_report_io_usage_duplicate_keys_and_format_are_exit_two(self):
        for content in ['{}', '{"schema_version":1,"schema_version":1}']:
            self.report.write_text(content)
            self.assertEqual(self.policy().returncode, 2)
        self.report.unlink()
        self.assertEqual(self.policy().returncode, 2)
        self.assertEqual(self.run_cli("policy").returncode, 2)
        self.assertEqual(self.policy("--format", "html").returncode, 2)

    def test_tracked_synthetic_budget_fixtures_pass_and_fail_without_changing_evaluation(self):
        original = self.report.read_bytes()
        for filename, code in [("budget-pass.json", 0), ("budget-fail.json", 1)]:
            result = self.run_cli("policy", "--evaluation", self.report, "--rules", ROOT / "fixtures" / filename)
            self.assertEqual(result.returncode, code, result.stderr)
            verdict = json.loads(result.stdout)
            self.assertEqual(verdict["evaluation"], {"cases": 6, "passed": 6, "failed": 0, "regressions": 0})
            self.assertEqual([r["status"] for r in verdict["rules"]], ["pass", "pass" if code == 0 else "fail", "pass"])
        self.assertEqual(self.report.read_bytes(), original)

    def test_original_evaluate_exit_zero_one_two_three_is_unchanged(self):
        baseline = self.directory / "baseline.json"
        args = ["evaluate", "--cases", ROOT / "fixtures/cases.jsonl", "--outputs", ROOT / "fixtures/clean.jsonl"]
        self.assertEqual(self.run_cli(*args, "--report", baseline).returncode, 0)
        args[-1] = ROOT / "fixtures/regression.jsonl"
        self.assertEqual(self.run_cli(*args).returncode, 1)
        self.assertEqual(self.run_cli(*args, "--baseline", baseline).returncode, 3)
        args[-1] = self.directory / "absent.jsonl"
        self.assertEqual(self.run_cli(*args).returncode, 2)


if __name__ == "__main__":
    unittest.main()
