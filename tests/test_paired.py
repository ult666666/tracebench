"""Paired statistics and gates: exact values, brute-force references, seeded properties, simulations."""

from copy import deepcopy
from decimal import Decimal, Inexact, Rounded, localcontext
from fractions import Fraction
from itertools import product
import math
from pathlib import Path
import random
from statistics import NormalDist, stdev
import subprocess
import sys
import unittest

from scripts import simulate_gates
from tracebench.evaluate import compare_baseline, evaluate, outcome, validate_report
from tracebench.io import InputError, load_cases, load_json, load_outputs, load_pricing
from tracebench.paired import (GATES, binomial_tail, critical_regressions, gate_fails, gate_options, mcnemar,
                               min_discordant, percentile_interval, resample_sums)

ROOT = Path(__file__).resolve().parents[1]
PRICING = {"currency": "USD", "input_per_million": "0.10", "output_per_million": "0.30"}


def reports(before, after, *, latency=None, tokens=None, pricing=PRICING, order=None):
    """Evaluate one synthetic suite twice. before/after are pass flags per case."""
    ids = [f"c{index:03d}" for index in range(len(before))]
    cases = {key: {"id": key, "input": "synthetic", "checks": [{"type": "exact", "expected": "ok"}]} for key in ids}

    def outputs(flags, side):
        rows = {}
        for index, (key, good) in enumerate(zip(ids, flags)):
            metrics = {}
            if latency is not None and latency[side][index] is not None:
                metrics["latency_ms"] = latency[side][index]
            if tokens is not None and tokens[side][index] is not None:
                metrics["input_tokens"], metrics["output_tokens"] = tokens[side][index]
            rows[key] = {"id": key, "output": "ok" if good else "bad", **({"metrics": metrics} if metrics else {})}
        return rows

    if order is not None:
        cases = {key: cases[key] for key in order}
    return evaluate(cases, outputs(before, 0), pricing=pricing), evaluate(cases, outputs(after, 1), pricing=pricing)


def random_suite(rng, size=None):
    size = size or rng.randint(1, 60)
    before = [rng.random() < 0.7 for _ in range(size)]
    after = [flag if rng.random() < 0.8 else not flag for flag in before]
    latency = [[None if rng.random() < 0.1 else Decimal(rng.randrange(0, 50000)) / 100 for _ in range(size)] for _ in range(2)]
    tokens = [[None if rng.random() < 0.1 else (rng.randrange(0, 500), rng.randrange(0, 200)) for _ in range(size)] for _ in range(2)]
    return before, after, latency, tokens


def random_options(rng):
    gate = rng.choice(GATES)
    alpha = rng.choice(["0.5", "0.2", "0.1", "0.05", "0.01"])
    margin = rng.choice(["0", "0.02", "0.1"]) if gate in ("noninferiority", "confident-regression") else None
    minimum = math.ceil(2 / Fraction(alpha)) - 1
    return {"gate": gate, "alpha": alpha, "margin": margin, "resamples": rng.randint(minimum, minimum + 300),
            "seed": rng.randrange(2 ** 64)}


def brute_force(trials, observed):
    """Upper tail and 'probabilities no larger than observed' two-sided p by enumeration."""
    counts = [0] * (trials + 1)
    for outcome_bits in product((0, 1), repeat=trials):
        counts[sum(outcome_bits)] += 1
    upper = Fraction(sum(counts[observed:]), 2 ** trials)
    two_sided = Fraction(sum(count for count in counts if count <= counts[observed]), 2 ** trials)
    return min(Fraction(1), two_sided), upper


class ExactBinomialTests(unittest.TestCase):
    def test_hand_derived_values(self):
        self.assertEqual(binomial_tail(6, 6), Fraction(1, 64))
        self.assertEqual((binomial_tail(6, 0), binomial_tail(6, 7)), (1, 0))
        self.assertEqual(binomial_tail(10, 9), Fraction(11, 1024))
        expected = {(0, 0): (1, 1), (0, 6): (Fraction(1, 32), 1), (6, 0): (Fraction(1, 32), Fraction(1, 64)),
                    (1, 5): (Fraction(7, 32), Fraction(63, 64)), (3, 3): (1, Fraction(21, 32)),
                    (1, 7): (Fraction(9, 128), Fraction(255, 256)), (7, 1): (Fraction(9, 128), Fraction(9, 256))}
        for (regressions, improvements), values in expected.items():
            with self.subTest(regressions=regressions, improvements=improvements):
                self.assertEqual(mcnemar(regressions, improvements), values)
        self.assertEqual([min_discordant(a) for a in ("0.5", "0.05", "0.01", "0.001")], [3, 6, 8, 11])
        self.assertEqual([critical_regressions(m, "0.05") for m in (0, 5, 6, 10, 13)], [None, None, 6, 9, 11])

    def test_matches_brute_force_enumeration_of_every_outcome(self):
        for trials in range(1, 13):
            for regressions in range(trials + 1):
                with self.subTest(trials=trials, regressions=regressions):
                    self.assertEqual(mcnemar(regressions, trials - regressions), brute_force(trials, regressions))

    def test_large_counts_agree_with_math_comb_and_reference_values(self):
        rng = random.Random(7)
        for _ in range(40):
            trials = rng.randint(500, 3000)
            k = rng.randint(0, trials)
            self.assertEqual(binomial_tail(trials, k) - binomial_tail(trials, k + 1), Fraction(math.comb(trials, k), 2 ** trials))
            self.assertEqual(binomial_tail(trials, k) + binomial_tail(trials, trials - k + 1), 1)
        # Independently computed with scipy.stats.binomtest (SciPy 1.16.3) during development;
        # SciPy is not a dependency. (150, 86) is Agresti's presidential-approval table.
        for (regressions, improvements), (two_sided, regression_side) in {
                (150, 86): (3.71593613957e-05, 1.85796806979e-05), (500, 430): (0.0236088392925, 0.0118044196463),
                (37, 2): (2.84126144834e-09, 1.42063072417e-09), (1000, 1000): (1.0, 0.508919505573)}.items():
            values = mcnemar(regressions, improvements)
            self.assertAlmostEqual(float(values[0]) / two_sided, 1, places=10)
            self.assertAlmostEqual(float(values[1]) / regression_side, 1, places=10)

    def test_critical_regressions_match_a_linear_search(self):
        for alpha in ("0.5", "0.1", "0.05", "0.01", "0.001"):
            for discordant in range(0, 90):
                expected = next((b for b in range(discordant + 1)
                                 if b > discordant - b and mcnemar(b, discordant - b)[0] < Fraction(alpha)), None)
                with self.subTest(alpha=alpha, discordant=discordant):
                    self.assertEqual(critical_regressions(discordant, alpha), expected)
            self.assertEqual(critical_regressions(min_discordant(alpha), alpha), min_discordant(alpha))
            self.assertIsNone(critical_regressions(min_discordant(alpha) - 1, alpha))


class BootstrapTests(unittest.TestCase):
    def test_resampling_follows_the_documented_algorithm(self):
        column, other = [3, -1, 0, 7, 2, 2, -5], [1, 1, 0, 0, 1, 0, 1]
        draw = random.Random(42).random
        expected = [[], []]
        for _ in range(25):
            indices = [math.floor(draw() * len(column)) for _ in column]
            expected[0].append(sum(column[i] for i in indices))
            expected[1].append(sum(other[i] for i in indices))
        self.assertEqual(resample_sums([column, other], 25, 42), expected)

    def test_golden_interval_is_stable_across_python_versions(self):
        # CI runs this on Python 3.11 and 3.13; a change to the resampling stream fails here.
        sums = resample_sums([[-1, 0, 0, 1, 0, -1, 0, 0, 0, 1, -1, -1]], 2000, 0)[0]
        self.assertEqual(percentile_interval(sums, "0.05"), (-7, 3))
        self.assertEqual(sum(sums), -3804)

    def test_rank_rule_and_minimum_resamples(self):
        sums = list(range(2000, 0, -1))
        self.assertEqual(percentile_interval(sums, "0.05"), (50, 1951))
        self.assertEqual(percentile_interval(list(range(39)), "0.05"), (0, 38))
        with self.assertRaises(InputError):
            percentile_interval(list(range(38)), "0.05")
        for resamples, valid in [(38, False), (39, True)]:
            with self.subTest(resamples=resamples):
                if valid:
                    gate_options(resamples=resamples)
                else:
                    with self.assertRaises(InputError):
                        gate_options(resamples=resamples)

    def test_negated_differences_mirror_the_interval_exactly(self):
        rng = random.Random(3)
        for _ in range(50):
            column = [rng.randint(-9, 9) for _ in range(rng.randint(1, 30))]
            resamples, seed, alpha = rng.randint(39, 400), rng.randrange(1000), rng.choice(["0.05", "0.1", "0.5"])
            low, high = percentile_interval(resample_sums([column], resamples, seed)[0], alpha)
            self.assertEqual(percentile_interval(resample_sums([[-v for v in column]], resamples, seed)[0], alpha), (-high, -low))

    def test_minimum_detectable_effect_matches_an_independent_float_formula(self):
        rng = random.Random(11)
        before, after, latency, tokens = random_suite(rng, size=40)
        baseline, current = reports(before, after, latency=latency, tokens=tokens)
        statistics = compare_baseline(current, baseline)["statistics"]
        z = NormalDist().inv_cdf(0.975) + NormalDist().inv_cdf(0.8)
        differences = [int(b) - int(a) for a, b in zip(before, after)]
        expected = z * stdev(differences) / math.sqrt(len(differences))
        self.assertAlmostEqual(float(statistics["pass_rate"]["mde"]) / expected, 1, places=5)
        paired = [(a, b) for a, b in zip(*latency) if a is not None and b is not None]
        expected = z * stdev([float(b - a) for a, b in paired]) / math.sqrt(len(paired))
        self.assertEqual(statistics["latency_ms"]["pairs"], len(paired))
        self.assertAlmostEqual(float(statistics["latency_ms"]["mde"]) / expected, 1, places=5)


class PropertyTests(unittest.TestCase):
    def test_identical_baseline_and_candidate_never_fail_any_gate(self):
        rng = random.Random(2026)
        for trial in range(150):
            before, _, latency, tokens = random_suite(rng)
            options = random_options(rng)
            baseline, current = reports(before, before, latency=[latency[0]] * 2, tokens=[tokens[0]] * 2)
            current["comparison"] = compare_baseline(current, baseline, **options)
            with self.subTest(trial=trial, options=options):
                statistics = current["comparison"]["statistics"]
                self.assertFalse(current["comparison"]["gate"]["failed"])
                self.assertIn(outcome(current), (0, 1) if options["gate"] == "any-regression" else (0,))
                self.assertEqual(statistics["pass_rate"]["mcnemar_p"], "1")
                for name in ("pass_rate", "check_pass_rate", "latency_ms", "cost"):
                    block = statistics[name]
                    if block is not None:
                        self.assertEqual({Fraction(block[key]) for key in ("delta", "ci_lower", "ci_upper")}, {0})
                validate_report(current)

    def test_swapping_baseline_and_candidate_mirrors_every_statistic(self):
        rng = random.Random(99)
        for trial in range(80):
            before, after, latency, tokens = random_suite(rng)
            options = random_options(rng)
            options.update(gate="any-regression", margin=None)
            first, second = reports(before, after, latency=latency, tokens=tokens)
            forward = compare_baseline(second, first, **options)
            backward = compare_baseline(first, second, **options)
            with self.subTest(trial=trial):
                self.assertEqual((forward["regressions"], forward["improvements"]), (backward["improvements"], backward["regressions"]))
                for name in ("pass_rate", "check_pass_rate", "latency_ms", "cost"):
                    one, two = forward["statistics"][name], backward["statistics"][name]
                    if one is None:
                        self.assertIsNone(two)
                        continue
                    self.assertEqual((one["baseline"], one["current"], one["mde"], one["pairs"]),
                                     (two["current"], two["baseline"], two["mde"], two["pairs"]))
                    self.assertEqual(Fraction(one["delta"]), -Fraction(two["delta"]))
                    self.assertEqual((Fraction(one["ci_lower"]), Fraction(one["ci_upper"])),
                                     (-Fraction(two["ci_upper"]), -Fraction(two["ci_lower"])))
                self.assertEqual(forward["statistics"]["pass_rate"]["mcnemar_p"], backward["statistics"]["pass_rate"]["mcnemar_p"])

    def test_case_and_output_order_never_change_statistics(self):
        rng = random.Random(5)
        for _ in range(30):
            before, after, latency, tokens = random_suite(rng)
            options = random_options(rng)
            order = [f"c{index:03d}" for index in range(len(before))]
            rng.shuffle(order)
            plain = compare_baseline(*reversed(reports(before, after, latency=latency, tokens=tokens)), **options)
            shuffled = compare_baseline(*reversed(reports(before, after, latency=latency, tokens=tokens, order=order)), **options)
            self.assertEqual(plain, shuffled)

    def test_constant_latency_shift_moves_the_interval_exactly(self):
        rng = random.Random(8)
        for _ in range(20):
            size = rng.randint(2, 40)
            base = [Decimal(rng.randrange(0, 100000)) / 10 for _ in range(size)]
            noisy = [value + Decimal(rng.randrange(-500, 500)) / 10 for value in base]
            noisy = [max(value, Decimal(0)) for value in noisy]
            shifted = [value + Decimal("7.25") for value in noisy]
            flags = [True] * size
            one = compare_baseline(*reversed(reports(flags, flags, latency=[base, noisy])))["statistics"]["latency_ms"]
            two = compare_baseline(*reversed(reports(flags, flags, latency=[base, shifted])))["statistics"]["latency_ms"]
            for key in ("delta", "ci_lower", "ci_upper"):
                self.assertEqual(Fraction(two[key]) - Fraction(one[key]), Fraction("7.25"))

    def test_more_regressions_never_help_the_candidate(self):
        rng = random.Random(13)
        for _ in range(300):
            regressions, improvements, alpha = rng.randint(0, 60), rng.randint(0, 60), rng.choice(["0.05", "0.01", "0.2"])
            now, worse = mcnemar(regressions, improvements), mcnemar(regressions + 1, improvements)
            self.assertLessEqual(worse[1], now[1])
            if gate_fails("mcnemar", alpha, None, regressions, improvements, now[0], 0, 0):
                self.assertTrue(gate_fails("mcnemar", alpha, None, regressions + 1, improvements, worse[0], 0, 0))

    def test_ambient_decimal_context_does_not_change_statistics(self):
        before, after, latency, tokens = random_suite(random.Random(4), size=30)
        expected = compare_baseline(*reversed(reports(before, after, latency=latency, tokens=tokens)))
        pair = reversed(reports(before, after, latency=latency, tokens=tokens))
        with localcontext() as context:
            context.prec = 2
            context.traps[Inexact] = context.traps[Rounded] = True
            before_context = (context.prec, dict(context.traps), dict(context.flags))
            self.assertEqual(compare_baseline(*pair), expected)
            self.assertEqual((context.prec, dict(context.traps), dict(context.flags)), before_context)


class ReportContractTests(unittest.TestCase):
    def fixture(self, gate=None, margin=None):
        cases, pricing = load_cases(ROOT / "fixtures/cases.jsonl"), load_pricing(ROOT / "fixtures/pricing.json")
        report = evaluate(cases, load_outputs(ROOT / "fixtures/regression.jsonl"), pricing=pricing)
        report["comparison"] = compare_baseline(report, load_json(ROOT / "fixtures/baseline-report.json"), gate=gate, margin=margin)
        return report

    def test_schema_1_baselines_are_still_read_and_schema_2_is_written(self):
        baseline = load_json(ROOT / "fixtures/baseline-report.json")
        self.assertEqual(baseline["schema_version"], 1)
        report = self.fixture()
        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(report["comparison"]["statistics"]["pass_rate"]["discordant"], 2)
        validate_report(report)
        old = deepcopy(report)
        old["schema_version"] = 1
        with self.assertRaisesRegex(InputError, "unknown fields"):
            validate_report(old)
        for key in ("statistics", "gate"):
            missing = deepcopy(report)
            del missing["comparison"][key]
            with self.assertRaisesRegex(InputError, "missing fields"):
                validate_report(missing)
        with self.assertRaisesRegex(InputError, "schema 2"):
            compare_baseline(baseline, baseline)

    def test_tampered_or_unnormalized_statistics_are_rejected(self):
        report = self.fixture(gate="noninferiority", margin="0.05")
        statistics = ("comparison", "statistics")
        mutations = [
            (statistics + ("pass_rate", "ci_lower"), "-0.500000"), (statistics + ("pass_rate", "mcnemar_p"), "0.25"),
            (statistics + ("pass_rate", "critical_regressions"), 2), (statistics + ("pass_rate", "mde"), "0"),
            (statistics + ("pass_rate", "delta"), "-0.333334"), (statistics + ("alpha",), "0.050"),
            (statistics + ("resamples",), True), (statistics + ("seed",), -1), (statistics + ("power",), "0.9"),
            (statistics + ("check_pass_rate", "current"), "0.500000"), (statistics + ("check_pass_rate", "ci_upper"), "1.500000"),
            (statistics + ("latency_ms", "pairs"), 1),
            (statistics + ("latency_ms", "ci_lower"), "1000"), (statistics + ("cost", "currency"), "EUR"),
            (statistics + ("cost", "delta"), "+0"), (("comparison", "gate", "failed"), False),
            (("comparison", "gate", "reason"), "Trust me."), (("comparison", "gate", "margin"), "0.050"),
            (("comparison", "gate", "policy"), "mcnemar"), (statistics + ("extra",), 1)]
        validate_report(report)
        for path, value in mutations:
            changed = deepcopy(report)
            target = changed
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path, value=value), self.assertRaises(InputError):
                validate_report(changed)

    def test_gate_options_are_strict_and_normalized(self):
        self.assertEqual(gate_options(), {"gate": "any-regression", "alpha": "0.05", "margin": None, "resamples": 2000, "seed": 0})
        self.assertEqual(gate_options("noninferiority", "0.050", "00.10", "999", "7"),
                         {"gate": "noninferiority", "alpha": "0.05", "margin": "0.1", "resamples": 999, "seed": 7})
        self.assertEqual(gate_options("confident-regression")["margin"], "0")
        invalid = [{"gate": "bogus"}, {"alpha": "0"}, {"alpha": "0.6"}, {"alpha": "-0.1"}, {"alpha": "1e-2"},
                   {"alpha": " 0.05"}, {"alpha": 0.05}, {"gate": "mcnemar", "margin": "0.1"}, {"margin": "0.1"},
                   {"gate": "noninferiority", "margin": "1"}, {"resamples": "0"}, {"resamples": "1e3"},
                   {"resamples": True}, {"resamples": 10 ** 7}, {"seed": "-1"}, {"seed": "x"}, {"seed": 2 ** 64}]
        for options in invalid:
            with self.subTest(options=options), self.assertRaises(InputError):
                gate_options(**options)

    def test_fixture_gate_outcomes(self):
        expected = {("any-regression", None): (True, 3), ("mcnemar", None): (False, 0),
                    ("noninferiority", "0.05"): (True, 3), ("confident-regression", "0"): (False, 0)}
        for (gate, margin), (failed, code) in expected.items():
            with self.subTest(gate=gate):
                report = self.fixture(gate, margin)
                self.assertEqual((report["comparison"]["gate"]["failed"], outcome(report)), (failed, code))


class CliGateTests(unittest.TestCase):
    def cli(self, outputs, *extra):
        return subprocess.run([sys.executable, "-m", "tracebench", "evaluate", "--cases", ROOT / "fixtures/cases.jsonl",
                               "--outputs", ROOT / "fixtures" / outputs, "--pricing", ROOT / "fixtures/pricing.json", *extra],
                              cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30)

    def test_exit_codes_follow_the_selected_gate(self):
        baseline = ["--baseline", ROOT / "fixtures/baseline-report.json"]
        for outputs, extra, code in [("regression.jsonl", [], 3), ("regression.jsonl", ["--gate", "mcnemar"], 0),
                                     ("regression.jsonl", ["--gate", "noninferiority", "--margin", "0.05"], 3),
                                     ("regression.jsonl", ["--gate", "confident-regression"], 0),
                                     ("clean.jsonl", ["--gate", "noninferiority", "--margin", "0"], 0)]:
            with self.subTest(outputs=outputs, extra=extra):
                result = self.cli(outputs, *baseline, *extra)
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertEqual(result.stderr, "")
        for extra in [["--gate", "mcnemar"], ["--seed", "1"], [*baseline, "--alpha", "0.6"],
                      [*baseline, "--gate", "mcnemar", "--margin", "0.1"], [*baseline, "--resamples", "10"]]:
            with self.subTest(extra=extra):
                result = self.cli("clean.jsonl", *extra)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertNotIn("Traceback", result.stderr)

    def test_markdown_states_the_gate_and_statistics(self):
        result = self.cli("regression.jsonl", "--baseline", ROOT / "fixtures/baseline-report.json", "--gate", "mcnemar",
                          "--format", "markdown")
        self.assertEqual(result.returncode, 0, result.stderr)
        for text in ["Gate mcnemar: passed.", "| Pass rate | 6 | 1.000000 | 0.666667 | -0.333333 | -0.666667 to 0.000000 |",
                     "p = 0.5 two-sided, 0.25 in the regression direction", "needs at least 6 discordant pairs"]:
            self.assertIn(text, result.stdout)


class SimulationTests(unittest.TestCase):
    def test_exact_mcnemar_false_failure_rate_stays_below_half_alpha(self):
        for cases, discordance in product((20, 50, 100, 400, 1600), ("0.02", "0.1", "0.3")):
            with self.subTest(cases=cases, discordance=discordance):
                rates = simulate_gates.exact_failure_rates(cases, discordance, "0", "0.05")
                self.assertLess(rates["mcnemar"], 0.025)
        legacy = simulate_gates.exact_failure_rates(100, "0.1", "0", "0.05")["any-regression"]
        self.assertAlmostEqual(legacy, 1 - 0.95 ** 100)

    def test_reported_detectable_change_has_about_80_percent_exact_power(self):
        # The exact test is conservative, so its power at the normal-approximation MDE is a little under 0.8.
        for cases, discordant in [(400, 40), (1600, 160), (1600, 480)]:
            with self.subTest(cases=cases, discordant=discordant):
                before = [index % 2 == 0 for index in range(cases)]
                after = [not flag if index < discordant else flag for index, flag in enumerate(before)]
                baseline, current = reports(before, after)
                mde = compare_baseline(current, baseline)["statistics"]["pass_rate"]["mde"]
                power = simulate_gates.exact_failure_rates(cases, str(Fraction(discordant, cases)), "-" + mde, "0.05")["mcnemar"]
                self.assertTrue(0.74 < power < 0.82, power)

    def test_simulated_rates_agree_with_exact_rates_and_interval_gates_hold_their_level(self):
        # 800 runs: Monte Carlo standard error about 0.006 near 0.025.
        null = simulate_gates.simulate(200, "0.1", "0", 800, resamples=399)
        exact = simulate_gates.exact_failure_rates(200, "0.1", "0", "0.05")
        for gate in ("any-regression", "mcnemar"):
            self.assertLess(abs(null[gate] - exact[gate]), 4 * math.sqrt(exact[gate] * (1 - exact[gate]) / 800) + 1e-9, gate)
        self.assertLess(null["confident-regression"], 0.025 + 3 * 0.0055)
        self.assertGreater(null["tolerance"], 0.05)
        at_margin = simulate_gates.simulate(400, "0.1", "-0.02", 400, resamples=399, data_seed=2)
        self.assertLess(1 - at_margin["noninferiority"], 0.025 + 3 * 0.0078)


if __name__ == "__main__":
    unittest.main()
