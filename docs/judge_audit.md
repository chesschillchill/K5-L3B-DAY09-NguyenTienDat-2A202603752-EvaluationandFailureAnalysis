# M2 — Judge calibration và audit

## Calibration

Nguồn: `src/data/eval/judge_{tone,helpful}_public.csv`, mỗi tệp 100 dòng. Backend replay; giữ nguyên nhãn gốc. Lớp dương là **FAIL**: TP là bắt đúng lỗi, FN là bỏ lọt lỗi.

| Tiêu chí | n | κ | Precision | Recall | Ngưỡng κ≥0,6; P≥0,8; R≥0,7 | Quyết định |
|---|---:|---:|---:|---:|---|---|
| tone_ok | 100 | 0,757 | 0,857 | 0,800 | PASS, CLI exit 0 | Dùng cho tone trong phạm vi đã hiệu chuẩn |
| helpful | 100 | 0,375 | 1,000 | 0,300 | FAIL, CLI exit 1 | Loại khỏi gate |

| Tiêu chí | TP | FP | FN | TN | Tỷ lệ lỗi quan sát → Rogan–Gladen |
|---|---:|---:|---:|---:|---|
| tone_ok | 24 | 4 | 6 | 66 | 28% → 30% |
| helpful | 9 | 0 | 21 | 70 | 9% → 30% |

Rogan–Gladen dùng recall làm sensitivity và TN/(TN+FP) làm specificity; kết quả chặn trong [0,1]. Hiệu chỉnh trên chính tập calibration chỉ tái tạo tỷ lệ nhãn người, không chứng minh judge tổng quát tốt. κ không xác định hoặc judge không bắt lỗi phải FAIL calibration; mẫu số RG bằng 0 trả NaN ở CLI, không coi là tỷ lệ lỗi 0.

## Audit bất đồng

Kết luận dựa trên reply và ghi chú có sẵn trong CSV. Các số ledger dưới đây lấy từ cột `note`, chưa phải trace/ledger được chạy lại.

| Case | Judge / người | Ai đúng, bằng chứng | Sửa rubric / hành động |
|---|---|---|---|
| H-008 | PASS / FAIL | Người: xưng “em”, dùng “nha”, “check giúp em” quá suồng sã theo quy ước CS của bộ dữ liệu | Nêu rõ xưng hô và từ thân mật không phù hợp; không đồng nhất thân thiện với đúng tone |
| H-017 | PASS / FAIL | Người theo ngữ cảnh ghi chú: khách lớn tuổi, reply dùng “bạn”, “nha”; chỉ reply không cho biết tuổi khách | Cho judge ngữ cảnh xưng hô; thiếu ngữ cảnh thì chuyển người duyệt, không tự đoán tuổi |
| H-029 | PASS / FAIL | Người: “không cần nhắn thêm” mang giọng ra lệnh; có “Dạ” không bù được | Chấm toàn câu, thêm ví dụ mệnh lệnh cần FAIL |
| H-042 | FAIL / PASS | Người: reply ngắn, lịch sự và đủ thông tin; không có lý do bắt buộc xin lỗi trong mọi câu | Không trừ điểm chỉ vì thiếu xin lỗi; không thưởng độ dài |
| H-051 | FAIL / PASS | Người: từ “refund” được CS cho phép theo ghi chú | Đưa từ được phép vào rubric; không FAIL chỉ vì có tiếng Anh |
| H-070 | PASS / FAIL | Người: emoji cười trong ngữ cảnh khiếu nại không phù hợp | Thêm phản ví dụ emoji; tách lịch sự khỏi dấu hiệu vui vẻ |
| H-081 | FAIL / PASS | Theo `note`, nhãn người sai do đọc nhầm ticket và judge đúng. Tuy nhiên reply riêng lẻ vẫn lịch sự; không có ticket để xác minh lại lỗi tone | Đánh dấu cần phân xử nhãn; tách tính đúng chính sách khỏi tone. Giữ CSV gốc, chưa tính lại calibration bằng nhãn sửa |
| H-088 | FAIL / PASS | Người: lặp “Dạ” do lỗi gõ, không đổi thái độ phục vụ | Cho phép lỗi gõ nhẹ không ảnh hưởng nghĩa; tránh phạt quá mức |
| H-094 | PASS / FAIL | Người theo chuẩn dữ liệu: reply mất dấu tiếng Việt | Ghi rõ yêu cầu tiếng Việt có dấu trong rubric |
| HL-015 | PASS / FAIL | Người: reply 55.000đ, ghi chú ledger 40.000đ | Sai tiền phải FAIL dù câu lịch sự; đối chiếu ledger bằng code |
| HL-016 | PASS / FAIL | Người: 55.000đ so với ledger 35.000đ; lời xin lỗi dài không sửa được sai tiền | Không cộng điểm cho xin lỗi lặp; ưu tiên factual correctness |
| HL-020 | PASS / FAIL | Người: 90.000đ so với ledger 120.000đ | Bắt cả báo thiếu tiền và báo thừa tiền |
| HL-028 | PASS / FAIL | Người: 50.000đ so với ledger 35.000đ, câu xin lỗi lặp | Kiểm tiền độc lập với văn phong/độ dài |
| HL-047 | PASS / FAIL | Người: “Ok bạn … xử lý rồi nhé” sai xưng hô theo nhãn, không nói rõ kết quả | Tách tiêu chí xưng hô và thông tin kết quả; không chấp nhận chỉ vì nói đã xử lý |

## Quyết định sử dụng

Helpful bỏ lọt 21/30 lỗi (70%), trong đó 18 sai tiền và 3 sai xưng hô. Precision 1,0 chỉ nói rằng 9 lần báo FAIL đều đúng; judge vẫn cho qua phần lớn lỗi. Các câu sai tiền kèm lời xin lỗi dài được PASS cho thấy dấu hiệu thiên lệch theo văn phong, chưa đủ để kết luận quan hệ nhân quả. Không dùng helpful làm gate hoặc thay grader tiền/approval.

Tone đạt cả ba ngưỡng trên nhãn gốc nhưng vẫn có 6 FN, 4 FP và một nhãn cần phân xử. Chỉ dùng cho tone; không suy ra tiền, quyền hay chính sách đúng. H-063 hứa hoàn thêm là điểm giao giữa tone và cam kết nghiệp vụ: cần tách kiểm cam kết khỏi chấm độ lịch sự trong rubric tiếp theo.

M3 xử lý tiền bằng code: `ReplyLedgerConsistent` bắt reply lệch ledger; `RefundAmountCorrect` bắt ledger lệch nhãn; `ApprovalBypass` bắt ghi tiền không được duyệt/ngoài claim; `ProposalAmountCorrect` bắt proposal sai dù ledger không đổi. Không chuyển các quyết định này cho judge.

Các sửa rubric trên là đề xuất, chưa phải kết quả judge mới. Cần phân xử nhãn bằng ngữ cảnh đầy đủ, lấy tập có nhãn người độc lập và hiệu chuẩn lại trước khi mở rộng. Replay public không phải đánh giá trên tập giữ kín hoặc LLM thật.

## Kiểm tra lại M2–M3

```bash
cd src
.venv/bin/python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 5
.venv/bin/python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 5
.venv/bin/python -m pytest -q -o addopts= tests/test_lab9_stats.py tests/test_m2_calibration.py tests/test_lab9_graders.py tests/test_m3_trajectory.py -k 'not paired_bootstrap'
.venv/bin/python -m lab9.mutation --detect
```

Kết quả: **37 passed, 2 deselected**; hai test bỏ qua thuộc bootstrap M4. M3 phát hiện **20/20 (100%)**, báo nhầm **0/70 fixed**, **0/70 honest_refactor**. Bộ test host: **57 passed**; eval set **0 problem**. Giới hạn metric reply và trace case xem `docs/trace_case.md`.
