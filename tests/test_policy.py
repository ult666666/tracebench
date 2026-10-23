"""Hand-derived recorded-observation budget boundaries; no provider calls."""

from copy import deepcopy
from decimal import Decimal, Inexact, Rounded, ROUND_DOWN, localcontext
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from tracebench.evaluate import evaluate
from tracebench.io import InputError
from tracebench.report import render_json


def recorded(*, passed=(True, True, True), metrics=None, pricing=None):
    cases = {str(i): {"id": str(i), "input": "synthetic", "checks": [{"type": "exact", "expected": "ok"}]}
             for i in range(len(passed))}
    outputs = {str(i): {"id": str(i), "output": "ok" if good else "bad"} for i, good in enumerate(passed)}
    if metrics is not None:
        for row, observation in zip(outputs.values(), metrics):
            row["metrics"] = observation
    return evaluate(cases, outputs, pricing=pricing)


class PolicyTests(unittest.TestCase):
    def setUp(self):
        try:
            self.policy = importlib.import_module("tracebench.policy")
        except ModuleNotFoundError:
            self.fail("recorded-observation policy module is not implemented")

    def verdict(self, report, **rules):
        return self.policy.evaluate_policy(report, {"schema_version": 1, **rules})

    def test_one_third_uses_counts_on_both_sides_of_rounded_display(self):
        report = recorded(passed=(True, False, False))
        self.assertEqual(report["summary"]["pass_rate"], "0.333333")
        for threshold, status in [("0.3333331", "pass"), ("0.3333334", "fail")]:
            with self.subTest(threshold=threshold):
                verdict = self.verdict(report, min_pass_rate=threshold)
                self.assertEqual(verdict["rules"][0]["actual"], {"passed": 1, "cases": 3})
                self.assertEqual(verdict["rules"][0]["status"], status)
                self.assertEqual(verdict["accepted"], status == "pass")
                self.assertEqual(verdict["evaluation"], {"cases": 3, "passed": 1, "failed": 2, "regressions": 0})

    def test_all_selected_rules_are_required_and_order_is_fixed(self):
        report = recorded(metrics=[{"latency_ms": 10, "input_tokens": 1, "output_tokens": 0}] * 3,
                          pricing={"currency": "USD", "input_per_million": "1", "output_per_million": "0"})
        verdict = self.verdict(report, max_total_cost={"currency": "USD", "amount": "0.000003"},
                               max_p95_latency_ms="10.00", min_pass_rate="1")
        self.assertTrue(verdict["accepted"])
        self.assertEqual([r["rule"] for r in verdict["rules"]],
                         ["min_pass_rate", "max_p95_latency_ms", "max_total_cost"])
        self.assertEqual(verdict["rules"][1]["threshold"], "10")
        self.assertEqual(verdict["rules"][2]["actual"], {"currency": "USD", "amount": "0.000003"})
        verdict = self.verdict(report, min_pass_rate="1", max_p95_latency_ms="9.999999999999999999999")
        self.assertEqual([r["status"] for r in verdict["rules"]], ["pass", "fail"])
        self.assertFalse(verdict["accepted"])

    def test_exact_tiny_and_large_cost_boundaries(self):
        for rate, amount, too_small in [("1e-93", "0." + "0" * 98 + "1", "9e-100"),
                                        ("1e100", "1" + "0" * 94, "9e93")]:
            report = recorded(passed=(True,), metrics=[{"input_tokens": 1, "output_tokens": 0}],
                              pricing={"currency": "USD", "input_per_million": rate, "output_per_million": "0"})
            self.assertEqual(report["summary"]["cost"]["total"], amount)
            self.assertTrue(self.verdict(report, max_total_cost={"currency": "USD", "amount": amount})["accepted"])
            self.assertFalse(self.verdict(report, max_total_cost={"currency": "USD", "amount": too_small})["accepted"])

    def test_exact_latency_tiny_large_and_nearest_rank(self):
        for latency, threshold in [(Decimal("1e-100"), "1e-100"), (Decimal("1e100"), "1e100")]:
            report = recorded(passed=(True,), metrics=[{"latency_ms": latency}])
            self.assertTrue(self.verdict(report, max_p95_latency_ms=threshold)["accepted"])
        report = recorded(passed=(True,) * 20, metrics=[{"latency_ms": i} for i in range(20)])
        self.assertTrue(self.verdict(report, max_p95_latency_ms="18")["accepted"])
        self.assertFalse(self.verdict(report, max_p95_latency_ms="17.999")["accepted"])

    def test_ambient_decimal_context_traps_flags_and_inputs_are_unchanged(self):
        report = recorded(passed=(True, False, False), metrics=[{"latency_ms": Decimal("0.1234567890123456789")}] * 3)
        rules = {"schema_version": 1, "min_pass_rate": "0.3333331", "max_p95_latency_ms": "0.1234567890123456789"}
        originals = deepcopy((report, rules))
        with localcontext() as context:
            context.prec = 2
            context.rounding = ROUND_DOWN
            context.traps[Inexact] = context.traps[Rounded] = True
            before = (context.prec, context.rounding, dict(context.traps), dict(context.flags))
            verdict = self.policy.evaluate_policy(report, rules)
            self.assertTrue(verdict["accepted"])
            self.assertEqual((context.prec, context.rounding, dict(context.traps), dict(context.flags)), before)
        self.assertEqual((report, rules), originals)

    def test_zero_observations_are_evaluable_but_absent_partial_and_wrong_currency_are_unavailable(self):
        zero = recorded(metrics=[{"latency_ms": 0, "input_tokens": 0, "output_tokens": 0}] * 3,
                        pricing={"currency": "USD", "input_per_million": "1", "output_per_million": "1"})
        verdict = self.verdict(zero, max_p95_latency_ms="0", max_total_cost={"currency": "USD", "amount": "0"})
        self.assertTrue(verdict["accepted"])
        self.assertEqual(verdict["rules"][0]["actual"], "0")
        self.assertEqual(verdict["rules"][1]["actual"], {"currency": "USD", "amount": "0"})
        partial = recorded(metrics=[{}, {"latency_ms": 0, "input_tokens": 0, "output_tokens": 0}, {}],
                           pricing={"currency": "USD", "input_per_million": "0", "output_per_million": "0"})
        no_prices = recorded(metrics=[{"input_tokens": 0, "output_tokens": 0}] * 3)
        for report in [recorded(), partial, no_prices]:
            verdict = self.verdict(report, max_p95_latency_ms="100", max_total_cost={"currency": "USD", "amount": "100"})
            self.assertFalse(verdict["accepted"])
            self.assertEqual([r["status"] for r in verdict["rules"]], ["unavailable", "unavailable"])
            self.assertEqual([r["actual"] for r in verdict["rules"]], [None, None])
            self.assertTrue(all(r["reason"] for r in verdict["rules"]))
        wrong = self.verdict(zero, max_total_cost={"currency": "EUR", "amount": "100"})
        self.assertEqual(wrong["rules"][0]["status"], "unavailable")
        self.assertIn("currency", wrong["rules"][0]["reason"])

    def test_verdict_fingerprints_and_markdown_retain_supplied_observation_limits(self):
        report = recorded(passed=(False,))
        verdict = self.verdict(report, min_pass_rate="0")
        self.assertTrue(verdict["accepted"])
        self.assertEqual(set(verdict), {"schema_version", "suite_sha256", "evaluation_sha256", "evaluation", "accepted", "rules", "notice"})
        self.assertEqual(verdict["suite_sha256"], report["suite_sha256"])
        self.assertEqual(verdict["evaluation_sha256"], hashlib.sha256(render_json(report).encode()).hexdigest())
        self.assertEqual(set(verdict["rules"][0]), {"rule", "threshold", "actual", "status", "reason"})
        markdown = self.policy.render_policy_markdown(verdict)
        self.assertIn("Failed cases: 1", markdown)
        self.assertIn("supplied", markdown)
        self.assertIn("does not", markdown)
        self.assertIn(report["suite_sha256"], markdown)

    def test_rules_reject_unknown_empty_version_invalid_decimal_and_currency(self):
        valid = {"schema_version": 1, "min_pass_rate": "0"}
        invalid = [{}, {"schema_version": 1}, {**valid, "unknown": "1"}, {**valid, "schema_version": True},
                   {**valid, "schema_version": 2}, {**valid, "min_pass_rate": "1.0000001"},
                   {"schema_version": 1, "max_total_cost": {"currency": "usd", "amount": "1"}},
                   {"schema_version": 1, "max_total_cost": {"currency": "USD", "amount": "1", "extra": 0}}]
        for value in [True, 1, 0.5, None, "NaN", "Infinity", "-0", "-1", "+1", " 1", "1_0", "1e101", "1e-101", "0e999999", "1" * 101, "0." + "0" * 129]:
            invalid.append({**valid, "min_pass_rate": value})
            invalid.append({"schema_version": 1, "max_p95_latency_ms": value})
            invalid.append({"schema_version": 1, "max_total_cost": {"currency": "USD", "amount": value}})
        for rules in invalid:
            with self.subTest(rules=rules), self.assertRaises(InputError):
                self.policy.evaluate_policy(recorded(), rules)

    def test_normalized_rules_remain_reusable_at_extreme_boundaries(self):
        for value in ["1e-100", "1e100"]:
            rules = {"schema_version": 1, "max_p95_latency_ms": value}
            normalized = self.policy.validate_rules(rules)
            self.assertEqual(self.policy.validate_rules(normalized), normalized)

    def test_report_validation_is_not_bypassed(self):
        report = recorded()
        for change in [{"summary": {**report["summary"], "passed": 0}}, {"schema_version": 2}, {"extra": "field"}]:
            with self.subTest(change=change), self.assertRaises(InputError):
                self.verdict({**report, **change}, min_pass_rate="0")

    def test_rule_reader_rejects_duplicate_keys_and_documents_above_64_kib(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rules.json"
            for text in ['{"schema_version":1,"min_pass_rate":"0","min_pass_rate":"1"}',
                         '{"schema_version":1,"max_total_cost":{"currency":"USD","amount":"0","amount":"1"}}',
                         json.dumps({"schema_version": 1, "min_pass_rate": "0"}) + " " * 65536]:
                path.write_text(text)
                with self.assertRaises(InputError):
                    self.policy.load_rules(path)


if __name__ == "__main__":
    unittest.main()
