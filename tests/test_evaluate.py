from copy import deepcopy
from decimal import Decimal, localcontext
import unittest

from tracebench.io import InputError
from tracebench.evaluate import evaluate, compare_baseline, validate_report


def case(case_id="x", kind="exact", expected="你好"):
    return {"id": case_id, "input": "synthetic prompt", "checks": [{"type": kind, "expected": expected}]}


def output(case_id="x", value="你好", **metrics):
    row = {"id": case_id, "output": value}
    if metrics:
        row["metrics"] = metrics
    return row


def run_case(spec, actual):
    return evaluate({spec["id"]: spec}, {actual["id"]: actual})


class EvaluationTests(unittest.TestCase):
    def test_library_rejects_mixed_nonstring_object_keys_with_input_error(self):
        malformed = case()
        malformed[1] = "invalid key"
        malformed[None] = "another invalid key"
        with self.assertRaises(InputError):
            evaluate({"x": malformed}, {"x": output()})

    def test_report_comparison_ids_must_agree_with_current_statuses(self):
        cases = {"a": case("a"), "b": case("b")}
        report = evaluate(cases, {"a": output("a"), "b": output("b", "wrong")})
        report["comparison"] = {"baseline_passed": 1, "current_passed": 1,
                                "regressions": ["a"], "improvements": ["b"], "unchanged": 0}
        with self.assertRaises(InputError):
            validate_report(report)

    def test_exact_is_case_whitespace_and_unicode_sensitive(self):
        for expected, actual, passed in [("你好", "你好", True), ("Hello", "hello", False),
                                         ("你好", "你好 ", False), ("é", "e\u0301", False), ("1", 1, False)]:
            with self.subTest(expected=expected, actual=actual):
                self.assertIs(run_case(case(expected=expected), output(value=actual))["results"][0]["passed"], passed)

    def test_contains_checks_literal_multilingual_substring(self):
        report = run_case(case(kind="contains", expected="北京"), output(value="天气：北京晴天"))
        self.assertEqual(report["summary"]["passed"], 1)
        self.assertFalse(run_case(case(kind="contains", expected="北京"), output(value=["北京"]))["results"][0]["passed"])

    def test_json_subset_allows_extra_object_keys_and_recurses(self):
        spec = case(kind="json_subset", expected={"city": "北京", "data": {"n": 2}, "tags": ["a", "b"]})
        good = {"city": "北京", "data": {"n": Decimal("2.0"), "other": 3}, "tags": ["a", "b"], "extra": True}
        self.assertTrue(run_case(spec, output(value=good))["results"][0]["passed"])

    def test_json_subset_distinguishes_booleans_numbers_and_array_order_length(self):
        for expected, actual in [(True, 1), (1, True), ([1, 2], [2, 1]), ([1], [1, 2]), ({"a": 1}, {})]:
            with self.subTest(expected=expected, actual=actual):
                self.assertFalse(run_case(case(kind="json_subset", expected=expected), output(value=actual))["results"][0]["passed"])

    def test_multiple_checks_require_all_to_pass_and_explain_failures(self):
        spec = case(expected="你好")
        spec["checks"].append({"type": "contains", "expected": "北京"})
        result = run_case(spec, output())["results"][0]
        self.assertFalse(result["passed"])
        self.assertEqual([c["passed"] for c in result["checks"]], [True, False])
        self.assertIn("substring", result["checks"][1]["reason"])

    def test_output_id_join_does_not_depend_on_output_order(self):
        cases = {"a": case("a", expected="A"), "b": case("b", expected="B")}
        outputs = {"b": output("b", "B"), "a": output("a", "A")}
        report = evaluate(cases, outputs)
        self.assertEqual([r["id"] for r in report["results"]], ["a", "b"])
        self.assertEqual(report["summary"]["passed"], 2)

    def test_missing_and_extra_outputs_are_explicit_input_errors(self):
        with self.assertRaisesRegex(InputError, "missing.*x.*extra.*y"):
            evaluate({"x": case()}, {"y": output("y")})

    def test_api_validation_rejects_empty_mismatched_and_nonfinite_values(self):
        for cases, outputs in [({}, {}), ({"wrong": case()}, {"x": output()}),
                               ({"x": case()}, {"x": output(latency_ms=float("nan"))})]:
            with self.subTest(cases=cases), self.assertRaises(InputError):
                evaluate(cases, outputs)

    def test_latency_uses_observations_with_mean_and_nearest_rank_percentiles(self):
        cases = {str(i): case(str(i)) for i in range(1, 5)}
        outputs = {str(i): output(str(i), latency_ms=value) for i, value in [(1, 10), (2, 20), (3, 100)]}
        outputs["4"] = output("4")
        latency = evaluate(cases, outputs)["summary"]["latency_ms"]
        self.assertEqual(latency, {"observed": 3, "missing": 1, "min": "10", "max": "100", "mean": "43.333333", "p50": "20", "p95": "100"})

    def test_missing_measurements_are_null_never_fabricated_zero(self):
        summary = run_case(case(), output())["summary"]
        self.assertEqual(summary["latency_ms"]["observed"], 0)
        self.assertIsNone(summary["latency_ms"]["mean"])
        self.assertIsNone(summary["cost"]["total"])

    def test_decimal_cost_is_exact_and_independent_of_ambient_context(self):
        pricing = {"currency": "USD", "input_per_million": Decimal("0.10"), "output_per_million": Decimal("0.30")}
        with localcontext() as ctx:
            ctx.prec = 2
            report = evaluate({"x": case()}, {"x": output(input_tokens=12345, output_tokens=6789)}, pricing=pricing)
        self.assertEqual(report["results"][0]["cost"], "0.0032712")
        self.assertEqual(report["summary"]["cost"], {"currency": "USD", "total": "0.0032712", "priced_cases": 1, "missing_token_cases": 0})

    def test_partial_cost_coverage_is_explicit(self):
        pricing = {"currency": "USD", "input_per_million": "1", "output_per_million": "2"}
        cases = {"a": case("a"), "b": case("b")}
        outputs = {"a": output("a", input_tokens=0, output_tokens=0), "b": output("b")}
        cost = evaluate(cases, outputs, pricing=pricing)["summary"]["cost"]
        self.assertEqual(cost, {"currency": "USD", "total": "0", "priced_cases": 1, "missing_token_cases": 1})

    def test_suite_fingerprint_ignores_case_order_but_detects_changed_checks(self):
        cases = {"a": case("a"), "b": case("b")}
        outputs = {"a": output("a"), "b": output("b")}
        first = evaluate(cases, outputs)
        second = evaluate(dict(reversed(list(cases.items()))), outputs)
        self.assertEqual(first["suite_sha256"], second["suite_sha256"])
        changed = deepcopy(cases)
        changed["a"]["checks"][0]["expected"] = "another"
        self.assertNotEqual(first["suite_sha256"], evaluate(changed, outputs)["suite_sha256"])

    def test_baseline_detects_regressions_and_improvements_by_id(self):
        cases = {"a": case("a"), "b": case("b")}
        baseline = evaluate(cases, {"a": output("a"), "b": output("b", "bad")})
        candidate = evaluate(cases, {"b": output("b"), "a": output("a", "bad")})
        comparison = compare_baseline(candidate, baseline)
        self.assertEqual(comparison, {"baseline_passed": 1, "current_passed": 1, "regressions": ["a"], "improvements": ["b"], "unchanged": 0})

    def test_baseline_rejects_missing_cases_and_changed_suite(self):
        current = run_case(case(), output())
        missing = run_case(case("other"), output("other"))
        with self.assertRaisesRegex(InputError, "missing.*x.*extra.*other"):
            compare_baseline(current, missing)
        changed = run_case(case(expected="other"), output())
        with self.assertRaisesRegex(InputError, "suite fingerprint"):
            compare_baseline(current, changed)

    def test_baseline_rejects_duplicate_ids_invalid_booleans_and_nonfinite_metrics(self):
        original = run_case(case(), output())
        mutations = []
        duplicate = deepcopy(original)
        duplicate["results"].append(deepcopy(duplicate["results"][0]))
        mutations.append(duplicate)
        numeric = deepcopy(original)
        numeric["results"][0]["passed"] = 1
        mutations.append(numeric)
        nonfinite = deepcopy(original)
        nonfinite["results"][0]["metrics"]["latency_ms"] = "NaN"
        mutations.append(nonfinite)
        inconsistent = deepcopy(original)
        inconsistent["summary"]["passed"] = 0
        mutations.append(inconsistent)
        for mutated in mutations:
            with self.subTest(mutated=mutated), self.assertRaises(InputError):
                compare_baseline(original, mutated)

    def test_valid_deep_output_can_be_compared_with_its_own_report(self):
        nested = None
        for _ in range(63):
            nested = [nested]
        report = run_case(case(kind="json_subset", expected=None), output(value=nested))
        self.assertEqual(compare_baseline(report, report)["unchanged"], 1)


if __name__ == "__main__":
    unittest.main()
