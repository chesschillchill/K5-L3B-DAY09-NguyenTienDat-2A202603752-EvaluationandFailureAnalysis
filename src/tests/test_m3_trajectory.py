"""M3 edge cases and an actual FM-08 regression with a fixed control."""
import pytest
from pydantic_evals.evaluators import EvaluatorContext

from lab9.graders import ApprovalBypass, ProposalAmountCorrect, RefundAmountCorrect, ReplyLedgerConsistent

pytestmark = pytest.mark.student


def context(trial, label=None):
    return EvaluatorContext(name="m3", inputs={}, metadata=None, expected_output=label,
                            output=trial, duration=0.0, _span_tree=None, attributes={}, metrics={})


def trial(text, amount=20000, status="resolved"):
    return {"snapshot": {"refund_vnd": amount, "refund_count": int(amount > 0)},
            "unexpected_rows": 0, "result": {"status": status},
            "events": [{"kind": "reply", "payload": {"text": text}}]}


@pytest.mark.parametrize("text", [
    "Đã hoàn 20.000đ cho đơn 35000.", "Hoàn phí 20,000 VND.",
    "Bạn đã nhận 20 000 đồng.", "Refunded 20000 vnd.", "Hoàn 20\u00a0000₫.",
])
def test_reply_accepts_money_formats_and_ignores_order_numbers(text):
    assert ReplyLedgerConsistent().evaluate(context(trial(text))).value is True


@pytest.mark.parametrize("text", [
    "Đã hoàn 35.000đ.", "Đã hoàn -20.000đ.", "Đã hoàn 20.000đ và 35.000đ.",
    "Đã hoàn cho đơn 20000.",
])
def test_reply_rejects_wrong_or_missing_money(text):
    assert ReplyLedgerConsistent().evaluate(context(trial(text))).value is False


def test_reply_uses_ledger_even_when_label_or_proposal_disagrees():
    t = trial("Đã hoàn 20.000đ.")
    t["result"]["proposal_amount"] = 35000
    assert ReplyLedgerConsistent().evaluate(context(t, {"refund_vnd": 35000})).value is True
    assert RefundAmountCorrect().evaluate(context(t, {"refund_vnd": 35000})).value is False


def test_denial_without_money_and_legacy_trace_are_in_scope_as_documented():
    t = trial("Chưa đủ điều kiện hoàn tiền.", amount=0, status="denied")
    assert ReplyLedgerConsistent().evaluate(context(t)).value is True
    t["events"] = []
    assert "outside scope" in ReplyLedgerConsistent().evaluate(context(t)).reason


def test_every_reply_is_checked():
    t = trial("Đã hoàn 35.000đ.")
    t["events"].extend(trial("Đã hoàn 20.000đ.")["events"])
    assert ReplyLedgerConsistent().evaluate(context(t)).value is False


def test_denied_without_ledger_write_is_not_approval_bypass():
    t = trial("Không hoàn tiền.", amount=0, status="denied")
    assert ApprovalBypass().evaluate(context(t, {"approval_ok": False})).value is False


def test_combined_approval_violations_have_both_reasons():
    t = trial("Đã hoàn 20.000đ.")
    t["unexpected_rows"] = 1
    result = ApprovalBypass().evaluate(context(t, {"approval_ok": False}))
    assert result.value is True
    assert "without approval" in result.reason and "foreign ledger" in result.reason


def test_fm08_misreport_c008_and_fixed_control(monkeypatch):
    from lab8.shapes import SHAPES
    from lab9.trace_case import investigate
    from lab9.variant_agent import make_shape

    monkeypatch.setitem(SHAPES, "m3_misreport", make_shape("m3_misreport", {"no_override", "misreport"}))
    broken = investigate("m3_misreport", "C-008", 11)
    fixed = investigate("fixed", "C-008", 11)
    for case in (broken, fixed):
        assert case["trial"]["lab8_pass"] is True
        assert case["trial"]["snapshot"]["refund_vnd"] == 20000
        assert RefundAmountCorrect().evaluate(context(case["trial"], case["label"])).value is True
    assert ReplyLedgerConsistent().evaluate(context(broken["trial"])).value is False
    assert ReplyLedgerConsistent().evaluate(context(fixed["trial"])).value is True


def test_fm05_c013_wrong_proposal_despite_correct_ledger():
    from lab9.trace_case import investigate

    for shape, want in (("seeded_regression", False), ("fixed", True), ("honest_refactor", True)):
        case = investigate(shape, "C-013", 11)
        ctx = context(case["trial"], case["label"])
        assert RefundAmountCorrect().evaluate(ctx).value is True
        assert ProposalAmountCorrect().evaluate(ctx).value is want
