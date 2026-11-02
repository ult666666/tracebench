"""Write the synthetic 100-case paired-gate demo in fixtures/paired/.

Everything here is invented: no model was called, and the latencies and token
counts are seeded pseudo-random numbers. The baseline passes 80 of 100 cases.
The noisy candidate swaps 5 passing and 5 failing cases (no net change), and the
regressed candidate breaks 12 passing cases and fixes 1 failing case. Run with
--check to verify the committed files instead of rewriting them.
"""

import argparse
import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "fixtures/paired"
CASES = 100


def _line(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"


def build():
    """Return {file name: text} for the four demo files."""
    rng = random.Random(20261101)
    ids = [f"synthetic-{index:03d}" for index in range(CASES)]
    baseline_pass = set(rng.sample(ids, 80))
    passing, failing = sorted(baseline_pass), sorted(set(ids) - baseline_pass)
    flips = {"noisy": (set(rng.sample(passing, 5)), set(rng.sample(failing, 5))),
             "regressed": (set(rng.sample(passing, 12)), set(rng.sample(failing, 1)))}
    observed = {}
    for case_id in ids:
        latency = rng.randrange(800, 4000) / 10
        observed[case_id] = (latency, rng.randrange(20, 200), rng.randrange(5, 80))
    files = {"cases.jsonl": "".join(_line({"id": case_id, "input": f"Synthetic question {case_id}",
                                           "checks": [{"type": "exact", "expected": f"answer {case_id}"}]})
                                    for case_id in ids)}

    def outputs(passes, changes):
        rows = []
        for case_id in ids:
            latency, tokens_in, tokens_out = observed[case_id]
            extra_latency, extra_tokens = changes.get(case_id, (0.0, 0))
            answer = f"answer {case_id}" if case_id in passes else f"answer {case_id}?"
            rows.append(_line({"id": case_id, "output": answer,
                               "metrics": {"latency_ms": round(max(0.0, latency + extra_latency), 1),
                                           "input_tokens": tokens_in, "output_tokens": tokens_out + extra_tokens}}))
        return "".join(rows)

    files["baseline.jsonl"] = outputs(baseline_pass, {})
    for name, (broken, fixed) in flips.items():
        # Candidates are about 6 ms slower and write up to 4 more tokens per case.
        noise = random.Random(name)
        changes = {case_id: (noise.gauss(6.0, 12.0), noise.randrange(0, 5)) for case_id in ids}
        files[name + ".jsonl"] = outputs((baseline_pass - broken) | fixed, changes)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if committed files differ from the generator")
    args = parser.parse_args()
    files = build()
    if args.check:
        stale = [name for name, text in files.items() if (DIRECTORY / name).read_text(encoding="utf-8") != text]
        if stale:
            raise SystemExit(f"fixtures/paired differs from the generator: {', '.join(stale)}")
        print("fixtures/paired matches scripts/make_paired_fixtures.py")
        return
    DIRECTORY.mkdir(exist_ok=True)
    for name, text in files.items():
        (DIRECTORY / name).write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {len(files)} files to {DIRECTORY.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
