# Methodology and limitations

## Deterministic checks

`exact` compares strings literally. `contains` looks for a nonempty literal
substring. Case, punctuation, whitespace, and Unicode code points matter.
For example, `é` and `e` plus combining acute accent differ. Mandarin is handled
as Unicode text without tokenization or language-specific rules.

`json_subset` recursively requires each expected object key. Extra actual object
keys are allowed. Arrays require equal length and order, with recursive checks
at each position. Scalars require the same type and value, except that JSON
numbers compare numerically: `2` equals `2.0`. Booleans are distinct from numbers,
so `true` does not equal `1`. Null matches only null. A string containing JSON
does not count as structured JSON.

Every check must pass for a case to pass. `pass_rate = passed cases / all cases`,
rendered to six decimal places. Checks are not weighted. There is no semantic
correctness, factuality, safety, reasoning-quality, or language-quality judge.
An answer can satisfy a substring and still be wrong; choose cases accordingly.

## Recorded latency

The caller supplies optional `latency_ms` observations in **milliseconds**.
TraceBench summarizes them; it does not measure provider calls or time the
evaluation itself. Summaries include observed and missing counts. No observations
means null statistics, not zero latency. Supplied zero is an observed value.

For sorted observations `x[1] ... x[n]`, the p-th percentile is
`x[ceil(p*n)]`, with p = 0.50 or 0.95 (nearest rank). Mean is the arithmetic
sum divided by observed count, rounded half-even to six fractional milliseconds.
Min/max and percentiles retain supplied decimal precision.

For observations 10, 20, 100 ms: mean = 43.333333 ms, p50 = 20 ms, p95 = 100 ms.
With a fourth unobserved case, coverage is 3/4. Small sample percentiles are
descriptive, not a statistically reliable estimate of production tail latency.
There are no confidence intervals or repeated-run aggregates.

## Explicit token cost

The caller supplies both nonnegative integer `input_tokens` and `output_tokens`
per observed case and separate decimal price strings. For each priced case:

```text
cost = (input_tokens * input_per_million + output_tokens * output_per_million)
       / 1,000,000
```

For 12,345 input tokens and 6,789 output tokens at 0.10 and 0.30 USD per million,
cost is exactly **0.0032712 USD**. No binary float arithmetic or currency
rounding is used. The currency code labels the caller's unit; TraceBench does
not validate exchange rates, retrieve current rates, or infer provider/model.

Cost is null without prices or without token observations. Supplied zero tokens
with prices produces zero cost. The summary adds **known priced cases only**
and reports priced-case coverage and cases missing tokens. A partial sum is not
a complete bill. Discounts, caching tiers, reasoning-token conventions, batch
prices, taxes, retries, and non-token fees must be accounted for upstream.

## Baseline gate

Only compatible case suites compare. A regression is baseline pass → candidate
fail; an improvement is baseline fail → candidate pass. Existing failures do
not become regressions. A regression wins over a simultaneous improvement,
even when overall pass rate is unchanged. Changed IDs, prompts, expectations,
or descriptions require a fresh baseline. No automatic threshold test is
applied to costs or latency.

## Synthetic demo interpretation

All six fixtures, observations, and prices were created for this demonstration.
No model was called. The clean candidate has 6/6 passes, a 150 ms supplied mean,
and a 0.0000327 USD synthetic cost. These numbers prove the formulas and join
behavior for the fixture; they say nothing about any model's real performance.
The regression intentionally changes capitalization and replaces 北京 with 上海.

The tool is useful for mechanical acceptance criteria and reproducible review.
It cannot establish whether cases represent real users, whether recorded data
is trustworthy, or whether a change is safe to deploy. Human review and broader
evaluation remain outside its scope.
