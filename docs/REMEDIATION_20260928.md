# Sửa lỗi chức năng XAUPY — 28/09/2026

Đã sửa **7/7 mục mang trạng thái “Lỗi”** trong [báo cáo trước sửa](FEATURE_FUNCTION_AUDIT_20260928.md), bổ sung một số thao tác còn thiếu và triển khai bản **0.17.2-remediation**, EA **1.019** trên máy. Điều này không có nghĩa toàn bộ 172 chức năng đã hoàn tất. Báo cáo gốc được giữ nguyên làm bằng chứng trước sửa.

## Đối chiếu từng lỗi

| Mục | Bản sửa | Kiểm chứng và giới hạn |
| --- | --- | --- |
| UI-057 — tất cả symbol của vị thế | EA gửi thêm vị thế cùng magic trên mọi symbol; checkbox lọc ngay và đếm đúng dòng hiện ra. | Fixture nhiều symbol qua Bridge/Python/UI. Hành động trên symbol khác bị vô hiệu để không dùng metadata XAU cho tài sản khác; tổng rủi ro vẫn của symbol kết nối. EA 1.019 chạy thật, nhưng tài khoản hiện không có vị thế nhiều symbol để nghiệm thu broker đa tài sản. |
| UI-059 — symbol hiện tại ở lịch sử | Thêm tập deal cùng magic trên mọi symbol và nối checkbox. | Kiểm danh sách hỗn hợp, export giữ đúng bộ lọc. Snapshot vẫn giới hạn 50 deal thoát trong 7 ngày, không phải toàn lịch sử broker. |
| UI-082 — lý do DEMO bị cũ | Lý do cập nhật theo heartbeat; trạng thái cuối ưu tiên reason hiện tại, không để blocker cũ che lỗi. | Kiểm chuyển trạng thái, profile đổi, quyền đã dùng và kết nối cũ. App thật hiện BROKER_DEAL_CONFIRMED và quyền đã dùng. |
| UI-092 — bỏ qua costs trong Backtest | Replay và lập kế hoạch DEMO dùng chung spread, phí, dự phòng trượt giá, RR ròng và sizing theo rủi ro. | Regression siết ngưỡng rồi đối chiếu số lệnh/sizing. Commission đầu vào được trừ P/L; slippage là dự phòng trước vào, không giả làm trượt giá đã quan sát. |
| UI-095 — Backtest chặn cập nhật | Job nền, profile bất biến khi bắt đầu, desktop lấy tiến độ bằng yêu cầu ngắn. Đọc dataset qua kết nối riêng đã kiểm danh tính Engine. | Replay thật trên dataset 100.062 nến trong runtime cách ly: 20 heartbeat, chậm nhất 94,747 ms; hủy ở 17.024 nến, không lưu kết quả dở. Không phải SLA mọi máy hoặc phép đo tải broker production. |
| UI-138 — mất bản nháp Công cụ | Refresh tự động giữ nháp; thao tác bỏ nháp có xác nhận; server phát hiện active thay đổi đồng thời. | Kiểm UI và compare-and-swap backend. Ctrl+S/lưu nháp xuất file; nút Áp dụng mới đổi active. |
| UI-140 — Symbol sai | Đọc strategy.symbol, cập nhật khi nạp/áp profile. | Fixture EURUSD không còn hiện XAUUSD; app thật hiện XAUUSD đúng profile. |

## Các phần bổ sung

- UI-096: hủy Backtest thật; giữ kết quả lần trước khi hủy lần mới; hủy không đua với ghi kết quả hoàn tất.
- Optimizer: chu kỳ RSI/Z riêng cho pullback/trigger, ngưỡng Z hai phía và độ hồi Z; tôn trọng cờ bật chỉ báo, lưu/nạp đủ preset. SL ATR dùng multiplier; TP động dùng khoảng TP ban đầu. Các dải bổ sung dưới nút “Chu kỳ RSI / Z…” giữ bố cục chính.
- Lệnh & Vị thế: xuất JSON snapshot đang xem, đóng băng dữ liệu trước khi mở hộp lưu, ghi thời điểm/bộ lọc/phạm vi. Không phải xuất toàn lịch sử.
- Công cụ phân biệt lưu file với áp active và bảo vệ xung đột với Cấu hình/Chiến lược/Cấu hình nhanh.

## Kiểm tra và bản đang chạy

- **394 kiểm tra Python, 148 hợp đồng IPC, 100 tương tác UI đạt**. Các smoke gói Engine, cấu hình, lệnh mô phỏng, backtest, optimizer, quản lý mô phỏng, bảo trì, intrabar, DEMO một lần đều đạt trong môi trường cách ly.
- EA biên dịch **0 lỗi, 0 cảnh báo**, nạp trên XAUPY XAUUSD,M30. Journal xác nhận Bridge **1.019** lúc 11:04:47 giờ Việt Nam. EA khác không thay đổi.
- Bản chạy `dist/XAUPY-verified-remediation-win-x64`; desktop/Python **0.17.2-remediation**. Bố cục cuối đã publish và chạy lại 100 kiểm tra UI.
- Chụp đủ 10 tab tại `artifacts/remediation-final-captures`; xem trực tiếp Backtest, Optimizer, Lệnh, Công cụ. Không chứng nhận giống ảnh 100%; [các khoảng trống parity](UI_REFERENCE_PARITY_AUDIT.md) còn mở.
- Profile giữ nguyên, hash `1e8eb3d4fb26b318ac28b1af0390e5fe8ba91f68775bb8a5ae4a96286db2c92e`. DEMO vẫn FILLED, quyền đã dùng; không arm/đặt/sửa/đóng lệnh mới trong lần sửa.
- Dùng **100.062 nến M1**, replay **10.150 tick**: [kết quả tham số](PARAMETER_RESEARCH_20260928.md). Chưa có bộ đạt tiêu chí lợi nhuận sau phí qua các giai đoạn; không áp ứng viên thất bại vào app.

Bằng chứng cục bộ: `artifacts/remediation-build.log`, `remediation-layout-tests.log`, `remediation-nonblocking-probe.json`, `remediation-ea1019-status.json`, `remediation-final-status.json`, thư mục `parameter-remediation-20260928` và ảnh native nói trên. Snapshot chỉ xác nhận thời điểm kiểm tra, không thay thế giám sát liên tục.

## Phần chưa hoàn tất

Các mục “Chưa có”, “Một phần”, “Mô phỏng” không tự chuyển thành đã làm. Đặc biệt còn executor chung/REAL theo quyền người dùng; quản lý vị thế broker sau vào (BE, trailing, partial, TP động); P/L intrabar từ tick; đóng trước cuối tuần; consumer comment; lịch tin; thống kê ngày; duyệt/xuất lịch sử đầy đủ; các công cụ/pending/so sánh chưa có. Bản này vẫn có đường DEMO một lần và các thao tác lệnh mô phỏng theo phạm vi đã công bố. Đây là thiếu chức năng sản phẩm cần làm tiếp, không phải tùy chọn REAL đã mở thành công.
