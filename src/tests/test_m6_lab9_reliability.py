"""M6: combinatorial probabilities, aggregation and reliability floor."""
from itertools import combinations

import pytest

from lab9 import stats
from lab9.eval import aggregate, load_spec

pytestmark = pytest.mark.student


def test_probabilities_match_exhaustive_draws():
    for n in range(1, 9):
        for c in range(n + 1):
            trials = [True] * c + [False] * (n - c)
            for k in range(1, n + 1):
                draws = list(combinations(trials, k))
                at = stats.pass_at_k(n, c, k)
                hat = stats.pass_hat_k(n, c, k)
                assert at == pytest.approx(sum(map(any, draws)) / len(draws))
                assert hat == pytest.approx(sum(map(all, draws)) / len(draws))
                assert 0 <= hat <= c / n + 1e-15
                assert c / n <= at + 1e-15 <= 1 + 1e-15


@pytest.mark.parametrize("args", [
    (0, 0, 1), (-1, 0, 1), (5, -1, 1), (5, 6, 1),
    (5, 2, 0), (5, 2, -1), (3, 1, 4),
    (5.0, 2, 1), (5, 2.0, 1), (5, 2, 1.0),
    (True, 1, 1), (5, False, 1), (5, 2, True), (None, 2, 1),
])
def test_invalid_arguments(args):
    for fn in (stats.pass_at_k, stats.pass_hat_k):
        with pytest.raises(ValueError):
            fn(*args)


def test_large_counts_and_full_sample():
    assert stats.pass_at_k(10000, 5000, 5000) == 1.0
    assert stats.pass_hat_k(10000, 10000, 5000) == 1.0
    assert stats.pass_at_k(5, 1, 5) == 1.0
    assert stats.pass_hat_k(5, 4, 5) == 0.0


def test_aggregate_weights_items_and_handles_insufficient_trials():
    rows = [{"item_id": item, "pass_rate": passed, "cost": 1.0}
            for item, results in (("A", [True] * 5), ("B", [True, False, False]))
            for passed in results]
    metrics = aggregate(rows, ["pass_rate"], k_values=[1, 3, 5])
    assert metrics["pass_rate"] == 0.75
    assert metrics["pass_at_1"] == metrics["pass_hat_1"] == 0.6667
    assert metrics["pass_at_3"] == 1.0
    assert metrics["pass_hat_3"] == 0.5
    assert metrics["pass_at_5"] is metrics["pass_hat_5"] is None
    empty = aggregate([], ["pass_rate"], k_values=[1, 3, 5])
    assert all(v is None for v in empty.values())


def test_reliability_gate_boundary():
    from pathlib import Path
    from lab9.gate import check

    spec = load_spec(Path("config/metric_spec_v2.yaml"))
    metric = next(m for m in spec["metrics"] if m["id"] == "pass_hat_5")
    assert metric["blocking"] and metric["threshold"]["min"] >= 0.8
    isolated = {"metrics": [metric]}
    floor = metric["threshold"]["min"]
    base = {"manifest": {"eval_set_sha": "same"}, "metrics": {"pass_hat_5": 1.0}}
    for value, blocked in ((floor, []), (floor - 0.0001, ["pass_hat_5"]),
                           (None, ["pass_hat_5"])):
        pr = {**base, "metrics": {"pass_hat_5": value}}
        assert check(pr, base, isolated)[0] == blocked
