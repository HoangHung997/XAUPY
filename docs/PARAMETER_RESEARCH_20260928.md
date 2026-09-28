# Nghiên cứu bộ tham số — 28/09/2026

**Chưa tìm được bộ có lợi nhuận đạt tiêu chí.** Cả 16 cấu hình đều âm trên train. Ứng viên theo quy tắc đã định cũng âm trên validation, test và stress; không áp vào cấu hình đang chạy. Đây là xếp hạng tương đối trong phạm vi thử, không phải bộ tốt nhất toàn cục hoặc khuyến nghị giao dịch.

## Dữ liệu và phương pháp

- Dùng đủ **100.062 nến M1 XAUUSD**, từ 16/06 đến 28/09/2026 trong kho `data/mt5-history/XAUUSD-20260928-unlimited`. Kho gốc có 598.794 nến trên 8 khung; lần này dùng toàn bộ M1, không cộng các khung trùng thời gian làm mẫu độc lập.
- SHA-256 CSV: `6c451f8eb01bb470c58084204e498b91a050a4653c74d7645b84b3bdf4dacd61`.
- Chia theo ngày giao dịch tuần tự khoảng 60/20/20: train **16/06–17/08**, validation **18/08–07/09**, test **08/09–28/09**. Test không tham gia chọn trong lần chạy này. Lịch sử đã từng được khảo sát ở các lần trước: đây là đánh giá hồi cứu, không phải dữ liệu mới chưa từng thấy.
- Chốt trước 16 bộ: RSI riêng, Z riêng, RSI AND Z, RSI OR Z; RSI 7 với 40/60 hoặc RSI 14 với 35/65; Z20 ±2,5 hoặc Z20/Z30 ±2; hồi RSI 3, hồi Z 0,3; SL 3 hoặc 5 đơn vị giá, TP hai lần SL. Từng tổ hợp cụ thể nằm trong protocol JSON.
- M1 cho ba vai trò; MA tắt; **xác nhận nến đóng**; lot 0,01; vốn giả lập 1.000 USD. Giữ BE mặc định bật tại 1R, offset 0,1; trailing/partial tắt; tối đa 8 lệnh/ngày, nghỉ 3 phút, dừng chuỗi 3 thua; phiên 07–17 và 17–22 trên lịch nguồn. Lưu đầy đủ cấu hình, không chỉ ngưỡng RSI/Z.
- Spread giả định **40 point = 0,40 đơn vị giá**, phí khứ hồi **7 USD/lot**; stress spread **70 point = 0,70**. Đây là giả định, không phải chuỗi spread/commission lịch sử đã đo. Giới hạn spread 1, phí 7, trượt giá dự phòng 20 point, RR ròng tối thiểu 1,2. P/L không giả lập trượt giá khớp thực.
- Giữ nguyên epoch trong kho, không cộng thêm offset. Phiên theo lịch nguồn; chưa chứng minh quy đổi DST toàn giai đoạn. Engine `M1_OHLC_COST_GUARDS_V2` dùng chính sách OHLC đã công bố, không biết thứ tự tick thực.
- Xếp train bằng `net_profit − 0,5 × max_drawdown_usd`, tối thiểu 30 lệnh; lấy ba bộ vào validation. Chọn từ validation bằng cùng quy tắc, sau đó mới chạy test, stress và toàn lịch sử. Điều kiện đạt: net dương và ít nhất 30 lệnh ở từng train/validation/test/stress. Không tính PBO/CSCV hoặc khoảng tin cậy trong đợt này.

## Kết quả 16 bộ trên train

| Bộ | Số lệnh | Ròng USD | Max DD USD | PF | Điểm chọn |
| --- | ---: | ---: | ---: | ---: | ---: |
| RSI-r7-60-z20-2.5-sl3 | 284 | -112.98 | 146.91 | 0.771 | -186.44 |
| RSI-r7-60-z20-2.5-sl5 | 288 | -52.46 | 153.93 | 0.928 | -129.43 |
| RSI-r14-65-z20-2.5-sl3 | 279 | -91.73 | 131.96 | 0.808 | -157.71 |
| RSI-r14-65-z20-2.5-sl5 | 263 | -212.81 | 249.78 | 0.720 | -337.70 |
| Z-r14-65-z20-2.5-sl3 | 99 | -63.13 | 71.11 | 0.693 | -98.69 |
| Z-r14-65-z20-2.5-sl5 | 96 | -54.72 | 80.55 | 0.800 | -95.00 |
| Z-r14-65-z30-2-sl3 | 275 | -58.35 | 69.53 | 0.872 | -93.12 |
| Z-r14-65-z30-2-sl5 | 272 | -77.64 | 175.75 | 0.893 | -165.51 |
| AND-r7-60-z20-2.5-sl3 | 8 | -12.46 | 17.30 | 0.324 | Loại: <30 lệnh |
| AND-r7-60-z20-2.5-sl5 | 8 | -20.46 | 25.32 | 0.327 | Loại: <30 lệnh |
| AND-r14-65-z20-2-sl3 | 75 | -48.75 | 58.76 | 0.647 | -78.13 |
| AND-r14-65-z20-2-sl5 | 72 | -68.34 | 79.61 | 0.671 | -108.15 |
| OR-r7-60-z20-2.5-sl3 | 278 | -112.26 | 137.18 | 0.764 | -180.85 |
| OR-r7-60-z20-2.5-sl5 | 282 | -41.84 | 106.67 | 0.940 | -95.18 |
| OR-r14-65-z30-2-sl3 | 275 | -90.95 | 108.02 | 0.802 | -144.96 |
| OR-r14-65-z30-2-sl5 | 270 | -267.50 | 291.78 | 0.660 | -413.39 |

## Validation và đánh giá sau chọn

| Bộ | Giai đoạn | Số lệnh | Ròng USD | Max DD USD | PF |
| --- | --- | ---: | ---: | ---: | ---: |
| AND-r14-65-z20-2-sl3 | validation | 22 | -37.14 | 44.09 | 0.244 |
| Z-r14-65-z30-2-sl3 | validation | 82 | -114.64 | 120.51 | 0.295 |
| Z-r14-65-z20-2.5-sl5 | validation | 28 | -81.66 | 81.66 | 0.268 |
| Z-r14-65-z30-2-sl3 | test | 87 | -76.59 | 84.67 | 0.555 |
| Z-r14-65-z30-2-sl3 | test-stress | 74 | -81.98 | 89.76 | 0.466 |
| Z-r14-65-z30-2-sl3 | full | 444 | -249.58 | 257.90 | 0.685 |

Ứng viên theo quy tắc: **Z30, ngưỡng −2/+2, hồi 0,3, RSI tắt, SL 3, TP 6**, nến đóng M1. Hai bộ còn lại có validation dưới 30 lệnh nên bị loại dù lỗ USD ít hơn. Bộ được chọn lỗ **76,59 USD / 87 lệnh** trên test, stress lỗ **81,98 USD / 74 lệnh**, toàn kỳ lỗ **249,58 USD / 444 lệnh**. Không có căn cứ gọi bộ này là “đẹp” để áp giao dịch. File ứng viên giữ ở artifacts để tái lập, không thêm vào preset mặc định của app.

Tổng kết toàn kỳ không bằng tổng ba giai đoạn: mỗi lần replay có vốn, trạng thái chỉ báo/lệnh và warm-up riêng ở biên; không cộng cơ học các lần độc lập thành một equity liên tục.

## RSI/Z động trong nến

Replay riêng **10.150 tick thực** đã lưu với `Research_M1_RSI_Z_Comparator.json` cho **5 tín hiệu BUY**. Luồng giữ dấu vết lần chạm cực trị và xét hồi ở nến kế tiếp, không yêu cầu nến chạm phải đóng đúng ngưỡng. Đây là kiểm hành vi tín hiệu, **không tính P/L**, không xác nhận lợi nhuận hoặc thay thế nghiên cứu tick dài hạn. Kho có một packet không đầy đủ/có gap; không tuyên bố quan sát liên tục. Bộ live RSI7 intrabar và comparator tick khác bộ nến đóng nói trên.

Với ý “chạm Z >2,5 rồi hồi về 2,2”, đường hiện có giữ latch cực trị theo tick đã quan sát, mốc nến chạm, cực trị RSI/Z và xét điều kiện hồi. Đợt này kiểm lại đường latch đó; chưa có engine P/L tick đủ phạm vi để tuyên bố tối ưu ngưỡng intrabar từ OHLC.

## Tái lập và bước nghiên cứu tiếp

- Script `scripts/research_parameters.py` chạy offline, hai worker, không truy cập/gửi lệnh MT5. `artifacts/parameter-remediation-20260928/` chứa protocol, summary, dataset, selected-profile, kết quả từng lần chạy, trade ledger và result hash. Replay tick bằng `scripts/replay_intrabar_ticks.py` lưu trong `intrabar-regression.json`.
- Kết luận **không có ứng viên đạt**, giữ nguyên ngưỡng live. Cần tick dài hơn và kiểm P/L intrabar với Bid/Ask, phí, quản lý lệnh, phiên đã đối chiếu trước khi chọn bộ thử tiếp. Nếu mở rộng tìm kiếm phải khai báo phạm vi mới và dùng forward mới, không liên tục chỉnh đến khi test cũ có lãi.

Thử nhiều cấu hình trên cùng lịch sử làm tăng nguy cơ chọn kết quả ngẫu nhiên: [Bailey và cộng sự, The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf). Nguồn tick và quy tắc thời gian API: [MetaQuotes — copy_ticks_range](https://www.mql5.com/en/docs/python_metatrader5/mt5copyticksrange_py). Hai nguồn giải thích phương pháp/giới hạn; số liệu báo cáo đến từ lần chạy cục bộ.
