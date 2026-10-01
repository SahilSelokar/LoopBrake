import math
import random

from loopbrake.conformal import rank, threshold


def test_rank_is_exact():
    assert rank(19, 0.05) == 19
    assert rank(20, 0.05) == 20
    assert rank(18, 0.05) == 19
    assert rank(99, 0.01) == 99
    assert rank(20, 0.10) == 19


def test_too_few_runs_never_stops():
    for n in range(19):
        assert threshold(list(range(n)), 0.05) == math.inf


def test_19_or_20_runs_use_the_highest_score():
    for n in (19, 20):
        scores = random.Random(n).sample(range(1000), n)
        assert threshold(scores, 0.05) == max(scores)


def test_kth_smallest_with_unsorted_input_and_ties():
    # n = 10, alpha = 0.3 -> k = ceil(11 * 0.7) = 8 -> sorted [1,2,3,3,3,3,5,7,8,9][7] = 7
    assert threshold([5, 1, 3, 3, 9, 2, 3, 8, 7, 3], 0.3) == 7


def test_false_stop_rate_matches_theory():
    # A new successful run should go over the stop line with probability (n + 1 - k) / (n + 1) = 1/21.
    rng = random.Random(0)
    trials = 20_000
    over = 0
    for _ in range(trials):
        scores = [rng.random() for _ in range(21)]
        over += scores[20] > threshold(scores[:20], 0.05)
    assert abs(over / trials - 1 / 21) < 0.005
