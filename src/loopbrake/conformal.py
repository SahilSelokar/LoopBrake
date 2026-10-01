"""The stop-line rule (constitution Principle I).

Given the scores of n past successful runs, pick the stop line so that a new successful run
from the same agent and task mix goes over it with probability at most alpha.
"""
import math
from fractions import Fraction


def rank(n, alpha):
    """Which calibration score becomes the stop line: the k-th smallest, k = ceil((n + 1)(1 - alpha)).

    Exact fractions, so rounding can never change k.
    """
    return math.ceil((n + 1) * (1 - Fraction(str(alpha))))


def threshold(run_scores, alpha):
    """The stop line. math.inf when there are too few runs, so nothing is ever stopped."""
    k = rank(len(run_scores), alpha)
    return math.inf if k > len(run_scores) else sorted(run_scores)[k - 1]
