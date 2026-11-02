"""Paired statistics for baseline comparisons: exact McNemar tests, bootstrap intervals and gates.

Standard library only. Callers pass integer columns of per-case differences
(candidate minus baseline), already paired by case ID and sorted by ID, so file
order never changes a result. Gate decisions use exact integers and fractions.
Only the minimum detectable effect uses floating point, and it never decides a gate.
"""

from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
import math
import random
import re
from statistics import NormalDist

from .io import InputError

GATES = ("any-regression", "mcnemar", "noninferiority", "confident-regression")
INTERVAL_GATES = ("noninferiority", "confident-regression")
DEFAULT_GATE = "any-regression"
DEFAULT_ALPHA = "0.05"
DEFAULT_RESAMPLES = 2000
DEFAULT_SEED = 0
MAX_RESAMPLES = 1_000_000
MAX_SEED = 2 ** 64 - 1
POWER = Fraction(4, 5)
POWER_TEXT = "0.8"
_ROOT = Context(prec=60, rounding=ROUND_HALF_EVEN, Emin=-999999999, Emax=999999999)
_PROBABILITY = re.compile(r"([0-9]{1,20})(?:\.([0-9]{1,20}))?")
_INTEGER = re.compile(r"[0-9]{1,20}")
REASONS = {
    ("any-regression", True): "At least one case passed in the baseline and fails now.",
    ("any-regression", False): "No case passed in the baseline and fails now.",
    ("mcnemar", True): "The exact McNemar p-value is below alpha and regressions outnumber improvements.",
    ("mcnemar", False): "No net regression is significant at alpha under the exact McNemar test.",
    ("noninferiority", True): "The pass-rate interval's lower bound is below -margin, so non-inferiority is not shown.",
    ("noninferiority", False): "The pass-rate interval's lower bound is at or above -margin.",
    ("confident-regression", True): "The pass-rate interval's upper bound is below -margin, so the drop exceeds the margin.",
    ("confident-regression", False): "The pass-rate interval's upper bound is at or above -margin.",
}


def _lower_count(trials, last):
    """Sum of C(trials, i) for i = 0..last, using exact integer recurrences."""
    term = total = 1
    for i in range(last):
        term = term * (trials - i) // (i + 1)
        total += term
    return total


def binomial_tail(trials, successes):
    """Exact P(X >= successes) for X ~ Binomial(trials, 1/2), as a Fraction."""
    if successes <= 0:
        return Fraction(1)
    if successes > trials:
        return Fraction(0)
    # Sum whichever side has fewer terms; the distribution is symmetric.
    if trials - successes < successes:
        count = _lower_count(trials, trials - successes)
    else:
        count = (1 << trials) - _lower_count(trials, successes - 1)
    return Fraction(count, 1 << trials)


def mcnemar(regressions, improvements):
    """Exact McNemar test on discordant pairs; returns (two_sided, regression_direction).

    Under no change, each discordant pair is a regression with probability 1/2,
    so the regression count is Binomial(regressions + improvements, 1/2). The
    two-sided value doubles the smaller tail and caps at 1, which equals the
    "probabilities no larger than observed" rule for this symmetric distribution.
    The regression-direction value is P(X >= regressions).
    """
    discordant = regressions + improvements
    if discordant == 0:
        return Fraction(1), Fraction(1)
    upper = binomial_tail(discordant, regressions)
    lower = 1 - binomial_tail(discordant, regressions + 1)
    return min(Fraction(1), 2 * min(upper, lower)), upper


def min_discordant(alpha):
    """Fewest discordant pairs for which the two-sided exact test can reach p < alpha."""
    alpha = Fraction(alpha)
    pairs = 1
    while Fraction(2, 1 << pairs) >= alpha:
        pairs += 1
    return pairs


def critical_regressions(discordant, alpha):
    """Fewest regressions among `discordant` pairs that the McNemar gate rejects, or None.

    The gate fails when the two-sided p-value is below alpha and regressions
    outnumber improvements. The p-value falls as regressions rise above half of
    the discordant pairs, so a binary search over that half is exact.
    """
    alpha = Fraction(alpha)
    if discordant == 0 or 2 * binomial_tail(discordant, discordant) >= alpha:
        return None
    low, high = discordant // 2 + 1, discordant
    while low < high:
        middle = (low + high) // 2
        if 2 * binomial_tail(discordant, middle) < alpha:
            high = middle
        else:
            low = middle + 1
    return low


def resample_sums(columns, resamples, seed):
    """Paired bootstrap: for each resample, the sum of every column over the same case indices.

    All columns have the same length n. Each resample draws n case indices with
    replacement as floor(U * n), where U comes from random.Random(seed).random(),
    so the index stream depends only on n, the resample count and the seed.
    """
    size = len(columns[0])
    if size == 0 or any(len(column) != size for column in columns):
        raise InputError("bootstrap columns must be nonempty and equally long")
    draw = random.Random(seed).random
    getters = [column.__getitem__ for column in columns]
    sums = [[] for _ in columns]
    for _ in range(resamples):
        indices = [int(draw() * size) for _ in range(size)]
        for totals, get in zip(sums, getters):
            totals.append(sum(map(get, indices)))
    return sums


def interval_rank(resamples, alpha):
    """1-based rank k of the lower bound; the upper bound uses rank resamples + 1 - k."""
    return math.floor((resamples + 1) * Fraction(alpha) / 2)


def percentile_interval(sums, alpha):
    """Percentile interval from sorted resample sums: x[k] and x[B + 1 - k].

    Using the same rank from both ends makes the interval exactly mirror when
    every difference changes sign, so swapping baseline and candidate negates it.
    """
    ordered = sorted(sums)
    rank = interval_rank(len(ordered), alpha)
    if rank < 1:
        raise InputError("too few bootstrap resamples for this alpha")
    return ordered[rank - 1], ordered[len(ordered) - rank]


def detectable_effect(column, alpha):
    """Smallest true mean change found with 80% power, in the column's units, or None.

    Uses the normal approximation (z for 1 - alpha/2 plus z for the power) and
    the sample variance of the paired differences: MDE = z_sum * s / sqrt(n).
    Returns None with fewer than two pairs or no variance, because the formula
    would then claim that every change is detectable. The square root is taken
    in a fixed 60-digit decimal context, so tiny and huge values stay in range.
    """
    size = len(column)
    if size < 2:
        return None
    total = sum(column)
    variance = Fraction(size * sum(value * value for value in column) - total * total, size * (size - 1))
    if variance == 0:
        return None
    normal = NormalDist()
    multiplier = normal.inv_cdf(1 - float(Fraction(alpha)) / 2) + normal.inv_cdf(float(POWER))
    with localcontext(_ROOT):
        spread = (Decimal(variance.numerator) / Decimal(variance.denominator * size)).sqrt()
        return Decimal(multiplier) * spread


def gate_fails(gate, alpha, margin, regressions, improvements, two_sided_p, lower, upper):
    """Exact gate decision. lower/upper bound the pass-rate change as Fractions."""
    if gate == "any-regression":
        return regressions > 0
    if gate == "mcnemar":
        return two_sided_p < Fraction(alpha) and regressions > improvements
    if gate == "noninferiority":
        return lower < -Fraction(margin)
    if gate == "confident-regression":
        return upper < -Fraction(margin)
    raise InputError(f"gate must be one of {', '.join(GATES)}")


def _probability(value, name, *, low_open, high, high_open):
    if not isinstance(value, str) or _PROBABILITY.fullmatch(value) is None:
        raise InputError(f"{name} must be a decimal string such as 0.05")
    number = Fraction(value)
    if number < 0 or (low_open and number == 0) or number > high or (high_open and number == high):
        raise InputError(f"{name} is outside its allowed range")
    whole, fraction = _PROBABILITY.fullmatch(value).groups()
    fraction = (fraction or "").rstrip("0")
    return str(int(whole)) + ("." + fraction if fraction else "")


def _count(value, name, low, high):
    if isinstance(value, str):
        if _INTEGER.fullmatch(value) is None:
            raise InputError(f"{name} must be a nonnegative integer")
        value = int(value)
    if type(value) is not int or not low <= value <= high:
        raise InputError(f"{name} must be an integer from {low} to {high}")
    return value


def gate_options(gate=None, alpha=None, margin=None, resamples=None, seed=None):
    """Validate gate options from the CLI (strings) or the library; return normalized values.

    alpha is a two-sided level in (0, 0.5]. margin applies only to the interval
    gates and is a pass-rate fraction in [0, 1). The bootstrap needs enough
    resamples that (resamples + 1) * alpha / 2 is at least 1.
    """
    gate = DEFAULT_GATE if gate is None else gate
    if gate not in GATES:
        raise InputError(f"gate must be one of {', '.join(GATES)}")
    alpha = _probability(DEFAULT_ALPHA if alpha is None else alpha, "alpha", low_open=True, high=Fraction(1, 2), high_open=False)
    if margin is not None and gate not in INTERVAL_GATES:
        raise InputError("margin applies only to the noninferiority and confident-regression gates")
    if gate in INTERVAL_GATES:
        margin = _probability("0" if margin is None else margin, "margin", low_open=False, high=Fraction(1), high_open=True)
    resamples = _count(DEFAULT_RESAMPLES if resamples is None else resamples, "resamples", 1, MAX_RESAMPLES)
    if interval_rank(resamples, alpha) < 1:
        raise InputError("resamples too few for alpha: (resamples + 1) * alpha / 2 must be at least 1")
    seed = _count(DEFAULT_SEED if seed is None else seed, "seed", 0, MAX_SEED)
    return {"gate": gate, "alpha": alpha, "margin": margin, "resamples": resamples, "seed": seed}
