"""Bounded GitHub Actions handoff for the installed, offline TraceBench CLI.

Inputs are environment values, never shell fragments. The caller checkout and
TraceBench installation are trusted code; this is not a sandbox for that code.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

from tracebench import __version__
from tracebench.evaluate import validate_report
from tracebench.io import InputError, load_json


class RunnerError(ValueError):
    """Fixed runner-owned diagnostic, safe to display in Actions logs."""


INPUT_LIMIT = 10 * 1024 * 1024
REPORT_LIMIT = 64 * 1024 * 1024
REPORTS = ("report.json", "report.md", "report.html", "provenance.json")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_root(value):
    if not value or any(ord(c) < 32 for c in value):
        raise RunnerError("missing or invalid trusted runner directory")
    path = Path(value)
    if not path.is_absolute() or not path.is_dir() or path.is_symlink():
        raise RunnerError("runner directory must be an existing absolute directory")
    return path.resolve()


def roots():
    workspace = safe_root(os.environ.get("TB_WORKSPACE", ""))
    runtime = safe_root(os.environ.get("RUNNER_TEMP", ""))
    if runtime == workspace or runtime.is_relative_to(workspace) or workspace.is_relative_to(runtime):
        raise RunnerError("runner temporary directory and caller workspace must be separate")
    return workspace, runtime


def input_file(workspace, value):
    if (not value or len(value) > 1024 or "\\" in value or any(ord(c) < 32 for c in value)
            or Path(value).is_absolute()):
        raise RunnerError("input must be a bounded workspace-relative path")
    parts = value.split("/")
    if len(parts) > 20 or any(p in {"", ".", "..", "node_modules", "__pycache__", "venv"}
                              or p.startswith(".") for p in parts):
        raise RunnerError("input path contains a forbidden private/runtime or traversal component")
    path = workspace
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise RunnerError("input symlinks are forbidden")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > INPUT_LIMIT:
        raise RunnerError("input must be a regular file of at most 10 MiB")
    if not path.resolve().is_relative_to(workspace):
        raise RunnerError("input must stay inside the caller workspace")
    return path


def expectation():
    value = os.environ.get("TB_EXPECTATION", "pass")
    if value not in {"pass", "regression"}:
        raise RunnerError("expectation must be pass or regression")
    return value


def source_sha():
    value = os.environ.get("TB_SOURCE_SHA", "")
    if re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise RunnerError("TraceBench source must be pinned to a lowercase 40-hex commit SHA")
    return value


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def append_environment(name, text):
    value = os.environ.get(name)
    if not value:
        raise RunnerError(f"{name} is required for workflow handoff")
    with Path(value).open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def evaluate_stage():
    workspace, runtime = roots()
    expected, revision = expectation(), source_sha()
    inputs = {}
    for name in ("cases", "outputs", "baseline", "pricing"):
        value = os.environ.get("TB_" + name.upper(), "")
        if value or name in {"cases", "outputs"}:
            inputs[name] = input_file(workspace, value)
    provenance_inputs = {name: {"path": path.relative_to(workspace).as_posix(), "sha256": digest(path)}
                         for name, path in inputs.items()}
    # New exclusive directories; neither caller nor input selects an output path.
    directory = Path(tempfile.mkdtemp(prefix="tracebench-", dir=runtime))
    try:
        command = [sys.executable, "-m", "tracebench", "evaluate"]
        for name, path in inputs.items():
            command += ["--" + name, str(path)]
        codes = []
        for format_name, filename in [("json", "report.json"), ("markdown", "report.md"), ("html", "report.html")]:
            result = subprocess.run(command + ["--format", format_name, "--report", str(directory / filename)],
                                    cwd=runtime, capture_output=True, timeout=60)
            if result.returncode not in {0, 1, 3}:
                # Do not echo untrusted CLI diagnostics into GitHub workflow commands/logs.
                raise RunnerError("evaluation rejected input or failed (expected valid exit 0, 1 or 3)")
            if not (directory / filename).is_file() or (directory / filename).stat().st_size > REPORT_LIMIT:
                raise RunnerError("evaluation report missing or exceeds 64 MiB")
            codes.append(result.returncode)
        if len(set(codes)) != 1 or any(digest(inputs[name]) != meta["sha256"] for name, meta in provenance_inputs.items()):
            raise RunnerError("input or outcome changed during evaluation")
        code = codes[0]
        report = load_json(directory / "report.json", max_bytes=REPORT_LIMIT)
        provenance = {"tracebench_version": __version__, "source_sha": revision,
                      "suite_sha256": report["suite_sha256"], "inputs": provenance_inputs,
                      "evaluation_exit": code, "expected_outcome": expected,
                      "notice": "Recorded outputs only; provenance hashes do not establish truth or model quality."}
        write_json(directory / "provenance.json", provenance)
        write_json(directory / "gate.json", {"exit_code": code, "expectation": expected,
                                             "sha256": {name: digest(directory / name) for name in REPORTS}})
        regressions = len(report["comparison"]["regressions"]) if report["comparison"] else 0
        append_environment("GITHUB_STEP_SUMMARY", f"### TraceBench recorded evaluation\n\n"
                           f"Evaluation exit: **{code}** · passed: **{report['summary']['passed']}** · "
                           f"failed: **{report['summary']['failed']}** · regressions: **{regressions}**\n\n"
                           f"Gate expectation: `{expected}`. Reports are uploaded before applying the gate.\n\n"
                           f"TraceBench `{__version__}` · source `{revision}` · suite `{report['suite_sha256']}`\n\n"
                           "Recorded outputs only; no provider was called. Download the JSON, Markdown, HTML and provenance artifact.\n")
        append_environment("GITHUB_OUTPUT", f"report_dir={directory}\nexit_code={code}\n")
        print(f"Recorded evaluation completed with exit {code}; bounded reports ready for upload.")
        return 0
    except BaseException:
        shutil.rmtree(directory)
        raise


def gate_stage():
    _, runtime = roots()
    expected = expectation()
    raw = Path(os.environ.get("TB_REPORT_DIR", ""))
    if raw.is_symlink() or raw.parent != runtime or not re.fullmatch(r"tracebench-[A-Za-z0-9_-]+", raw.name):
        raise RunnerError("gate directory must be the generated directory in RUNNER_TEMP")
    if {p.name for p in raw.iterdir()} != set(REPORTS) | {"gate.json"}:
        raise RunnerError("gate directory contains unexpected or missing artifacts")
    for name in (*REPORTS, "gate.json"):
        path = raw / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > REPORT_LIMIT:
            raise RunnerError("gate artifacts must be bounded regular files")
    handoff = load_json(raw / "gate.json")
    if (not isinstance(handoff, dict) or set(handoff) != {"exit_code", "expectation", "sha256"}
            or type(handoff["exit_code"]) is not int or handoff["exit_code"] not in {0, 1, 3}
            or handoff["expectation"] != expected
            or handoff["sha256"] != {name: digest(raw / name) for name in REPORTS}):
        raise RunnerError("invalid or changed evaluation handoff")
    code = handoff["exit_code"]
    report = load_json(raw / "report.json", max_bytes=REPORT_LIMIT)
    validate_report(report)
    actual = 3 if report["comparison"] and report["comparison"]["regressions"] else (1 if report["summary"]["failed"] else 0)
    if code != actual:
        raise RunnerError("handoff outcome disagrees with the validated JSON report")
    if expected == "regression":
        if code != 3:
            raise RunnerError("regression verification expected exit 3")
        print("Verified the deliberately regressed fixture produced exit 3.")
        return 0
    print(f"Applying recorded-evaluation gate: exit {code}.")
    return code


def main():
    try:
        if sys.argv[1:] == ["evaluate"]:
            return evaluate_stage()
        if sys.argv[1:] == ["gate"]:
            return gate_stage()
        raise RunnerError("expected evaluate or gate stage")
    except RunnerError as exc:
        print(f"TraceBench CI: {exc}.", file=sys.stderr)
        return 2
    except (InputError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        # Own fixed diagnostics only: never relay caller paths or recorded text.
        print(f"TraceBench CI: invalid input or runner failure ({type(exc).__name__}).", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
