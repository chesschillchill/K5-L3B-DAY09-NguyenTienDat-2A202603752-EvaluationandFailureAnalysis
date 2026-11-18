"""M5: item-level slice decisions and reproducible v2 coverage."""
import copy
import json
from collections import Counter

import pytest

from lab9 import evalset, gate
from lab9.eval import load_spec

pytestmark = pytest.mark.student


def report(values, name="custom"):
    return {"rows": [{"item_id": f"E-{i}", "seed": seed, "pass_rate": val,
                       "slices": [name]}
                      for i, val in enumerate(values) for seed in (11, 22)]}


def spec(**overrides):
    return {"slices": [{"name": "custom", "metric": "pass_rate", "min": .85,
                        "blocking": True, **overrides}]}


@pytest.mark.parametrize("value,blocked", [(.84, True), (.85, False), (1, False)])
def test_slice_floor_boundary(value, blocked):
    ids, _ = gate.slice_check(report([value] * 3), report([1] * 3), spec())
    assert ids == (["slice:custom/pass_rate"] if blocked else [])


def test_ci_blocks_drop_above_floor_and_respects_flag():
    pr, base = report([.9] * 4), report([1] * 4)
    ids, lines = gate.slice_check(pr, base, spec(no_significant_drop=True))
    assert ids == ["slice:custom/pass_rate"]
    assert "CI [-0.100, -0.100]" in lines[0]
    assert gate.slice_check(pr, base, spec(no_significant_drop=False))[0] == []
    assert gate.slice_check(base, base, spec(no_significant_drop=True))[0] == []


def test_ci_touching_zero_does_not_block():
    ids, lines = gate.slice_check(report([0] + [1] * 13), report([1] * 14),
                                 spec(no_significant_drop=True))
    assert ids == []
    assert "+0.000]" in lines[0]


def test_slice_warning_and_missing_data():
    ids, lines = gate.slice_check(report([0, 0]), report([1, 1]), spec(blocking=False))
    assert ids == []
    assert "warn" in lines[0]
    ids, lines = gate.slice_check(report([], name="other"), report([1, 1]), spec())
    assert ids == ["slice:custom/pass_rate"]
    assert "MISSING" in lines[0]


@pytest.mark.parametrize("value,blocked", [(1, False), (.5, True)])
def test_single_item_checks_floor_without_bootstrap(value, blocked):
    ids, lines = gate.slice_check(report([value]), report([1]), spec(no_significant_drop=True))
    assert bool(ids) == blocked
    assert "CI unavailable: 1 paired item(s)" in lines[0]


def test_pairs_item_means_and_uses_spec_bootstrap(monkeypatch):
    base = report([1, .5])
    pr = report([.5, 1])
    # Unequal seed counts distinguish item means from a pooled row mean.
    pr["rows"].append(copy.deepcopy(pr["rows"][0]))
    pr["rows"].append({"item_id": "outside", "seed": 11, "pass_rate": 0, "slices": []})
    pr["rows"].reverse()
    config = spec(min=.75, no_significant_drop=True)
    config["bootstrap"] = {"n_resamples": 2000, "rng": 42, "confidence": .8}
    calls = []

    def bootstrap(a, b, **kwargs):
        calls.append((a, b, kwargs))
        return 0, -.5, .5

    monkeypatch.setattr(gate.stats, "paired_bootstrap", bootstrap)
    ids, lines = gate.slice_check(pr, base, config)
    assert ids == []
    assert "0.7500" in lines[0] and "n=2" in lines[0]
    assert calls == [([.5, 1], [1, .5], {"n_resamples": 2000, "rng": 42, "confidence": .8})]


def test_v2_sources_mapping_labels_and_slices():
    import yaml

    items = evalset.load_jsonl(evalset.ITEMS_V2)
    v1 = evalset.load_jsonl(evalset.ITEMS)
    labels = json.loads(evalset.LABELS_V2.read_text())
    labels_v1 = json.loads(evalset.LABELS.read_text())
    pack = json.loads(evalset.PACK.read_text())
    mapping = yaml.safe_load(evalset.FM_MAP.read_text())
    assert mapping == {"ticket_over_db": "FM-03", "stale_policy": "FM-06",
                       "clause_sum": "FM-04", "double_deduct": "FM-05",
                       "sibling_refund": "FM-07", "denied_ignored": "FM-02",
                       "reply_ledger_mismatch": "FM-08", "cross_principal": "FM-09"}
    assert evalset.check(evalset.ITEMS_V2, evalset.LABELS_V2) == []
    assert len(items) == len(labels) == len({it["item_id"] for it in items}) == 28
    claims = {it["claim_id"] for it in items}
    assert len(claims) == 28
    assert claims == set(labels_v1) | {c["claim_id"] for c in pack["claims"]}
    for old, new in zip(v1, items[:14], strict=True):
        assert new == {**old, "eval_set_version": "v2",
                       "slices": evalset.slices_for(labels_v1[old["claim_id"]], False)}
        assert labels[new["claim_id"]] == labels_v1[new["claim_id"]]
    by_claim = {it["claim_id"]: it for it in items}
    for claim in pack["claims"]:
        item = by_claim[claim["claim_id"]]
        assert item["failure_modes"] == [mapping[m] for m in claim["mechanisms"]]
        assert item["split"] == "adversarial"
        assert labels[claim["claim_id"]] == claim["expected"]
    for item in items:
        assert "expected" not in item and "label" not in item
        assert item["slices"] == evalset.slices_for(labels[item["claim_id"]], item["split"] == "adversarial")
    counts = Counter(fm for it in items for fm in it["failure_modes"])
    assert all(counts[fm] >= 3 for fm in mapping.values())
    assert Counter(t for it in items for t in it["slices"]) == {
        "money_movement": 12, "denial": 11, "escalation": 4, "adversarial": 14}


def test_v2_spec_protects_required_slices_and_reply():
    from pathlib import Path

    config = load_spec(Path("config/metric_spec_v2.yaml"))
    slices = {s["name"]: s for s in config["slices"]}
    for name, floor in (("denial", .9), ("money_movement", .95), ("adversarial", .85)):
        assert slices[name] == {"name": name, "metric": "pass_rate", "min": floor,
                                "no_significant_drop": True, "blocking": True}
    reply = next(m for m in config["metrics"] if m["id"] == "reply_ledger_consistent")
    assert reply["blocking"] is True and reply["threshold"] == {"min": 1.0}


@pytest.mark.parametrize("claim_id,amount", [("C-109", 20000), ("C-112", 25000)])
def test_v2_reply_mismatch_and_honest_controls(monkeypatch, tmp_path, claim_id, amount):
    from pathlib import Path
    from pydantic_evals.evaluators import EvaluatorContext
    from lab8.shapes import SHAPES
    from lab9 import variants
    from lab9.eval import load_world, make_task
    from lab9.graders import ReplyLedgerConsistent
    from lab9.variant_agent import make_shape

    variants.register()
    monkeypatch.setitem(SHAPES, "m5_misreport", make_shape("m5_misreport", {"no_override", "misreport"}))
    world, claims = load_world(load_spec(Path("config/metric_spec_v2.yaml")))
    labels = json.loads(evalset.LABELS_V2.read_text())
    for shape in ("fixed", "honest_refactor", "m5_misreport"):
        trial = make_task(shape, world, claims, labels, tmp_path)({"claim_id": claim_id, "seed": 11})
        assert trial["lab8_pass"] is True
        assert trial["snapshot"]["refund_vnd"] == amount
        ctx = EvaluatorContext(name=claim_id, inputs={}, metadata=None, expected_output=labels[claim_id],
                               output=trial, duration=0.0, _span_tree=None, attributes={}, metrics={})
        assert ReplyLedgerConsistent().evaluate(ctx).value is (shape != "m5_misreport")
