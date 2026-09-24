# XAUPY UI Reference

Thư mục này lưu các ảnh mockup giao diện đã duyệt và được dùng làm **nguồn tham chiếu trực quan chính (UI source-of-truth)** khi triển khai XAUPY / N30 Control Center bằng Python.

## Mục tiêu

- Giữ một chuẩn bố cục thống nhất cho toàn bộ ứng dụng.
- Làm căn cứ để triển khai từng tab của Python Control Center.
- Dùng để đối chiếu khi review UI/UX, tránh mỗi lần sửa lại thiết kế từ đầu.
- Phân biệt rõ phần **giao diện tham chiếu** với phần **logic giao dịch thực tế**.
- Không coi số liệu giao dịch, lợi nhuận, giá, tài khoản, thời gian hay kết quả backtest xuất hiện trong ảnh là dữ liệu thật hoặc mục tiêu bắt buộc.

## Danh sách ảnh tham chiếu

| File | Tab / màn hình | Mục đích tham chiếu |
| --- | --- | --- |
| `Tab Tổng Quan.png` | Tổng quan | Màn hình chính: giá XAUUSD, trạng thái hệ thống, tài khoản, chart, chiến lược realtime, lệnh gần đây và log nhanh. |
| `Tab Cấu Hình.png` | Cấu hình | Trung tâm chỉnh toàn bộ tham số chiến lược, risk, timeframe, session, news, SL/TP và profile. |
| `Tab Chiến Lược.png` | Chiến lược | Trình bày logic Direction → Pullback → Trigger, các chỉ báo/điều kiện và trạng thái realtime của chiến lược. |
| `Tab Giám Sát.png` | Giám sát | Theo dõi chart, tín hiệu đa timeframe, indicator realtime, bridge/engine, session/news, cảnh báo và tài nguyên hệ thống. |
| `Tab Lệnh & Vị thế.png` | Lệnh & Vị thế | Quản lý vị thế đang mở, pending orders, lịch sử giao dịch, đóng lệnh, BE, trailing, partial close và thao tác thủ công. |
| `Tab BackTest.png` | Backtest | Cấu hình backtest, kết quả, equity curve, drawdown, danh sách giao dịch và lịch sử các lần chạy. |
| `Tab Tối Ưu.png` | Tối ưu | Parameter sweep, top setup, heatmap, walk-forward validation, tiến độ và tài nguyên tối ưu. |
| `Tab Nhật Kí.png` | Nhật ký | Log tập trung cho MT5, EA Bridge, Python Engine, Strategy, Orders, Alerts; hỗ trợ lọc, tìm kiếm và bookmark. |
| `Tab Công Cụ.png` | Công cụ | Các tiện ích vận hành: chỉnh config, so sánh preset, kiểm tra indicator, risk calculator, symbol/session, news, bridge diagnostic, import/export. |
| `Tab Cài Đặt.png` | Cài đặt | Kết nối MT5, bridge, đường dẫn dữ liệu, giao diện/ngôn ngữ, thông báo, giới hạn an toàn, backup và startup. |

## Quy tắc sử dụng khi triển khai

1. **Ưu tiên bố cục và luồng thao tác trong ảnh** khi xây UI thật.
2. Không cần sao chép từng pixel; có thể điều chỉnh spacing, font, kích thước control và responsive layout để phù hợp màn hình thật.
3. Các tab, nhóm chức năng, thứ tự thông tin và trạng thái chính nên giữ nhất quán với mockup nếu không có quyết định thiết kế mới.
4. Mọi số liệu trong ảnh chỉ là **dữ liệu minh hoạ**. Code phải lấy dữ liệu thật từ MT5 / EA Bridge / Python Engine.
5. Tên tham số, giá trị mặc định và logic chiến lược phải lấy từ spec/code/config hiện hành, không suy ngược từ con số minh hoạ trên ảnh.
6. Màu trạng thái nên giữ quy ước chung:
   - xanh lá: hoạt động / pass / lợi nhuận;
   - vàng/cam: chờ / cảnh báo;
   - đỏ: lỗi / rủi ro / lỗ;
   - xanh dương: thao tác chính / trạng thái trung tính.
7. UI phải phân biệt rõ:
   - **Direction TF**
   - **Pullback TF**
   - **Trigger TF**
   - trạng thái strategy engine
   - trạng thái MT5 / EA Bridge / Python Engine.
8. Những thao tác có rủi ro như đóng toàn bộ lệnh, bật live trading, thay đổi risk lớn hoặc reset cấu hình phải có xác nhận phù hợp.
9. Các màn hình Backtest/Tối ưu chỉ được hiển thị số liệu thật khi backend đã chạy xong; không hard-code kết quả minh hoạ.
10. Nếu triển khai thực tế khác mockup vì giới hạn kỹ thuật hoặc UX tốt hơn, phải ghi lại quyết định đó trong tài liệu thiết kế thay vì âm thầm lệch chuẩn.

## Phạm vi

Bộ ảnh này là chuẩn tham chiếu cho **desktop Python Control Center**. EA MQL5 phía MT5 có thể dùng giao diện đơn giản hơn vì vai trò chính của EA là bridge/execution/safety, còn Python là nơi chứa logic, cấu hình, giám sát, backtest và tối ưu.

## Ghi chú

- Thư mục này chỉ chứa tài liệu tham chiếu UI/UX.
- Không dùng ảnh làm bằng chứng hiệu suất chiến lược.
- Khi có mockup mới được duyệt, cập nhật ảnh và README này để giữ một nguồn tham chiếu duy nhất.
