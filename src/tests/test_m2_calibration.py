"""M2 edge cases and calibration decisions, independent of M4 bootstrap."""
import csv
import math
from pathlib import Path

import pytest

from lab9 import judge, stats

pytestmark = pytest.mark.student


def test_fail_is_positive_and_zero_denominators_are_zero():
    assert stats.confusion(["FAIL", "PASS", "FAIL", "PASS"],
                           ["FAIL", "FAIL", "PASS", "PASS"]) == dict(tp=1, fp=1, fn=1, tn=1)
    assert stats.precision_recall(["PASS"], ["PASS"]) == (0.0, 0.0)
    assert stats.precision_recall(["FAIL"], ["PASS"]) == (0.0, 0.0)
    assert stats.precision_recall(["PASS"], ["FAIL"]) == (0.0, 0.0)


@pytest.mark.parametrize("human,predicted,want", [
    (["PASS", "FAIL"], ["PASS", "FAIL"], 1.0),
    (["PASS", "FAIL"], ["FAIL", "PASS"], -1.0),
    (["PASS", "FAIL"], ["PASS", "PASS"], 0.0),
])
def test_kappa_known_vectors(human, predicted, want):
    assert stats.cohen_kappa(human, predicted) == pytest.approx(want)


@pytest.mark.parametrize("labels", [[], ["PASS"] * 3, ["FAIL"] * 3])
def test_kappa_undefined(labels):
    with pytest.raises(ValueError):
        stats.cohen_kappa(labels, labels)


def test_confusion_rejects_misaligned_or_invalid_labels():
    with pytest.raises(ValueError):
        stats.confusion(["PASS"], [])
    with pytest.raises(ValueError):
        stats.confusion(["UNKNOWN"], ["PASS"])


def test_rogan_gladen_boundaries_and_unidentifiable_rate():
    assert stats.rogan_gladen(0.3, 1.0, 1.0) == pytest.approx(0.3)
    assert stats.rogan_gladen(0.0, 0.8, 0.9) == 0.0
    assert stats.rogan_gladen(1.0, 0.8, 0.9) == 1.0
    with pytest.raises(ValueError):
        stats.rogan_gladen(0.0, 0.0, 1.0)


@pytest.mark.parametrize("name,cm,p,r,k,passed,exit_code", [
    ("tone", dict(tp=24, fp=4, fn=6, tn=66), 0.857, 0.8, 0.757, True, 0),
    ("helpful", dict(tp=9, fp=0, fn=21, tn=70), 1.0, 0.3, 0.375, False, 1),
])
def test_public_calibration_and_cli(name, cm, p, r, k, passed, exit_code, capsys):
    path = Path(f"data/eval/judge_{name}_public.csv")
    result = judge.calibrate(path)
    assert result["n"] == 100 and result["confusion"] == cm
    assert (result["precision"], result["recall"], result["kappa"]) == (p, r, k)
    assert result["passed"] is passed
    assert result["corrected_fail_rate"] == 0.3
    assert judge.main(["--csv", str(path), "--audit", "5"]) == exit_code
    assert ("PASS floors" if passed else "FAIL floors") in capsys.readouterr().out


def test_constant_all_pass_judge_fails_without_crashing(tmp_path):
    path = tmp_path / "constant.csv"
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["item_id", "reply", "human", "judge"])
        writer.writeheader()
        writer.writerow(dict(item_id="constant", reply="ok", human="PASS", judge="PASS"))
    result = judge.calibrate(path)
    assert result["passed"] is False
    assert math.isnan(result["kappa"])
    assert math.isnan(result["corrected_fail_rate"])
