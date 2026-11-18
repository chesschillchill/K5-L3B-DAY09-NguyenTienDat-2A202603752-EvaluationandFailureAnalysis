"""M7: reject damaged evidence and weaker gates without variant-specific rules."""
import copy

import pytest

from lab9.gate import check, integrity_check

pytestmark = pytest.mark.student


@pytest.fixture
def evidence():
    spec = {"eval_set_version": "v2", "seeds": [11, 22], "metrics": [
        {"id": "pass_rate", "kind": "capability", "blocking": True,
         "threshold": {"min": .8, "no_significant_drop": True}},
        {"id": "approval_bypass", "kind": "safety", "blocking": True,
         "threshold": {"max": 0}},
        {"id": "cost_per_success", "threshold": {"max_increase": .1}},
    ], "slices": [{"name": "money", "metric": "pass_rate", "min": .9,
                   "no_significant_drop": True, "blocking": True}]}
    report = {"manifest": {"eval_set_sha": "same", "items": 3, "seeds": [11, 22]},
              "evaluator_failures": [], "metrics": {"pass_rate": 1., "approval_bypass": 0,
                                                    "cost_per_success": 1.},
              "rows": [{"item_id": item, "seed": seed, "slices": ["money", "other"],
                        "pass_rate": True, "approval_bypass": False, "cost": 1.}
                       for item in ("a", "b", "c") for seed in (11, 22)]}
    return report, spec


def test_valid_and_reordered_evidence(evidence):
    base, spec = evidence
    pr = copy.deepcopy(base)
    pr["rows"].reverse()
    pr["manifest"]["seeds"].reverse()
    for r in pr["rows"]:
        r["slices"].reverse()
    assert check(pr, base, spec, spec)[0] == []


@pytest.mark.parametrize("damage", [
    "nan", "inf", "negative_inf", "duplicate", "dropped", "replace_pair", "drop_item",
    "cherry_seed", "replace_seed", "duplicate_seed", "manifest_count", "missing_grade",
    "none_grade", "nan_grade", "inf_grade", "evaluator_failure", "slice_all", "slice_one",
    "safety_average", "cost_nan",
])
def test_green_aggregates_cannot_hide_broken_evidence(evidence, damage):
    base, spec = evidence
    pr = copy.deepcopy(base)
    if damage in ("nan", "inf", "negative_inf"):
        pr["metrics"]["diagnostic"] = float({"nan": "nan", "inf": "inf", "negative_inf": "-inf"}[damage])
    elif damage == "duplicate":
        pr["rows"].append(copy.deepcopy(pr["rows"][0]))
    elif damage == "dropped":
        pr["rows"].pop()
    elif damage == "replace_pair":
        pr["rows"][-1] = copy.deepcopy(pr["rows"][0])
    elif damage == "drop_item":
        pr["rows"] = [r for r in pr["rows"] if r["item_id"] != "c"]
        pr["manifest"]["items"] = 2
    elif damage in ("cherry_seed", "replace_seed"):
        if damage == "cherry_seed":
            pr["rows"] = [r for r in pr["rows"] if r["seed"] == 11]
            pr["manifest"]["seeds"] = [11]
        else:
            for r in pr["rows"]:
                if r["seed"] == 22:
                    r["seed"] = 99
            pr["manifest"]["seeds"] = [11, 99]
    elif damage == "duplicate_seed":
        pr["manifest"]["seeds"] = [11, 11]
    elif damage == "manifest_count":
        pr["manifest"]["items"] = 4
    elif damage == "missing_grade":
        for r in pr["rows"]:
            r.pop("pass_rate")
    elif damage in ("none_grade", "nan_grade", "inf_grade"):
        pr["rows"][0]["pass_rate"] = {"none_grade": None, "nan_grade": float("nan"), "inf_grade": float("inf")}[damage]
    elif damage == "evaluator_failure":
        pr["evaluator_failures"] = ["grader crashed"]
    elif damage in ("slice_all", "slice_one"):
        for r in pr["rows"] if damage == "slice_all" else pr["rows"][:1]:
            r["slices"] = ["other"]
    elif damage == "safety_average":
        pr["rows"][0]["approval_bypass"] = True
        pr["metrics"]["approval_bypass"] = 1 / 6
    elif damage == "cost_nan":
        pr["rows"][0]["cost"] = float("nan")
    blocked, lines = check(pr, base, spec)
    assert blocked == ["integrity"]
    assert all("INTEGRITY" in line for line in lines)
    # A damaged baseline must not silently become trusted reference evidence either.
    assert integrity_check(base, pr, spec)


@pytest.mark.parametrize("section", ["metrics", "slices"])
@pytest.mark.parametrize("change", ["remove", "blocking", "min", "remove_min", "ci"])
def test_ratchet_covers_metrics_and_slices(evidence, section, change):
    report, old = evidence
    new = copy.deepcopy(old)
    entry = new[section][0]
    threshold = entry["threshold"] if section == "metrics" else entry
    if change == "remove":
        new[section].pop(0)
    elif change == "blocking":
        entry["blocking"] = False
    elif change == "min":
        threshold["min"] -= .1
    elif change == "remove_min":
        threshold.pop("min")
    else:
        threshold.pop("no_significant_drop")
    # Bumping only the metric spec version does not bypass the eval-set ratchet.
    new["metric_spec_version"] = "99"
    assert any("ratchet" in p for p in integrity_check(report, report, new, old))


@pytest.mark.parametrize("mid,bound,value", [
    (1, "max", 1), (1, "max", None), (1, "max", float("nan")),
    (2, "max_increase", .2), (2, "max_increase", None),
])
def test_ratchet_upper_bounds(evidence, mid, bound, value):
    report, old = evidence
    new = copy.deepcopy(old)
    if value is None:
        new["metrics"][mid]["threshold"].pop(bound)
    else:
        new["metrics"][mid]["threshold"][bound] = value
    assert any("ratchet" in p for p in integrity_check(report, report, new, old))


def test_ratchet_accepts_stricter_thresholds_and_new_eval_version(evidence):
    report, old = evidence
    strict = copy.deepcopy(old)
    strict["metrics"][0]["threshold"]["min"] = .9
    strict["metrics"][2]["threshold"]["max_increase"] = .05
    strict["slices"][0]["min"] = .95
    assert integrity_check(report, report, strict, old) == []
    fresh = copy.deepcopy(old)
    fresh["eval_set_version"] = "v3"
    fresh["metrics"][0]["threshold"]["min"] = .5
    assert integrity_check(report, report, fresh, old) == []


def test_both_reports_cannot_cherry_pick_spec_seeds(evidence):
    report, spec = evidence
    report["rows"] = [r for r in report["rows"] if r["seed"] == 11]
    report["manifest"]["seeds"] = [11]
    assert any("seeds differ from spec" in p for p in integrity_check(report, report, spec))
