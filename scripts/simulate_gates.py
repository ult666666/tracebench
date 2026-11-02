"""Simulate how often each regression gate fails on synthetic paired pass/fail data.

No model is called and no recorded output is read. Each simulated suite has n
independent cases. A case regresses (baseline pass, candidate fail) with
probability r, improves with probability i, and is otherwise unchanged, so the
true pass-rate change is i - r. Gate decisions use the same tracebench.paired
functions as `tracebench evaluate --gate`, with the CLI's default bootstrap seed.

Two kinds of rate are printed for each scenario:

- exact: for any-regression and mcnemar, which depend only on the counts, the
  failure probability is a finite sum over binomial probabilities;
- simulated: every gate, including those two, over seeded replications. The
  exact column checks the simulation harness, and the interval gates
  (noninferiority, confident-regression) and a fixed-tolerance comparator that
  TraceBench does not offer have only simulated rates.

Run `python3 scripts/simulate_gates.py --help` for options. The defaults are the
scenarios published in docs/METHODOLOGY.md.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor
from fractions import Fraction
import math
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tracebench.paired import (critical_regressions, gate_fails, gate_options, mcnemar, percentile_interval,
                               resample_sums)

# (cases, discordance, true pass-rate change, replications)
SCENARIOS = [(n, "0.1", delta, reps) for n, reps in ((100, 2000), (400, 2000), (1600, 1000))
             for delta in ("0", "-0.02", "-0.05")] + [(6400, "0.1", "0", 300), (6400, "0.1", "-0.015", 300)]
TOLERANCE = Fraction(2, 100)
MARGIN = "0.02"
COLUMNS = ("any-regression", "tolerance", "mcnemar", "confident-regression", "noninferiority")


def rates(discordance, delta):
    """Regression and improvement probabilities for a discordance and true change."""
    discordance, delta = Fraction(discordance), Fraction(delta)
    regression, improvement = (discordance - delta) / 2, (discordance + delta) / 2
    if not (0 <= regression <= 1 and 0 <= improvement <= 1 and regression + improvement <= 1):
        raise ValueError("impossible discordance and change")
    return regression, improvement


def _binomial_pmf(trials, probability):
    """Binomial probabilities for 0..trials, computed in log space."""
    if probability in (0, 1):
        return [float(k == (trials if probability == 1 else 0)) for k in range(trials + 1)]
    log_p, log_q = math.log(float(probability)), math.log1p(-float(probability))
    return [math.exp(math.lgamma(trials + 1) - math.lgamma(k + 1) - math.lgamma(trials - k + 1) + k * log_p + (trials - k) * log_q)
            for k in range(trials + 1)]


def exact_failure_rates(cases, discordance, delta, alpha):
    """Exact failure probabilities of the count-only gates for one scenario."""
    regression, improvement = rates(discordance, delta)
    any_regression = 1 - (1 - float(regression)) ** cases
    discordant = regression + improvement
    if discordant == 0:
        return {"any-regression": any_regression, "mcnemar": 0.0}
    share = regression / discordant  # P(regression | discordant pair)
    total = 0.0
    for pairs, weight in enumerate(_binomial_pmf(cases, discordant)):
        if weight < 1e-300:  # negligible discordant counts; skip the exact critical value
            continue
        threshold = critical_regressions(pairs, alpha)
        if threshold is not None:
            total += weight * sum(_binomial_pmf(pairs, share)[threshold:])
    return {"any-regression": any_regression, "mcnemar": total}


def simulate(cases, discordance, delta, replications, *, alpha="0.05", resamples=2000, seed=0, data_seed=1):
    """Monte Carlo failure rates of every gate; the bootstrap uses the CLI's fixed seed."""
    regression, improvement = rates(discordance, delta)
    data = random.Random(data_seed)
    ci = gate_options("noninferiority", alpha, MARGIN, resamples, seed)
    failures = dict.fromkeys(COLUMNS, 0)
    for _ in range(replications):
        column = []
        for _ in range(cases):
            draw = data.random()
            column.append(-1 if draw < regression else 1 if draw < regression + improvement else 0)
        regressions, improvements = column.count(-1), column.count(1)
        two_sided, _ = mcnemar(regressions, improvements)
        low, high = percentile_interval(resample_sums([column], ci["resamples"], ci["seed"])[0], ci["alpha"])
        lower, upper = Fraction(low, cases), Fraction(high, cases)
        failures["tolerance"] += Fraction(improvements - regressions, cases) < -TOLERANCE
        for gate, margin in (("any-regression", None), ("mcnemar", None), ("confident-regression", "0"),
                             ("noninferiority", MARGIN)):
            failures[gate] += gate_fails(gate, ci["alpha"], margin, regressions, improvements, two_sided, lower, upper)
    return {gate: count / replications for gate, count in failures.items()}


def row(scenario, alpha="0.05", resamples=2000, data_seed=1):
    """One Markdown table row: exact rates first, simulated rates in parentheses."""
    cases, discordance, delta, replications = scenario
    exact = exact_failure_rates(cases, discordance, delta, alpha)
    simulated = simulate(cases, discordance, delta, replications, alpha=alpha, resamples=resamples, data_seed=data_seed)
    cells = [f"{exact['any-regression']:.3f} ({simulated['any-regression']:.3f})", f"{simulated['tolerance']:.3f}",
             f"{exact['mcnemar']:.4f} ({simulated['mcnemar']:.4f})", f"{simulated['confident-regression']:.4f}",
             f"{simulated['noninferiority']:.4f}"]
    return f"| {cases} | {delta} | {replications} | " + " | ".join(cells) + " |"


def table(scenarios, *, alpha="0.05", resamples=2000, data_seed=1, jobs=1):
    header = ["| Cases | True change | Runs | any-regression | tolerance 0.02 | mcnemar | confident-regression (margin 0) | noninferiority (margin 0.02) |",
              "| ---: | ---: | ---: | --- | ---: | --- | ---: | ---: |"]
    arguments = [(scenario, alpha, resamples, data_seed) for scenario in scenarios]
    if jobs == 1:
        rows = [row(*argument) for argument in arguments]
    else:
        with ProcessPoolExecutor(jobs) as pool:
            rows = list(pool.map(row, *zip(*arguments)))
    return "\n".join(header + rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cases", type=int, nargs="*", help="replace the default scenarios with these suite sizes")
    parser.add_argument("--changes", nargs="*", default=["0", "-0.02", "-0.05"], help="true pass-rate changes")
    parser.add_argument("--discordance", default="0.1", help="probability that a case changes status")
    parser.add_argument("--replications", type=int, default=1000)
    parser.add_argument("--resamples", type=int, default=2000)
    parser.add_argument("--alpha", default="0.05")
    parser.add_argument("--data-seed", type=int, default=1)
    parser.add_argument("--jobs", type=int, default=1, help="scenarios to run in parallel processes")
    args = parser.parse_args()
    scenarios = SCENARIOS if not args.cases else [(n, args.discordance, delta, args.replications)
                                                  for n in args.cases for delta in args.changes]
    print(f"Failure rates; discordance {args.discordance if args.cases else '0.1'}, alpha {args.alpha}, "
          f"{args.resamples} resamples. Exact values first, simulated in parentheses.\n")
    print(table(scenarios, alpha=args.alpha, resamples=args.resamples, data_seed=args.data_seed, jobs=args.jobs))


if __name__ == "__main__":
    main()
