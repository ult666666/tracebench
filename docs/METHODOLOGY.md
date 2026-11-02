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
Single-report percentiles have no confidence intervals and there are no
repeated-run aggregates. A comparison with a baseline adds a paired bootstrap
interval for the change in mean latency (see the paired statistics section).

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
not become regressions. With the default `any-regression` gate, a regression
wins over a simultaneous improvement, even when overall pass rate is unchanged.
Changed IDs, prompts, expectations, or descriptions require a fresh baseline.
The default evaluation applies no cost or latency threshold; optional explicit
budgets use the separate policy command described below. Version 0.5.0 adds
statistical gates that weigh regressions against improvements; see the last
section.

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

## Explicit recorded-observation budgets (0.4.0)

The optional separate `policy` command applies only caller-selected rules to an
already validated evaluation. It never changes the evaluation report, check outcomes,
baseline comparison or the default evaluation exit codes.

For `min_pass_rate = a/b`, acceptance uses `passed*b >= cases*a` with exact
integers. For 1/3 passed, thresholds `0.3333331` and `0.3333334` respectively pass
and fail even though the report displays `0.333333`. Latency and cost use exact
integer ratios derived from decimal strings. Boundaries are inclusive. No float,
rounding, global Decimal-context mutation or currency conversion is involved.

A p95 budget requires supplied latency for every case; the existing nearest-rank
percentile is then compared exactly. A total-cost budget requires every case to
have supplied token counts and a known priced cost, in the exact selected
currency. Partial sums, absent data and currency mismatch are `unavailable`,
which rejects the policy. Supplied zero with complete coverage remains evaluable.
Coverage is required only for the selected metric rules.

All selected rules must pass. A permissive minimum pass rate or a latency-only
policy may accept a report with failed cases; the separate verdict keeps failure
and regression counts visible. Normal CI preserves evaluation 1/3 as failures,
then adds policy rejection when evaluation is 0. A budget acceptance establishes
only a deterministic relationship between supplied values and selected limits.
It does not establish measured provider performance, authenticated observations,
model safety, production quality, spending authority or representativeness.

## Paired statistics and statistical gates (0.5.0)

Recorded outputs from a nondeterministic system change between runs even when
nothing that matters changed. The default `any-regression` gate fails on a
single pass-to-fail case, so it fails almost every unchanged candidate on a
noisy suite: with 100 cases of which 10% change status at random, its exact
failure rate is 0.994 (table below). A fixed tolerance on the pass-rate drop has
the opposite problems: it flags noise on small suites and passes real drops that
are smaller than the tolerance on large ones. The statistical gates compare the
baseline and the candidate case by case and state which error rate they control.

### Pairing

Cases are joined by ID, as before, and then sorted by ID in code-point order, so
file order never changes a statistic. Each case gives one paired difference
(candidate minus baseline) per metric:

| Metric | Per-case value | Cases used |
| --- | --- | --- |
| `pass_rate` | 1 if the case passed, else 0 | all |
| `check_pass_rate` | passed checks / checks, a partial-credit score | all |
| `latency_ms` | supplied latency, reported as a mean | cases with latency in both reports |
| `cost` | known token cost, reported as a total | cases priced in both reports, same currency |

Latency and cost need at least two paired cases; otherwise they are `null`.
Decimals are scaled to integers by one shared power of ten, so every sum is exact.

### Exact McNemar test for pass/fail outcomes

Let b be the regressions, c the improvements and m = b + c the discordant pairs.
Cases that kept their status say nothing about the direction of a change. If the
pass rate did not change, each discordant pair is a regression with probability
1/2, so b follows Binomial(m, 1/2) given m ([McNemar 1947](https://doi.org/10.1007/BF02295996)).
TraceBench computes the tail P(X >= b) as an exact fraction with integer
arithmetic. The two-sided p-value doubles the smaller tail and caps it at 1; for
this symmetric distribution that equals the "probabilities no larger than the
observed one" rule that SciPy's `binomtest` uses. Hand-checkable values: b = 6,
c = 0 gives 2/64 = 0.03125, and b = 1, c = 7 gives 18/256 = 0.0703125. The report
also gives the regression-direction p-value P(X >= b).

Tests compare these fractions with a brute-force enumeration of all 2^m outcomes
for m <= 12 and with `math.comb` for counts up to 3,000. During development they
were also cross-checked in a throwaway environment against SciPy 1.16.3
`binomtest` and statsmodels 0.15.0 `mcnemar(exact=True)`: over all 6,560 count
pairs with b, c <= 80, the largest relative difference was 8.5e-15, which is
floating-point rounding on SciPy's side. SciPy is not a dependency.

The exact conditional test is conservative: its real false-failure rate is
below the nominal level ([Fagerland, Lydersen and Laake 2013](https://doi.org/10.1186/1471-2288-13-91)).
For 100 cases with 10% discordance, the McNemar gate fails an unchanged
candidate with probability 0.0110, against a nominal one-sided 0.025.

### Paired bootstrap intervals for scores, latency and cost

For a metric with n pairs, TraceBench draws B resamples (`--resamples`, default
2,000) of n case indices with replacement. Each index is floor(U × n), with U from
`random.Random(seed).random()` (`--seed`, default 0). It sums the paired
differences over each resample and reports the percentile interval: the sorted
sums x[k] and x[B + 1 - k] with k = floor((B + 1) × alpha / 2), at least 1
([Efron 1979](https://doi.org/10.1214/aos/1176344552); Efron and Tibshirani,
*An Introduction to the Bootstrap*, 1993, chapter 13; the (B + 1) rank rule follows
Davison and Hinkley, *Bootstrap Methods and their Application*, 1997). Taking the
same rank from both ends makes the interval mirror exactly when every difference
changes sign, so swapping baseline and candidate negates it.

The index stream depends only on n, B and the seed. The same inputs therefore give
the same interval on any platform; CI checks a fixed interval on Python 3.11 and
3.13. Metrics over the same cases share one resampling pass. Rates and mean
latency are displayed rounded half-even to six decimals and cost totals exactly.
Gate decisions compare exact fractions, never the rounded display.

The work is O(B × n). On the 4-vCPU development machine, a 10,000-case comparison
took 6.0 s with 2,000 resamples and 2.7 s with 200 (timed with the evaluate CLI on
synthetic data). The existing 16 MiB baseline reader limit keeps practical suites
well under the 100,000-row input limit.

### Gates

`--alpha` (default 0.05) is a two-sided level. Each gate guards one direction, so
its nominal error rate is alpha/2. This matches the usual non-inferiority practice
of reading the lower bound of a two-sided 95% interval (U.S. FDA, *Non-Inferiority
Clinical Trials to Establish Effectiveness*, guidance for industry, 2016).
`--margin` is a pass-rate change, as a fraction of cases.

| `--gate` | Exit 3 when | Error rate it controls |
| --- | --- | --- |
| `any-regression` (default) | at least one case passed in the baseline and fails now | none; random noise fails it |
| `mcnemar` | two-sided exact p < alpha and regressions outnumber improvements | false failure when the pass rate did not change: at most alpha/2, exactly |
| `confident-regression` | the pass-rate interval's upper bound is below -margin | false failure when the true drop equals the margin: about alpha/2 |
| `noninferiority` | the pass-rate interval's lower bound is below -margin | false acceptance when the true drop equals the margin: about alpha/2 |

The gates differ in who carries the burden of proof. `mcnemar` and
`confident-regression` fail only on evidence of harm, so on a small suite they let
most changes through. `noninferiority` fails unless the evidence shows the
candidate is within the margin, so on a small suite it rejects most candidates,
including unchanged ones. An identical baseline and candidate never fail any gate:
every difference is zero, the interval is [0, 0] and the McNemar p-value is 1.

With a statistical gate, exit 0 means the gate passed even when some cases fail,
because the comparison with the baseline replaces the rule that every case must
pass. Add `tracebench policy` with `min_pass_rate` for an absolute floor.

### Minimum detectable effect

The report answers "could this suite have caught a change?" in three ways:

- `min_discordant`: the fewest discordant pairs for which the exact test can reach
  p < alpha at all. At alpha = 0.05 it is 6, because 2/2^6 = 0.03125 and
  2/2^5 = 0.0625.
- `critical_regressions`: for the observed m, the fewest regressions that make the
  McNemar gate fail, found by an exact binary search. With 13 discordant pairs at
  alpha = 0.05 it is 11.
- `mde`: the smallest true change in a metric's mean that a two-sided level-alpha
  test detects with 80% power, by the normal approximation
  MDE = (z(1 - alpha/2) + z(0.8)) × s / sqrt(n), where s is the sample standard
  deviation of the paired differences ([Bloom 1995](https://doi.org/10.1177/0193841X9501900504)).
  It is `null` with fewer than two pairs or no variance, since the formula would
  then claim that any change is detectable. Cost multiplies it by n, because cost
  is a total.

A test checks that the reported pass-rate `mde` means what it says. For suites of
400 cases (40 discordant), 1,600 (160) and 1,600 (480), the exact power of the
McNemar gate at a true drop equal to the reported `mde` is 0.774, 0.782 and 0.789:
slightly under 0.8, because the exact test is conservative. The test requires
0.74 to 0.82.

### Simulated error rates

`scripts/simulate_gates.py` draws synthetic suites in which each case regresses
with probability r, improves with probability i and otherwise keeps its status:
the discordance r + i is 0.1 and the true pass-rate change is i - r. Gate
decisions use the same functions as the CLI, with 2,000 resamples and the default
seed. For `any-regression` and `mcnemar` the exact failure probability is a finite
sum over binomial probabilities; simulated rates are in parentheses. The
"tolerance 0.02" column is a comparator that TraceBench does not offer: it fails
when the observed drop exceeds 2 points.

| Cases | True change | Runs | any-regression | tolerance 0.02 | mcnemar | confident-regression (margin 0) | noninferiority (margin 0.02) |
| ---: | ---: | ---: | --- | ---: | --- | ---: | ---: |
| 100 | 0 | 2000 | 0.994 (0.992) | 0.218 | 0.0110 (0.0100) | 0.0195 | 0.8575 |
| 100 | -0.02 | 2000 | 0.998 (0.998) | 0.448 | 0.0472 (0.0540) | 0.0885 | 0.9505 |
| 100 | -0.05 | 2000 | 1.000 (0.999) | 0.789 | 0.2408 (0.2315) | 0.3310 | 0.9925 |
| 400 | 0 | 2000 | 1.000 (1.000) | 0.089 | 0.0173 (0.0195) | 0.0230 | 0.7125 |
| 400 | -0.02 | 2000 | 1.000 (1.000) | 0.474 | 0.1975 (0.2110) | 0.2365 | 0.9630 |
| 400 | -0.05 | 2000 | 1.000 (1.000) | 0.965 | 0.8740 (0.8640) | 0.8840 | 0.9995 |
| 1600 | 0 | 1000 | 1.000 (1.000) | 0.005 | 0.0207 (0.0230) | 0.0240 | 0.2820 |
| 1600 | -0.02 | 1000 | 1.000 (1.000) | 0.493 | 0.6920 (0.7000) | 0.7060 | 0.9700 |
| 1600 | -0.05 | 1000 | 1.000 (1.000) | 1.000 | 1.0000 (1.0000) | 1.0000 | 1.0000 |
| 6400 | 0 | 300 | 1.000 (1.000) | 0.000 | 0.0228 (0.0167) | 0.0200 | 0.0033 |
| 6400 | -0.015 | 300 | 1.000 (1.000) | 0.117 | 0.9646 (0.9833) | 0.9833 | 0.7600 |

Produced by `python3 scripts/simulate_gates.py --jobs 3` (the default scenarios; it
ran for about an hour on the shared development machine). A simulated rate near
0.025 has a Monte Carlo standard error of about 0.0035 with 2,000 runs, 0.0049 with
1,000 and 0.009 with 300.

How to read it: at a true change of 0, every failure is a false alarm. At -0.02
(the non-inferiority margin), a `noninferiority` failure is the correct outcome and
1 minus the rate is its false-acceptance rate. At -0.05 and -0.015, failures are
detections (power).

What the table shows:

- `any-regression` failed 99.4% of unchanged 100-case suites and every unchanged
  suite of 400 cases or more. It reports noise, not regressions.
- The fixed 2-point tolerance raised false alarms on 21.8% of unchanged 100-case
  suites, yet on 6,400 cases it caught a real 1.5-point drop only 11.7% of the time.
- `mcnemar` kept its exact false-failure rate below 0.025 at every size (0.0110 at
  100 cases, rising to 0.0228 at 6,400 as the test becomes less discrete). Its power
  against a 5-point drop was 0.24 at 100 cases, 0.874 at 400 and 1.0 at 1,600, and
  it caught the 1.5-point drop at 6,400 cases 96.5% of the time.
- `confident-regression` with margin 0 had simulated false-failure rates from
  0.0195 to 0.0240, close to its nominal 0.025, with power similar to `mcnemar`.
- `noninferiority` with margin 0.02 wrongly accepted a candidate whose true drop
  equalled the margin in 1 - 0.9505 = 4.95% of runs at 100 cases, 3.70% at 400 and
  3.00% at 1,600. That is above the nominal 2.5% on small suites, because the
  percentile interval is too narrow when there are few discordant pairs. It also
  accepted an unchanged candidate in only 14.3% of runs at 100 cases and 71.8% at
  1,600: on small suites it rejects almost everything.

### Limits of the statistics

- Cases are assumed independent. Templated or near-duplicate cases make intervals
  too narrow and p-values too small. Cluster-aware errors, which
  [Miller 2024](https://arxiv.org/abs/2411.00640) recommends for evaluations with
  grouped questions, are not implemented.
- Each report is one recorded run. The statistics cannot separate a case's
  run-to-run sampling noise from differences between cases; repeated runs per case
  are not supported.
- With no discordant pairs the bootstrap interval is [0, 0] whatever the suite
  size, because the suite shows no variation. Read `min_discordant` and `mde` to
  judge whether the suite could have detected a change.
- The interval gates are approximate; `mcnemar` is exact and conservative. On a
  100-case suite, `noninferiority` accepted about 5% of candidates exactly at the
  margin instead of 2.5%. Prefer `mcnemar` for small suites.
- Running a gate on every push is repeated testing: across many pull requests some
  false failures are expected. There is no multiplicity or sequential correction.
- Gates use pass/fail only. Latency, cost and check-score statistics are reported,
  not gated; use `tracebench policy` for absolute budgets.
- 2,000 resamples put Monte Carlo noise of about 0.06 bootstrap standard errors on
  each interval endpoint (normal approximation: sqrt(0.025 × 0.975 / 2000) divided
  by the normal density at the 2.5% point). The decision is reproducible
  for a fixed seed, but raise `--resamples` when a bound sits close to the margin.
