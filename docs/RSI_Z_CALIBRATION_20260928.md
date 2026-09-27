# Nghiên cứu RSI/Z trên lịch sử MT5

Ngày chạy: 28/09/2026. Dữ liệu được cố định trong archive `data/mt5-history/XAUUSD-20260928-unlimited/`; đây là lịch sử hiện MT5/provider trả về sau khi tăng Max bars, không phải tuyên bố có toàn bộ lịch sử broker. Các file dữ liệu gốc và kết quả chi tiết lưu tại máy, không đẩy lên GitHub.

Đã phân tích 598,794 nến đóng, 8 khung thời gian; 90 bộ tham số/khung. 0 ứng viên vượt điều kiện kiểm tra ngoài mẫu.

Đây là nghiên cứu phản ứng giá sau tín hiệu đảo chiều, chưa phải lợi nhuận của toàn bộ chiến lược Direction → Pullback → Trigger. Không tự áp tham số vào profile đang chạy.

## Phương pháp

Việc ghi nhớ lần chạm trong nến là một thay đổi đúng về nhận diện tín hiệu; nó không tự chứng minh lợi nhuận cao hơn. Trong nghiên cứu này, 90 bộ mỗi khung tương đương 720 phép thử. Mỗi họ RSI, Z, RSI+Z chọn một ứng viên bằng mẫu đầu; cả 24 ứng viên được chọn đều không vượt điều kiện giữ lại trên hai mẫu sau. Không có bộ nào được tự áp dụng vào profile đang chạy.

- RSI Wilder và Z dùng độ lệch chuẩn tổng thể, khớp công thức Engine.
- Ghi nhận chạm ngưỡng từ high/low trong nến; chỉ xác nhận hồi tại giá đóng của nến sau; giá vào giả định ở open kế tiếp, giá ra ở close sau 5 nến; setup hết hạn sau 2 nến.
- Loại setup và kết quả đi qua khoảng trống thời gian, kể cả nghỉ thị trường; không tự lấp nến thiếu.
- Các sự kiện không chồng thời gian. Chia 60% chọn tham số, 20% kiểm tra, 20% kiểm tra cuối; không chuyển setup hoặc kết quả vượt ranh giới mẫu.
- Chọn riêng từng họ RSI, Z, RSI+Z bằng cận dưới trung bình của mẫu đầu. Hai mẫu sau không được dùng để đổi lựa chọn.
- Trừ spread lịch sử theo nến. Phí và trượt giá bổ sung chỉ có khi truyền --extra-cost; không có SL/TP, quản trị vốn hoặc bộ lọc hướng trong phép đo này.
- Khoảng tin cậy là mô tả thống kê; chưa hiệu chỉnh toàn bộ việc thử nhiều bộ tham số hoặc phụ thuộc theo thời gian. OHLC không chứng minh được thứ tự từng tick.
- Tám khung có khoảng ngày lịch sử khác nhau; không xếp hạng hiệu quả giữa các khung như thể chúng cùng giai đoạn thị trường. Giá trị tick trong backtest toàn chiến lược lấy theo metadata hiện tại của symbol, không tái dựng mọi thay đổi hợp đồng lịch sử.

## Dữ liệu và ứng viên được chọn trên mẫu đầu

Các mức dưới đây là kết quả nghiên cứu, không phải bộ cấu hình đã được xác nhận để giao dịch. Đơn vị kết quả là chênh lệch giá XAUUSD sau spread, không phải USD tài khoản hoặc phần trăm lợi nhuận.

| Khung | Nến | Họ | Tham số | Số sự kiện test | TB kiểm tra | TB test | Kết luận |
|---|---:|---|---|---:|---:|---:|---|
| M1 | 100,062 | RSI | RSI(7) 40/60, hồi 3 | 2465 | -0.1785 | -0.2188 | Chưa đạt |
| M1 | 100,062 | Z | Z(20) ±2, hồi 0.5 | 1130 | -0.2054 | -0.1975 | Chưa đạt |
| M1 | 100,062 | RSI_AND_Z | RSI(14) 40/60, hồi 3; Z(20) ±2, hồi 0.3 | 989 | -0.1708 | -0.1605 | Chưa đạt |
| M3 | 100,000 | RSI | RSI(7) 40/60, hồi 5 | 2357 | -0.3382 | -0.4472 | Chưa đạt |
| M3 | 100,000 | Z | Z(30) ±2, hồi 0.2 | 1115 | -0.3294 | -0.5203 | Chưa đạt |
| M3 | 100,000 | RSI_AND_Z | RSI(14) 35/65, hồi 3; Z(20) ±2.5, hồi 0.5 | 381 | 0.1247 | -0.8096 | Chưa đạt |
| M5 | 100,012 | RSI | RSI(14) 40/60, hồi 8 | 1255 | -0.3877 | -0.1895 | Chưa đạt |
| M5 | 100,012 | Z | Z(20) ±1.5, hồi 0.2 | 1960 | -0.6286 | -0.3179 | Chưa đạt |
| M5 | 100,012 | RSI_AND_Z | RSI(14) 40/60, hồi 5; Z(20) ±1.5, hồi 0.3 | 1342 | -0.4622 | -0.4345 | Chưa đạt |
| M15 | 100,000 | RSI | RSI(7) 40/60, hồi 5 | 2333 | -0.1786 | -0.6935 | Chưa đạt |
| M15 | 100,000 | Z | Z(20) ±1.5, hồi 0.2 | 1894 | -0.4192 | -0.7662 | Chưa đạt |
| M15 | 100,000 | RSI_AND_Z | RSI(14) 35/65, hồi 3; Z(20) ±1.5, hồi 0.3 | 1052 | -0.7882 | -0.9948 | Chưa đạt |
| M30 | 100,083 | RSI | RSI(7) 40/60, hồi 3 | 2338 | -0.3088 | -0.4143 | Chưa đạt |
| M30 | 100,083 | Z | Z(20) ±1.5, hồi 0.5 | 1658 | -0.2394 | -0.3941 | Chưa đạt |
| M30 | 100,083 | RSI_AND_Z | RSI(14) 40/60, hồi 5; Z(20) ±2, hồi 0.5 | 890 | -0.2573 | -1.0718 | Chưa đạt |
| H1 | 53,325 | RSI | RSI(14) 40/60, hồi 3 | 891 | -0.5811 | -1.0084 | Chưa đạt |
| H1 | 53,325 | Z | Z(50) ±1.5, hồi 0.2 | 740 | -1.2265 | -0.7926 | Chưa đạt |
| H1 | 53,325 | RSI_AND_Z | RSI(14) 35/65, hồi 3; Z(20) ±2, hồi 0.3 | 390 | 0.3696 | -1.5860 | Chưa đạt |
| H2 | 29,244 | RSI | RSI(21) 40/60, hồi 8 | 167 | -0.0019 | -2.9266 | Chưa đạt |
| H2 | 29,244 | Z | Z(20) ±1.5, hồi 0.5 | 470 | -0.7166 | -1.6563 | Chưa đạt |
| H2 | 29,244 | RSI_AND_Z | RSI(14) 30/70, hồi 3; Z(20) ±1.5, hồi 0.3 | 185 | -0.5613 | -4.5259 | Chưa đạt |
| H4 | 16,068 | RSI | RSI(7) 40/60, hồi 8 | 293 | -0.0872 | 2.6371 | Chưa đạt |
| H4 | 16,068 | Z | Z(50) ±1.5, hồi 0.2 | 216 | -0.3514 | -1.1677 | Chưa đạt |
| H4 | 16,068 | RSI_AND_Z | RSI(14) 35/65, hồi 5; Z(20) ±1.5, hồi 0.5 | 137 | -0.7538 | 4.5200 | Chưa đạt |

## Chạm trong nến so với chỉ nhìn giá đóng

Cùng bộ tham số được chọn, cùng mẫu test; số sự kiện có thể tăng hoặc giảm do quy tắc không chồng sự kiện và thời điểm kích hoạt khác nhau.

| Khung | Họ | Chạm trong nến: sự kiện / TB | Chỉ giá đóng: sự kiện / TB |
|---|---|---:|---:|
| H1 | RSI | 891 / -1.0084 | 563 / 0.6377 |
| H1 | Z | 740 / -0.7926 | 493 / -1.9559 |
| H1 | RSI_AND_Z | 390 / -1.5860 | 200 / 0.1604 |
| H2 | RSI | 167 / -2.9266 | 66 / -8.4473 |
| H2 | Z | 470 / -1.6563 | 301 / -2.0275 |
| H2 | RSI_AND_Z | 185 / -4.5259 | 118 / -2.0998 |
| H4 | RSI | 293 / 2.6371 | 211 / 2.8893 |
| H4 | Z | 216 / -1.1677 | 135 / 1.1146 |
| H4 | RSI_AND_Z | 137 / 4.5200 | 64 / -1.3656 |
| M1 | RSI | 2465 / -0.2188 | 1916 / -0.1686 |
| M1 | Z | 1130 / -0.1975 | 731 / -0.3131 |
| M1 | RSI_AND_Z | 989 / -0.1605 | 556 / -0.1321 |
| M15 | RSI | 2333 / -0.6935 | 1723 / -0.3789 |
| M15 | Z | 1894 / -0.7662 | 1360 / -0.8037 |
| M15 | RSI_AND_Z | 1052 / -0.9948 | 618 / -1.1876 |
| M3 | RSI | 2357 / -0.4472 | 1801 / -0.3437 |
| M3 | Z | 1115 / -0.5203 | 766 / -0.3137 |
| M3 | RSI_AND_Z | 381 / -0.8096 | 199 / -1.7197 |
| M30 | RSI | 2338 / -0.4143 | 1742 / -0.7228 |
| M30 | Z | 1658 / -0.3941 | 1089 / -0.3680 |
| M30 | RSI_AND_Z | 890 / -1.0718 | 449 / -0.5590 |
| M5 | RSI | 1255 / -0.1895 | 599 / -0.7349 |
| M5 | Z | 1960 / -0.3179 | 1387 / -0.2731 |
| M5 | RSI_AND_Z | 1342 / -0.4345 | 752 / -0.3584 |

## Nguồn và khả năng tái lập

### Đối chứng toàn bộ chiến lược hiện tại

Chạy riêng `BacktestEngine` mặc định Direction M30 → Pullback M5 → Trigger M1, xác nhận nến đóng, trên 100.062 nến M1 từ 16/06/2026 đến 28/09/2026: 319 lệnh, 127 thắng / 192 thua, tỷ lệ thắng 39,81%, profit factor 0,8185, lợi nhuận ròng −788,45 trên vốn mô phỏng 10.000 (−7,88%), drawdown cao nhất 11,62%. Giả định spread cố định 35 point = 0,35 giá, phí mỗi lot bằng 0, chưa bổ sung trượt giá. Đây không phải kết quả chiến lược tick mới.

CSV M1 SHA-256: `6c451f8eb01bb470c58084204e498b91a050a4653c74d7645b84b3bdf4dacd61`. Profile SHA-256: `04d944ec567a78ec2b368a00cb9dc271172cf4a73ec42fc28fa2e1d693a9ffe9`.

Chạy lại bằng `scripts/analyze_rsi_z.py <archive> --point-size 0.01 --output <results>`; đối chứng chiến lược dùng `scripts/backtest_archived_candles.py <archive> --spread-points 35 --output <file.json>`. Bản đầy đủ gồm JSON của 720 phép thử ở `artifacts/rsi-z-calibration-unlimited/`; kết quả chiến lược ở `artifacts/rsi-z-calibration/canonical-baseline-backtest.json`.

### Tick thực và cài đặt mới

Đã replay 10.150 tick MT5 thực trong khoảng 30 phút. Profile mặc định chuyển sang quan sát intrabar tạo 0 signal trong đoạn ngắn đó; profile nghiên cứu Z ±2,5, hồi 0,3, các khung M1 và tắt MA tạo 3 signal BUY. Đây chỉ là kiểm tra luồng và quy tắc, không đủ đánh giá lợi nhuận. Đoạn cuối thiếu nến đóng tương ứng được giữ ở warm-up thay vì suy diễn dữ liệu.

Trong tab Chiến lược, bỏ chọn “Chỉ xác nhận khi nến đóng” để dùng cơ chế mới. Ví dụ SELL: chỉ cần một tick Z ≥ 2,5 để ghi nhận; trong nến đó giảm về 2,2 vẫn giữ dấu chạm, và chỉ từ nến Trigger kế tiếp mới xét mức hồi ít nhất 0,3 so với cực trị đã lưu. RSI dùng cùng nguyên tắc với delta RSI. Ngưỡng vẫn do profile đặt; chưa tự thay đổi ngưỡng theo thống kê. Xem [định nghĩa đầy đủ](INTRABAR_THRESHOLD_LATCH.md) về hết hạn, mất tick, khung Pullback/Trigger và kết hợp AND/OR.

Mỗi JSON theo khung chứa SHA-256 của CSV nguồn, mốc tách mẫu, đầy đủ 90 kết quả, các chi phí giả định và đối chiếu với cách chỉ lấy giá đóng.

[MetaQuotes CopyRates](https://www.mql5.com/en/docs/series/copyrates) mô tả giới hạn lịch sử; [CopyTicks](https://www.mql5.com/en/docs/series/copyticks) giải thích vì sao OnTick không đại diện mọi tick. [Bailey và cộng sự](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) trình bày rủi ro chọn tham số quá khớp dữ liệu.
