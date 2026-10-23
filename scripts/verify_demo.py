"""Run the installed CLI outside the checkout and verify all four exit codes."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", type=Path, required=True, help="installed tracebench executable")
    args = parser.parse_args()
    executable = args.cli.resolve()
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        baseline = directory / "baseline.json"
        common = [str(executable), "evaluate", "--cases", str(ROOT / "fixtures/cases.jsonl"),
                  "--pricing", str(ROOT / "fixtures/pricing.json")]

        def run(name, extra, expected):
            command = common + ["--outputs", str(ROOT / "fixtures" / name)] + extra
            result = subprocess.run(command, cwd=directory, capture_output=True,
                                    text=True, encoding="utf-8", timeout=15)
            if result.returncode != expected:
                raise AssertionError(f"{name}: expected exit {expected}, got {result.returncode}: {result.stderr}")
            return result

        run("baseline.jsonl", ["--report", str(baseline)], 0)
        clean = json.loads(run("clean.jsonl", ["--baseline", str(baseline)], 0).stdout)
        assert clean["summary"]["passed"] == 6
        assert clean["summary"]["latency_ms"]["mean"] == "150"
        assert clean["summary"]["cost"]["total"] == "0.0000327"
        regression = json.loads(run("regression.jsonl", ["--baseline", str(baseline)], 3).stdout)
        assert regression["comparison"]["regressions"] == ["en-greeting", "zh-location"]
        run("regression.jsonl", [], 1)
        invalid = directory / "invalid.jsonl"
        invalid.write_text('{"id":"x","output":NaN}\n', encoding="utf-8")
        bad = subprocess.run(common + ["--outputs", str(invalid)], cwd=directory,
                             capture_output=True, text=True, timeout=15)
        assert bad.returncode == 2 and not bad.stdout and "Traceback" not in bad.stderr
    print("Installed CLI verified outside checkout: baseline=0 clean=0 regression=3 failure=1 invalid=2; clean=6/6, mean=150ms, cost=0.0000327 USD")


if __name__ == "__main__":
    main()
