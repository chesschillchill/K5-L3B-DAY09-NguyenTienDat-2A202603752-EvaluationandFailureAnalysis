# M3 — Trajectory và trace case

## Kết quả kiểm tra

Eval set `c23639c10f29`, 14 item × 5 seed `[11,22,33,44,55]`, MockLLM.

| Report trong `src/reports/` | Run ID | Pass rate | Reply/ledger đúng | Proposal đúng |
|---|---|---:|---:|---:|
| `eval_fixed.json` | `E-fixed-20261118-c236` | 100% | 100% | 100% |
| `m3_honest_refactor.json` | `E-honest_refactor-20261118-c236` | 100% | 100% | 100% |
| `baseline_v1.json` | `E-swarm-20261118-c236` | 98,57% | 100%* | 98,57% |
| `eval_seeded_regression.json` | `E-seeded_regression-20261118-c236` | 71,43% | 78,57% | 78,57% |

`mutation --detect`: giải thích được **20/20 trial lỗi (100%)**, báo nhầm **0/70 trial fixed (0%)**. `honest_refactor` cũng không có trial bị grader phụ báo lỗi. Cả 4 report có 70 dòng, đủ item/seed, không thiếu điểm và không có evaluator failure.

21 test M3 đạt; test host: 57 passed. Report được sinh bằng `lab9.eval`, không sửa tay.

## Trace lỗi trong report

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-013@11`, item `E-013`, report `eval_seeded_regression.json` |
| Run ID trace | `R-seeded_regression-C-013-s11` |
| Triệu chứng | Lab 8 FAIL `proposal_mismatch`; proposal 0 thay vì 35.000; ledger 0 và trạng thái denied vẫn khớp nhãn |
| Bước sai đầu tiên | Event **5**, `proposal`, `{"amount_vnd": 0}` |
| Các bước trước | Event 1 handoff đúng quyền; 2 đọc DB đơn O-505; 3 quote 35.000 theo SHIP-LATE-03; 4 đọc lịch sử đã hoàn 35.000. Đọc lịch sử hợp lệ; tự trừ trước khi gọi host mới sai |
| Failure mode | FM-05: trừ lịch sử hoàn tiền ở agent, trong khi host chịu trách nhiệm xử lý lịch sử |
| Đối chứng | `fixed C-013@11`, `R-fixed-C-013-s11`: giữ proposal 35.000, host từ chối hoàn thêm; Lab 8 PASS |
| Regression test | `test_fm05_c013_wrong_proposal_despite_correct_ledger`: `ProposalAmountCorrect` FAIL trên lỗi, PASS trên `fixed` và `honest_refactor`; `RefundAmountCorrect` PASS cả ba |
| Giới hạn | Event cho thấy proposal sai, không chứng minh agent đã ghi tiền trái phép; ledger không đổi |

Grader `proposal_amount_correct` là chẩn đoán, không blocking. Nếu chỉ dùng các grader ban đầu cùng FM-08, tỷ lệ phát hiện là 75%; thêm kiểm proposal bắt được 5 trial C-013 còn lại.

```bash
cd src
.venv/bin/python -m lab9.trace_case --shape seeded_regression --claim C-013 --seed 11
.venv/bin/python -m lab9.trace_case --shape fixed --claim C-013 --seed 11
```

## FM-08 — reply sai dù ledger đúng

`test_fm08_misreport_c008_and_fixed_control` đăng ký shape tạm bằng công tắc `misreport` có sẵn; không sửa variant được cung cấp.

- Trace `R-m3_misreport-C-008-s11`: event 1 handoff, 2 đọc đơn O-808, 3 quote 35.000 đều đúng. Host trừ lịch sử, ledger ghi 20.000.
- Bước sai đầu tiên: event **4**, `reply`, `{"text":"Dạ, LogiX đã hoàn 35.000đ cho đơn O-808."}`. Lab 8 và grader ledger đều PASS; `ReplyLedgerConsistent` FAIL.
- Đối chứng `R-fixed-C-008-s11`: cùng quote/ledger, event 4 nói `20.000đ`; grader mới PASS.

Metric `reply_ledger_consistent`: capability, trajectory, code, **blocking**, sàn **1,0**. Đối chiếu số tiền có đơn vị `đ`, `₫`, `đồng`, `VND`; chấp nhận chữ số liền hoặc dấu phân nhóm chấm/phẩy/khoảng trắng. Không dùng số trong mã đơn hay proposal thay cho ledger. Reply resolved thiếu số tiền cũng FAIL.

*Phạm vi:* trial không có event `reply` được bỏ qua có lý do `outside scope`; vì thế 100% của `swarm` không chứng minh lời trả lời đúng. Chỉ kiểm số tiền VND tường minh, chưa hiểu số viết bằng chữ hoặc ngữ nghĩa câu chứa nhiều khoản tiền khác nhau. Grader áp dụng cho contract reply đơn khoản của lab.

## Chạy lại

```bash
cd src
.venv/bin/python -m pytest -q -o addopts= tests/test_lab9_graders.py tests/test_m3_trajectory.py
.venv/bin/python -m lab9.mutation --detect
.venv/bin/python -m lab9.eval --shape fixed --out reports/eval_fixed.json
.venv/bin/python -m lab9.eval --shape honest_refactor --out reports/m3_honest_refactor.json
.venv/bin/python -m lab9.eval --shape swarm --out reports/baseline_v1.json
.venv/bin/python -m lab9.eval --shape seeded_regression --out reports/eval_seeded_regression.json
```

Gate và kiểm tra v2 xem [eval_card.md](eval_card.md). Chưa có kết quả bộ chấm ẩn.
