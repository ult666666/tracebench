from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_wheel_and_sdist_build_from_standard_library_backend(self):
        import build_backend
        with tempfile.TemporaryDirectory() as directory:
            wheel_name = build_backend.build_wheel(directory)
            with zipfile.ZipFile(Path(directory) / wheel_name) as wheel:
                self.assertIsNone(wheel.testzip())
                self.assertIn("tracebench/cli.py", wheel.namelist())
                self.assertIn("tracebench/html_report.py", wheel.namelist())
                self.assertIn("tracebench = tracebench.cli:main", wheel.read("tracebench-0.3.0.dist-info/entry_points.txt").decode())
            archive = build_backend.build_sdist(directory)
            import tarfile
            with tarfile.open(Path(directory) / archive) as source:
                self.assertIn("tracebench-0.3.0/pyproject.toml", source.getnames())
                self.assertIn("tracebench-0.3.0/fixtures/cases.jsonl", source.getnames())
                self.assertIn("tracebench-0.3.0/tracebench/html_report.py", source.getnames())
                self.assertIn("tracebench-0.3.0/docs/sample-report.html", source.getnames())

    def test_built_wheel_runs_outside_checkout(self):
        import build_backend
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / build_backend.build_wheel(directory)
            script = "from tracebench.cli import main; raise SystemExit(main(['--version']))"
            result = subprocess.run([sys.executable, "-I", "-c", "import sys; sys.path.insert(0, sys.argv[1]); " + script, str(wheel)],
                                    cwd=directory, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "tracebench 0.3.0")


if __name__ == "__main__":
    unittest.main()
