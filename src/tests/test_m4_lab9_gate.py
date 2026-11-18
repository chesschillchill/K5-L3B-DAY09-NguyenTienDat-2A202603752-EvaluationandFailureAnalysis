"""M4: paired sampling and Core gate decisions."""
import numpy as np
import pytest
from scipy.stats import bootstrap

from lab9.gate import check
from lab9.stats import paired_bootstrap

pytestmark = pytest.mark.student


def test_paired_sampling_matches_scipy_and_is_repeatable():
    a, b = np.array([1, .8, .4, 0, .6]), np.array([.8, .4, .4, .2, 1])
    expected = bootstrap((a, b), lambda x, y, axis: np.mean(x - y, axis=axis),
                         paired=True, method="percentile", n_resamples=2000,
                         rng=np.random.default_rng(42), confidence_level=.8)
    actual = paired_bootstrap(a, b, n_resamples=2000, rng=42, confidence=.8)
    assert actual == pytest.approx((np.mean(a) - np.mean(b),
                                   expected.confidence_interval.low, expected.confidence_interval.high))
    assert actual == paired_bootstrap(a, b, n_resamples=2000, rng=42, confidence=.8)


def test_constant_paired_difference_has_zero_width():
    assert paired_bootstrap([1, 2, 3], [0, 1, 2]) == (1, 1, 1)


@pytest.mark.parametrize("a,b", [([], []), ([1], [1]), ([1, 2], [1]),
                                     ([[1, 2]], [[1, 2]]), ([1, np.nan], [1, 0]),
                                     ([1, 0], [1, np.inf])])
def test_invalid_paired_samples(a, b):
    with pytest.raises(ValueError):
        paired_bootstrap(a, b)


def _report(values):
    return {"manifest": {"eval_set_sha": "same"},
            "metrics": {"pass_rate": float(np.mean(values))},
            "rows": [{"item_id": f"E{i}", "seed": s, "pass_rate": v}
                     for i, v in enumerate(values) for s in [11, 22, 33, 44, 55]]}


def test_gate_ci_blocks_drop_above_floor_and_pairs_by_item():
    spec = {"metrics": [{"id": "pass_rate", "blocking": True,
                          "threshold": {"min": .85, "no_significant_drop": True}}]}
    base, pr = _report([1] * 14), _report([.9] * 14)
    pr["rows"].reverse()
    blocked, lines = check(pr, base, spec)
    assert blocked == ["pass_rate"]
    assert "CI [-0.100, -0.100]" in lines[0]
    assert check(base, base, spec)[0] == []
    assert check(base, pr, spec)[0] == []


def test_gate_floor_and_safety_block_independently():
    spec = {"metrics": [{"id": "pass_rate", "blocking": True, "threshold": {"min": .85}},
                         {"id": "approval_bypass", "blocking": True, "threshold": {"max": 0}}]}
    base, pr = _report([.8] * 14), _report([.8] * 14)
    pr["metrics"]["approval_bypass"] = 1
    assert check(pr, base, spec)[0] == ["pass_rate", "approval_bypass"]


def test_gate_accepts_drop_when_ci_includes_zero():
    spec = {"metrics": [{"id": "pass_rate", "blocking": True,
                          "threshold": {"min": .85, "no_significant_drop": True}}]}
    blocked, lines = check(_report([0] + [1] * 13), _report([1] * 14), spec)
    assert blocked == []
    assert "+0.000]" in lines[0]
