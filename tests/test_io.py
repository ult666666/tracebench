import json
from pathlib import Path
import tempfile
import unittest

from tracebench.io import InputError, load_cases, load_outputs, load_pricing


class InputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "input.jsonl"

    def write(self, text):
        self.path.write_text(text, encoding="utf-8")
        return self.path

    def case(self, **changes):
        row = {"id": "问候", "input": "Say hello", "checks": [{"type": "exact", "expected": "你好"}]}
        return row | changes

    def test_cases_preserve_unicode_and_file_order(self):
        self.write(json.dumps(self.case(), ensure_ascii=False) + "\n" + json.dumps(self.case(id="second")))
        cases = load_cases(self.path)
        self.assertEqual(list(cases), ["问候", "second"])
        self.assertEqual(cases["问候"]["checks"][0]["expected"], "你好")

    def test_duplicate_case_ids_rejected(self):
        row = json.dumps(self.case())
        with self.assertRaisesRegex(InputError, "duplicate.*问候"):
            load_cases(self.write(row + "\n" + row))

    def test_unknown_case_fields_rejected(self):
        with self.assertRaisesRegex(InputError, "unknown"):
            load_cases(self.write(json.dumps(self.case(secret="no"))))

    def test_missing_case_fields_rejected(self):
        with self.assertRaisesRegex(InputError, "missing"):
            load_cases(self.write('{"id":"x","checks":[]}'))

    def test_empty_suite_and_blank_rows_rejected(self):
        for value in ["", "\n", json.dumps(self.case()) + "\n\n"]:
            with self.subTest(value=value), self.assertRaises(InputError):
                load_cases(self.write(value))

    def test_check_schema_rejects_unknown_types_and_bad_expected_values(self):
        checks = [[], [{"type": "magic", "expected": "x"}], [{"type": "exact", "expected": 2}],
                  [{"type": "contains", "expected": ""}], [{"type": "exact", "expected": "x", "extra": True}]]
        for value in checks:
            with self.subTest(checks=value), self.assertRaises(InputError):
                load_cases(self.write(json.dumps(self.case(checks=value))))

    def test_ids_are_nonempty_strings_without_surrogates_or_controls(self):
        for value in ["", " ", 1, "line\nbreak", "\ud800"]:
            with self.subTest(value=repr(value)), self.assertRaises(InputError):
                load_cases(self.write(json.dumps(self.case(id=value))))

    def test_duplicate_object_keys_rejected_even_when_nested(self):
        with self.assertRaisesRegex(InputError, "duplicate.*key"):
            load_outputs(self.write('{"id":"x","output":{"a":1,"a":2}}'))

    def test_nan_infinity_and_extreme_exponents_rejected(self):
        for value in ["NaN", "Infinity", "-Infinity", "1e9999999999999999999"]:
            with self.subTest(value=value), self.assertRaises(InputError):
                load_outputs(self.write('{"id":"x","output":' + value + '}'))

    def test_output_missing_unknown_fields_and_duplicates_rejected(self):
        for text in ['{"id":"x"}', '{"id":"x","output":"ok","foo":1}',
                     '{"id":"x","output":"ok"}\n{"id":"x","output":"again"}']:
            with self.subTest(text=text), self.assertRaises(InputError):
                load_outputs(self.write(text))

    def test_output_metrics_require_nonnegative_finite_numbers_and_paired_tokens(self):
        for metrics in [{"latency_ms": -1}, {"latency_ms": True}, {"input_tokens": 1},
                        {"input_tokens": 1.5, "output_tokens": 0}, {"input_tokens": False, "output_tokens": 0},
                        {"latency": 1}, {"input_tokens": -1, "output_tokens": 0}]:
            with self.subTest(metrics=metrics), self.assertRaises(InputError):
                load_outputs(self.write(json.dumps({"id": "x", "output": "ok", "metrics": metrics})))

    def test_outputs_accept_missing_metrics_and_zero_metrics(self):
        self.write('{"id":"x","output":"你好"}\n{"id":"y","output":null,"metrics":{"latency_ms":0,"input_tokens":0,"output_tokens":0}}')
        outputs = load_outputs(self.path)
        self.assertEqual(outputs["x"]["output"], "你好")
        self.assertEqual(outputs["y"]["metrics"]["latency_ms"], 0)

    def test_invalid_utf8_json_and_oversized_rows_rejected(self):
        for data in [b'\xff', b'{', b'[' + b' ' * 1_048_576 + b']']:
            self.path.write_bytes(data)
            with self.subTest(length=len(data)), self.assertRaises(InputError):
                load_cases(self.path)

    def test_unpaired_surrogates_anywhere_are_rejected(self):
        with self.assertRaises(InputError):
            load_outputs(self.write('{"id":"x","output":"\\udfff"}'))

    def test_pricing_uses_explicit_decimal_strings(self):
        self.write('{"currency":"USD","input_per_million":"0.10","output_per_million":"0.30"}')
        pricing = load_pricing(self.path)
        self.assertEqual(str(pricing["input_per_million"]), "0.10")

    def test_pricing_rejects_nonfinite_negative_numeric_or_unknown_rates(self):
        valid = {"currency": "USD", "input_per_million": "0.10", "output_per_million": "0.30"}
        for changes in [{"input_per_million": "NaN"}, {"output_per_million": "Infinity"},
                        {"input_per_million": "-1"}, {"input_per_million": 0.1},
                        {"currency": ""}, {"other": "1"}]:
            with self.subTest(changes=changes), self.assertRaises(InputError):
                load_pricing(self.write(json.dumps(valid | changes)))


if __name__ == "__main__":
    unittest.main()
