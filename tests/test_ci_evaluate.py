"""Consumer-visible runner boundaries; real CLI subprocesses, no network calls."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import venv

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/ci_evaluate.py"


class CiEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.workspace = self.root / "caller workspace"
        self.workspace.mkdir()
        shutil.copytree(ROOT / "fixtures", self.workspace / "fixtures")
        self.runtime = self.root / "runtime"
        self.runtime.mkdir()
        self.output = self.root / "github-output"
        self.summary = self.root / "summary.md"
        self.output.touch()
        self.summary.touch()
        # Generate a real baseline without depending on the new tracked file.
        baseline = subprocess.run([sys.executable, "-m", "tracebench", "evaluate", "--cases",
                                   str(self.workspace / "fixtures/cases.jsonl"), "--outputs",
                                   str(self.workspace / "fixtures/baseline.jsonl"), "--pricing",
                                   str(self.workspace / "fixtures/pricing.json"), "--report",
                                   str(self.workspace / "baseline.json")], cwd=ROOT, capture_output=True, timeout=10)
        self.assertEqual(baseline.returncode, 0, baseline.stderr)
        self.env = {**os.environ, "PYTHONPATH": str(ROOT), "TB_WORKSPACE": str(self.workspace),
                    "RUNNER_TEMP": str(self.runtime), "TB_CASES": "fixtures/cases.jsonl",
                    "TB_OUTPUTS": "fixtures/clean.jsonl", "TB_PRICING": "fixtures/pricing.json",
                    "TB_BASELINE": "baseline.json", "TB_EXPECTATION": "pass", "TB_SOURCE_SHA": "a" * 40,
                    "GITHUB_OUTPUT": str(self.output), "GITHUB_STEP_SUMMARY": str(self.summary)}

    def run_stage(self, stage="evaluate", **changes):
        return subprocess.run([sys.executable, str(RUNNER), stage], env={**self.env, **changes},
                              cwd=self.root, capture_output=True, text=True, timeout=20)

    def handoff(self):
        return dict(line.split("=", 1) for line in self.output.read_text().splitlines())

    def test_reports_are_bounded_generated_artifacts_and_gate_preserves_all_valid_outcomes(self):
        for candidate, baseline, code, passed, failed in [
            ("clean.jsonl", "baseline.json", 0, 6, 0),
            ("regression.jsonl", "", 1, 4, 2),
            ("regression.jsonl", "baseline.json", 3, 4, 2),
        ]:
            with self.subTest(code=code):
                self.output.write_text("")
                before = {p: p.read_bytes() for p in self.workspace.rglob("*") if p.is_file()}
                result = self.run_stage(TB_OUTPUTS="fixtures/" + candidate, TB_BASELINE=baseline)
                self.assertEqual(result.returncode, 0, result.stderr)
                handoff = self.handoff()
                self.assertEqual(handoff["exit_code"], str(code))
                directory = Path(handoff["report_dir"])
                self.assertEqual(directory.parent, self.runtime)
                self.assertEqual({p.name for p in directory.iterdir()},
                                 {"report.json", "report.md", "report.html", "provenance.json", "gate.json"})
                report = json.loads((directory / "report.json").read_text())
                self.assertEqual((report["summary"]["passed"], report["summary"]["failed"]), (passed, failed))
                self.assertIn("<!doctype html>", (directory / "report.html").read_text().lower())
                self.assertIn("TraceBench", (directory / "report.md").read_text())
                provenance = json.loads((directory / "provenance.json").read_text())
                self.assertEqual(provenance["source_sha"], "a" * 40)
                self.assertEqual(provenance["inputs"]["cases"]["sha256"],
                                 hashlib.sha256(before[self.workspace / "fixtures/cases.jsonl"]).hexdigest())
                self.assertEqual(provenance["suite_sha256"], report["suite_sha256"])
                self.assertIn(f"Evaluation exit: **{code}**", self.summary.read_text())
                # Models upload's handoff: copying only this directory retains all reports on 0/1/3.
                uploaded = self.root / f"upload-{code}"
                shutil.copytree(directory, uploaded)
                self.assertEqual((uploaded / "report.json").read_bytes(), (directory / "report.json").read_bytes())
                gated = self.run_stage("gate", TB_REPORT_DIR=str(directory))
                self.assertEqual(gated.returncode, code, gated.stderr)
                self.assertEqual(before, {p: p.read_bytes() for p in self.workspace.rglob("*") if p.is_file()})

    def test_expected_regression_is_an_explicit_assertion_not_a_green_normal_gate(self):
        for candidate, want in [("regression.jsonl", 0), ("clean.jsonl", 2)]:
            with self.subTest(candidate=candidate):
                self.output.write_text("")
                result = self.run_stage(TB_OUTPUTS="fixtures/" + candidate, TB_EXPECTATION="regression")
                self.assertEqual(result.returncode, 0, result.stderr)
                gated = self.run_stage("gate", TB_REPORT_DIR=self.handoff()["report_dir"], TB_EXPECTATION="regression")
                self.assertEqual(gated.returncode, want, gated.stderr)
        invalid = self.run_stage(TB_EXPECTATION="ignore")
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("expectation must be pass or regression", invalid.stderr)

    def test_argv_paths_allow_spaces_leading_hyphens_and_literal_shell_metacharacters(self):
        for name in ["-candidate.jsonl", "candidate outputs.jsonl", "candidate;$(touch PWNED)`echo nope`.jsonl"]:
            with self.subTest(name=name):
                shutil.copyfile(self.workspace / "fixtures/clean.jsonl", self.workspace / name)
                result = self.run_stage(TB_OUTPUTS=name)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse((self.root / "PWNED").exists())

    def test_invalid_input_never_produces_an_upload_handoff_or_overwrites_input(self):
        (self.workspace / "invalid.jsonl").write_text('{"id":"broken"}\n')
        for changes in [{"TB_OUTPUTS": "invalid.jsonl"}, {"TB_OUTPUTS": "missing.jsonl"},
                        {"TB_CASES": "fixtures"}, {"TB_OUTPUTS": "../outside.jsonl"},
                        {"TB_OUTPUTS": str(self.workspace / "fixtures/clean.jsonl")},
                        {"TB_OUTPUTS": "fixtures/./clean.jsonl"}, {"TB_OUTPUTS": "fixtures//clean.jsonl"},
                        {"TB_OUTPUTS": "bad\npath"}, {"TB_OUTPUTS": "a" * 1025},
                        {"TB_SOURCE_SHA": "main"}]:
            with self.subTest(changes=changes):
                self.output.write_text("")
                result = self.run_stage(**changes)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(self.output.read_text(), "")
                self.assertNotIn("Traceback", result.stderr)
                self.assertIn("TraceBench CI:", result.stderr)
                self.assertEqual((self.workspace / "invalid.jsonl").read_text(), '{"id":"broken"}\n')
        self.assertFalse(list(self.runtime.glob("tracebench-*/gate.json")))

    def test_symlink_components_private_runtime_paths_and_nonregular_files_are_refused(self):
        (self.workspace / "linked.jsonl").symlink_to(self.workspace / "fixtures/clean.jsonl")
        (self.workspace / "linked-dir").symlink_to(self.workspace / "fixtures", target_is_directory=True)
        os.mkfifo(self.workspace / "pipe")
        for part in [".git", ".env", "node_modules", "__pycache__", ".venv", "venv"]:
            (self.workspace / part).mkdir()
            shutil.copyfile(self.workspace / "fixtures/clean.jsonl", self.workspace / part / "out.jsonl")
        for value in ["linked.jsonl", "linked-dir/clean.jsonl", "pipe"] + [p + "/out.jsonl" for p in [".git", ".env", "node_modules", "__pycache__", ".venv", "venv"]]:
            with self.subTest(value=value):
                result = self.run_stage(TB_OUTPUTS=value)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(self.output.read_text(), "")

    def test_oversize_input_is_rejected_before_parsing_and_staging_cannot_be_in_workspace(self):
        big = self.workspace / "big.jsonl"
        with big.open("wb") as stream:
            stream.truncate(10 * 1024 * 1024 + 1)
        for changes in [{"TB_OUTPUTS": "big.jsonl"}, {"RUNNER_TEMP": str(self.workspace)}]:
            with self.subTest(changes=changes):
                result = self.run_stage(**changes)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(self.output.read_text(), "")

    def test_gate_refuses_untrusted_handoff_changed_reports_and_outside_directory(self):
        result = self.run_stage(TB_OUTPUTS="fixtures/regression.jsonl")
        self.assertEqual(result.returncode, 0, result.stderr)
        directory = Path(self.handoff()["report_dir"])
        gate = directory / "gate.json"
        original = gate.read_bytes()
        for invalid in ['{"exit_code":0}', '{"exit_code":true}', 'invalid']:
            gate.write_text(invalid)
            self.assertEqual(self.run_stage("gate", TB_REPORT_DIR=str(directory)).returncode, 2)
        changed = json.loads(original)
        changed["exit_code"] = 0
        gate.write_text(json.dumps(changed))
        self.assertEqual(self.run_stage("gate", TB_REPORT_DIR=str(directory)).returncode, 2)
        gate.write_bytes(original)
        (directory / "report.md").write_text("changed after evaluation")
        self.assertEqual(self.run_stage("gate", TB_REPORT_DIR=str(directory)).returncode, 2)
        self.assertEqual(self.run_stage("gate", TB_REPORT_DIR=str(self.workspace)).returncode, 2)
        linked = self.runtime / "tracebench-linked"
        linked.symlink_to(directory, target_is_directory=True)
        self.assertEqual(self.run_stage("gate", TB_REPORT_DIR=str(linked)).returncode, 2)


class InstalledGeneratedReportLimitTests(unittest.TestCase):
    """Exercise the runner with a real wheel installed outside the checkout."""

    @classmethod
    def setUpClass(cls):
        import build_backend
        cls.temporary = tempfile.TemporaryDirectory(prefix="tracebench-report-limits-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        wheel = cls.root / build_backend.build_wheel(cls.root)
        environment = cls.root / "installed"
        venv.EnvBuilder(with_pip=True).create(environment)
        cls.python = environment / "bin/python"
        install = subprocess.run([str(cls.python), "-m", "pip", "install", "--no-index", str(wheel)],
                                 cwd=cls.root, capture_output=True, text=True, timeout=60)
        if install.returncode:
            raise AssertionError(install.stderr)

    def setUp(self):
        self.working = tempfile.TemporaryDirectory(dir=self.root)
        self.addCleanup(self.working.cleanup)
        self.directory = Path(self.working.name)
        self.workspace = self.directory / "caller"
        self.workspace.mkdir()
        self.runtime = self.directory / "runtime"
        self.runtime.mkdir()
        self.output = self.directory / "github-output"
        self.output.touch()
        self.env = {**os.environ, "TB_WORKSPACE": str(self.workspace), "RUNNER_TEMP": str(self.runtime),
                    "TB_CASES": "cases.jsonl", "TB_OUTPUTS": "outputs.jsonl", "TB_BASELINE": "",
                    "TB_PRICING": "", "TB_EXPECTATION": "pass", "TB_SOURCE_SHA": "a" * 40,
                    "GITHUB_OUTPUT": str(self.output), "GITHUB_STEP_SUMMARY": str(self.directory / "summary.md")}
        self.env.pop("PYTHONPATH", None)
        cases = [{"id": f"large-{i}", "input": "synthetic", "checks": [{"type": "contains", "expected": "<"}]}
                 for i in range(6)]
        (self.workspace / "cases.jsonl").write_text("".join(json.dumps(row) + "\n" for row in cases))
        self.recorded_outputs(large=False)
        self.cli_report("json", self.workspace / "baseline.json", 0)

    def recorded_outputs(self, *, large=True, failed=False):
        rows = [{"id": f"large-{i}", "output": (">" if failed and i == 5 else "<") * (500_000 if large else 1)}
                for i in range(6)]
        (self.workspace / "outputs.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
        self.assertLess((self.workspace / "outputs.jsonl").stat().st_size, 10 * 1024 * 1024)

    def cli_report(self, format_name, destination, code, *, baseline=""):
        command = [str(self.python), "-m", "tracebench", "evaluate", "--cases", str(self.workspace / "cases.jsonl"),
                   "--outputs", str(self.workspace / "outputs.jsonl"), "--format", format_name, "--report", str(destination)]
        if baseline:
            command += ["--baseline", str(self.workspace / baseline)]
        result = subprocess.run(command, cwd=self.directory, env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, code, result.stderr)

    def stage(self, name, **changes):
        return subprocess.run([str(self.python), str(RUNNER), name], cwd=self.directory,
                              env={**self.env, **changes}, capture_output=True, text=True, timeout=60)

    def assert_large_generated_json(self, directory):
        size = (directory / "report.json").stat().st_size
        self.assertGreater(size, 16 * 1024 * 1024)
        self.assertLess(size, 64 * 1024 * 1024)

    def test_evaluate_and_upload_handoff_accept_large_reports_from_installed_cli(self):
        # Removing the explicit generated-report read bound rejects otherwise valid input on all three outcomes.
        for code, failed, baseline in [(0, False, ""), (1, True, ""), (3, True, "baseline.json")]:
            with self.subTest(code=code):
                self.output.write_text("")
                self.recorded_outputs(failed=failed)
                result = self.stage("evaluate", TB_BASELINE=baseline)
                self.assertEqual(result.returncode, 0, result.stderr)
                handoff = dict(line.split("=", 1) for line in self.output.read_text().splitlines())
                self.assertEqual(handoff["exit_code"], str(code))
                reports = Path(handoff["report_dir"])
                self.assert_large_generated_json(reports)
                uploaded = self.directory / f"upload-{code}"
                shutil.copytree(reports, uploaded)
                self.assertEqual((uploaded / "report.json").stat().st_size, (reports / "report.json").stat().st_size)
                gate = self.stage("gate", TB_REPORT_DIR=str(reports))
                self.assertEqual(gate.returncode, code, gate.stderr)

    def test_gate_independently_accepts_large_validated_json_from_installed_cli(self):
        # Generate reports directly so an evaluate-stage failure cannot hide the second reader's limit bug.
        for code, failed, baseline in [(0, False, ""), (1, True, ""), (3, True, "baseline.json")]:
            with self.subTest(code=code):
                self.recorded_outputs(failed=failed)
                reports = self.runtime / f"tracebench-direct-{code}"
                reports.mkdir()
                for format_name, filename in [("json", "report.json"), ("markdown", "report.md"), ("html", "report.html")]:
                    self.cli_report(format_name, reports / filename, code, baseline=baseline)
                self.assert_large_generated_json(reports)
                (reports / "provenance.json").write_text(json.dumps({"notice": "Synthetic installed-CLI size-boundary fixture"}))
                hashes = {name: hashlib.sha256((reports / name).read_bytes()).hexdigest()
                          for name in ("report.json", "report.md", "report.html", "provenance.json")}
                (reports / "gate.json").write_text(json.dumps({"exit_code": code, "expectation": "pass", "sha256": hashes}))
                gate = self.stage("gate", TB_REPORT_DIR=str(reports))
                self.assertEqual(gate.returncode, code, gate.stderr)

    def test_gate_rejects_generated_report_above_64_mib_before_hashing(self):
        result = self.stage("evaluate")
        self.assertEqual(result.returncode, 0, result.stderr)
        reports = Path(dict(line.split("=", 1) for line in self.output.read_text().splitlines())["report_dir"])
        with (reports / "report.json").open("wb") as stream:
            stream.truncate(64 * 1024 * 1024 + 1)
        gate = self.stage("gate", TB_REPORT_DIR=str(reports))
        self.assertEqual(gate.returncode, 2, gate.stderr)
        self.assertIn("gate artifacts must be bounded regular files", gate.stderr)

    def test_evaluate_rejects_actual_generated_report_above_64_mib_without_handoff(self):
        # Separate bounded inputs can legitimately expand past the generated-report cap.
        checks = [{"type": "contains", "expected": "<"}] * 100
        cases = [{"id": f"oversize-{i}", "input": "synthetic", "checks": checks} for i in range(2100)]
        outputs = [{"id": f"oversize-{i}", "output": "<" * 4500} for i in range(2100)]
        for name, rows in [("cases.jsonl", cases), ("outputs.jsonl", outputs)]:
            path = self.workspace / name
            path.write_text("".join(json.dumps(row) + "\n" for row in rows))
            self.assertLess(path.stat().st_size, 10 * 1024 * 1024)
        direct = self.directory / "direct-oversize.json"
        self.cli_report("json", direct, 0)
        self.assertGreater(direct.stat().st_size, 64 * 1024 * 1024)
        result = self.stage("evaluate")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("evaluation report missing or exceeds 64 MiB", result.stderr)
        self.assertEqual(self.output.read_text(), "")
        self.assertEqual(list(self.runtime.iterdir()), [])

    def test_installed_cli_baseline_input_retains_16_mib_limit(self):
        self.recorded_outputs()
        self.cli_report("json", self.workspace / "large-baseline.json", 0)
        self.assertGreater((self.workspace / "large-baseline.json").stat().st_size, 16 * 1024 * 1024)
        result = subprocess.run([str(self.python), "-m", "tracebench", "evaluate", "--cases", str(self.workspace / "cases.jsonl"),
                                 "--outputs", str(self.workspace / "outputs.jsonl"), "--baseline", str(self.workspace / "large-baseline.json")],
                                cwd=self.directory, env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("JSON document exceeds 16777216 bytes", result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
