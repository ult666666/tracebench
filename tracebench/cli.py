"""CLI contract: 0 pass, 1 checks fail, 2 invalid input/I/O, 3 regression."""

import argparse
import os
from pathlib import Path
import sys
import tempfile

from . import __version__
from .evaluate import compare_baseline, evaluate
from .html_report import render_html
from .io import InputError, load_cases, load_json, load_outputs, load_pricing
from .report import render_json, render_markdown


def _write_report(path, text, inputs):
    destination = Path(path)
    for source in inputs:
        if source is None:
            continue
        source = Path(source)
        if destination.resolve() == source.resolve() or (destination.exists() and source.exists() and destination.samefile(source)):
            raise InputError("report destination must not overwrite an input file")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=destination.parent,
                                         prefix=".tracebench-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline deterministic evaluation of recorded AI outputs.")
    parser.add_argument("--version", action="version", version=f"tracebench {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    command = subparsers.add_parser("evaluate", help="validate, evaluate, and render a report")
    command.add_argument("--cases", required=True, type=Path, help="strict UTF-8 case JSONL")
    command.add_argument("--outputs", required=True, type=Path, help="recorded output JSONL joined by ID")
    command.add_argument("--pricing", type=Path, help="explicit decimal per-million-token prices in JSON")
    command.add_argument("--baseline", type=Path, help="prior JSON report for exactly the same case suite")
    command.add_argument("--format", choices=("json", "markdown", "html"), default="json", help="report format (default: json)")
    command.add_argument("--report", type=Path, help="atomically replace a report file; defaults to stdout")
    args = parser.parse_args(argv)
    try:
        report = evaluate(load_cases(args.cases), load_outputs(args.outputs),
                          pricing=load_pricing(args.pricing) if args.pricing else None)
        if args.baseline:
            report["comparison"] = compare_baseline(report, load_json(args.baseline))
        text = {"json": render_json, "markdown": render_markdown, "html": render_html}[args.format](report)
        if args.report:
            _write_report(args.report, text, [args.cases, args.outputs, args.pricing, args.baseline])
        else:
            sys.stdout.write(text)
        if report["comparison"] and report["comparison"]["regressions"]:
            return 3
        return 1 if report["summary"]["failed"] else 0
    except (InputError, OSError) as exc:
        print(f"tracebench: error: {exc}", file=sys.stderr)
        return 2
