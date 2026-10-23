# Input and report contracts

All inputs are UTF-8. JSON objects must not contain duplicate keys at any depth.
Unknown record fields are rejected. JSON values may not contain unpaired Unicode
surrogates, NaN, or infinity. UTF-8 byte-order marks are rejected by JSON parsing.

## Cases JSONL

| Field | Required | Type and rule |
| --- | --- | --- |
| `id` | Yes | Unique string, 1–200 characters, not all whitespace, no Unicode control/surrogate characters |
| `input` | Yes | Any valid JSON value; retained in the suite fingerprint, never executed |
| `checks` | Yes | Array of 1–100 check objects |
| `description` | No | String; included in fingerprint |

Every check has exactly `type` and `expected`. Type is `exact`, `contains`, or
`json_subset`. Exact/contains expectations must be strings, and contains must
be nonempty. JSON-subset expectations may be any valid JSON value.

## Outputs JSONL

| Field | Required | Type and rule |
| --- | --- | --- |
| `id` | Yes | Same ID rule as cases; exactly one record for every case |
| `output` | Yes | Any valid JSON value; subset checks use structured values directly |
| `metrics` | No | Object containing only the optional keys below |

`latency_ms` is a finite nonnegative JSON number in milliseconds. `input_tokens`
and `output_tokens` are nonnegative JSON **integers**, and must both be supplied
or both omitted. Booleans and decimal notation such as `1.0` are not integer
token counts. Empty metrics are allowed. Unknown fields and null metric values
are rejected. Absence represents missing observations.

Candidate file order does not matter. Missing or extra IDs are errors before
any scoring. IDs are case-sensitive and not Unicode-normalized.

## Pricing JSON document

Exactly `currency`, `input_per_million`, and `output_per_million` are required.
Currency is a three-letter uppercase code supplied by the caller. Both rates
are finite nonnegative decimal **strings**, never JSON numbers. Rates use
per-million-token units; rates and counts are not inferred.

## Resource and numeric limits

- JSONL: at most 100,000 rows; at most 1,048,576 bytes per row including newline.
- Empty files and blank rows are rejected; a single trailing newline is allowed.
- Nested JSONL records: at most 64 levels; baseline document wrappers permit
  128 levels while contained output records retain their original 64-level limit.
  JSON numbers: at most 100 digits, and absolute
  adjusted decimal exponent at most 100. Integers are limited to 100 digits.
- Pricing file: at most 1,048,576 bytes. Baseline JSON report: at most 16,777,216
  bytes. Large generated reports exceeding that baseline limit cannot be reused
  without reducing the suite/output size.
- Cost arithmetic uses 512 digits of precision. Latency means round to six
  decimal places; costs are not rounded to currency minor units.

The library validates the same data rules, but file byte/row limits apply only
to file readers. The complete dataset and reports are held in memory. These are
validation bounds, not tested throughput or memory-capacity guarantees.

Latency metrics in reports use fixed decimal strings. A valid input such as
`1e100` therefore becomes a string with 101 characters. Report validation removes
only coefficient trailing zeros from a temporary Decimal before reapplying the
original input bounds, using the fixed 512-digit context. This preserves accepted
boundaries without changing input limits, stored strings, summaries or exact
JSON/Markdown serialization, and does not use the caller's Decimal context.

## JSON report version 1

Top-level keys are exactly `schema_version`, `suite_sha256`, `results`,
`summary`, and `comparison`.

Each result contains `id`, Boolean `passed`, a nonempty `checks` array,
`output`, normalized `metrics`, and `cost`. Check entries contain `type`, Boolean
`passed`, and `reason`. Normalized metrics always contain `latency_ms`,
`input_tokens`, and `output_tokens`; missing observations are null. Latency and
cost are decimal strings, while tokens remain integers. Output values retain
JSON types and exact decimal numeric values.

Summary contains `cases`, `passed`, `failed`, `pass_rate`, `latency_ms`, and
`cost`. Latency fields are `observed`, `missing`, `min`, `max`, `mean`, `p50`,
and `p95`. Cost fields are `currency`, `total`, `priced_cases`, and
`missing_token_cases`. Rates are not copied into the report; preserve the pricing
file for a cost audit.

Comparison is null unless a baseline is supplied. Then it contains
`baseline_passed`, `current_passed`, sorted `regressions` and `improvements` ID
arrays, and an `unchanged` count. Report totals and statuses are validated for
internal consistency before a report is accepted as a baseline.

## Policy rules version 1 (separate document)

An object with integer `schema_version: 1` and at least one selected threshold:

```json
{
  "schema_version": 1,
  "min_pass_rate": "1",
  "max_p95_latency_ms": "210",
  "max_total_cost": {"currency": "USD", "amount": "0.0000327"}
}
```

Only these keys are accepted. `min_pass_rate` is a decimal string between 0 and 1;
`max_p95_latency_ms` is a nonnegative decimal string in milliseconds.
`max_total_cost` has exactly uppercase three-letter `currency` and nonnegative
`amount` decimal string. Currency is a caller-supplied unit label; no conversion
or price lookup occurs. JSON numbers, booleans, nulls, duplicate/unknown keys,
empty policies and unsupported schema versions are errors.

Threshold syntax is `[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?`, with at most 128
characters, 100 mantissa digits including leading/trailing zeros, explicit exponent
magnitude at most 100, and adjusted exponent magnitude at most 100. No whitespace,
leading sign, separators or nonfinite values are permitted. Scientific notation
allows exact `1e-100` and `1e100`. Normalization uses fixed notation when it fits
these limits, otherwise preserves a bounded scientific representation. Zero is
valid; `-0` is outside the syntax.

The CLI rules reader is limited to **65,536 bytes**, including whitespace. Its
separate evaluation-report reader permits **67,108,864 bytes** and uses unchanged
schema 1 report validation. This does not raise the evaluate baseline reader's
**16,777,216-byte** bound. File limits do not apply to direct API objects.

## Policy verdict version 1 (separate from report schema 1)

Fixed root keys: `schema_version` (integer 1), `suite_sha256`,
`evaluation_sha256`, `evaluation`, `accepted` (Boolean), `rules`, and `notice`.
`evaluation` contains integer `cases`, `passed`, `failed`, and `regressions`.
`evaluation_sha256` identifies `render_json(report).encode("utf-8")`, including
the final newline, rather than the original source file encoding.

`rules` is a nonempty list, ordered `min_pass_rate`, `max_p95_latency_ms`, then
`max_total_cost`, omitting unselected rules. Every entry contains exactly `rule`,
`threshold`, `actual`, `status`, and `reason`. Thresholds are normalized decimal
strings, except cost uses `{currency, amount}`. Actual pass rate is exact integer
`{passed, cases}`, actual p95 is a decimal string, and actual cost uses
`{currency, amount}`. Actual is null when unavailable. Status is one of `pass`,
`fail`, `unavailable`; every selected entry must be `pass` for acceptance.

Reasons are fixed text for satisfied/unsatisfied thresholds, incomplete supplied
latency coverage, incomplete token/pricing coverage, and mismatched currency.
The notice explicitly limits the verdict to supplied recorded observations and
preserves the independent evaluation status. No case selectors, executable
expressions, model calls, rate feeds or authorization decisions are supported.
