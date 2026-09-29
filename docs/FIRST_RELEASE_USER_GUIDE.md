# Hướng dẫn bản đầu tiên XAUPY 1.0 RC1

## Trước khi mở

Bản này có đường gửi lệnh thật qua MT5, không phải chỉ mô phỏng. Dùng tài khoản DEMO để nghiệm thu trước. Không thử REAL chỉ để xác minh một nút.

Giữ lại bản cũ và thư mục dữ liệu. Trong app cũ chọn **Dừng giao dịch**, lưu/sao lưu profile rồi dừng Engine và đóng app trước khi chạy bản mới trên cùng cổng. Bộ cài RC1 dùng thư mục chương trình riêng và không tự mở app, không bật AutoTrading, không sửa MT5. Dữ liệu người dùng vẫn nằm ngoài thư mục chương trình; gỡ cài đặt không xóa lịch sử. Tùy chọn khôi phục mode đã lưu là của người dùng: tắt tùy chọn này trước đổi bản khi chưa muốn tự khôi phục giao dịch.

Gói portable: giải nén trọn ZIP vào thư mục mới rồi mở `XAUPY.Desktop.exe`. Không chạy executable trực tiếp trong ZIP. Bộ cài: `XAUPY-1.0.0-rc1-Setup.exe`. Đây là bộ cài chưa ký số.

## Kết nối MT5

Dùng EA `mt5/XAUPY_Bridge_EA.ex5` **1.021** đi kèm chính gói. Dừng/gỡ EA của app cũ trên chart đó trước khi thay. Giữ EA khác không thuộc XAUPY nguyên trạng. Đặt `InpPort` bằng cổng trong Cài đặt (mặc định 39421), symbol và Magic khớp profile. Cho phép localhost theo hướng dẫn MT5; không đổi quyền mạng khác.

Python READY và EA kết nối chỉ xác nhận dữ liệu, không có nghĩa chế độ giao dịch đã bật. Để đặt lệnh, broker/MT5 cũng phải cho phép Algo Trading, và tài khoản/symbol đủ điều kiện. App sẽ nêu lý do đang chặn bằng tiếng Việt kèm mã trong tooltip/Nhật ký.

## Thử một thao tác DEMO

1. Xác minh nhãn **DEMO**, đúng account/server/symbol và lot/SL/TP trong Cấu hình.
2. Chọn **Thủ công**, xem và xác nhận danh tính. Không cần bật quyền REAL cho DEMO.
3. Nhập lot phù hợp. SL/TP để trống dùng profile; số nhập tay là **points**, không phải giá tuyệt đối. Không tự lấy con số ví dụ làm khuyến nghị giao dịch.
4. Tích **Xác nhận đặt lệnh** ngay trên BUY/SELL. Chỉnh lot/SL/TP sau đó sẽ bỏ xác nhận để anh kiểm lại.
5. Chỉ bấm một lần. **Đang xử lý** chưa phải đã khớp. Xem **Tiến trình lệnh** và ticket/retcode; đối chiếu tab Trade/History MT5. **UNKNOWN/Đang đối chiếu**: không gửi lại.
6. Sau nghiệm thu chọn Dừng; lưu kết quả và screenshot/nhật ký để đối chiếu.

`FRESH_QUOTE_REQUIRED` sau bản sửa vẫn là chặn hợp lệ khi không có tick đủ mới, packet sai clock hoặc tài khoản stale. Tooltip ghi tuổi giá, tuổi snapshot và nguồn giá. Không tăng ngưỡng hoặc bỏ guard để buộc gửi lệnh.

**Tự động** là quyền cho tín hiệu mới theo chiến lược, không tự bỏ xác nhận cho nút BUY/SELL bằng tay. Quyền REAL là phần độc lập; tick checkbox không tự đổi mode.

## Ma trận nghiệm thu thực tế sau tải

- Lệnh DEMO: BUY/SELL, pending tạo/sửa/hủy, đóng đơn/hàng loạt, BE, partial, trailing, TP động. Mỗi hành vi cần ticket và mức SL/TP thực tương ứng, không dùng một lệnh thành công để đánh dấu cả nhóm.
- Restart/reconnect: giữ stops tại broker; không gửi lại ý định UNKNOWN; kiểm ledger và trạng thái dữ liệu mới trước lệnh tiếp theo.
- Cấu hình/profile: lưu/nhập JSON và SET, startup default, nháp/xung đột. Import không cấp quyền REAL.
- Chart và báo cáo: 10 tab, scroll/zoom/fullscreen/PNG, so sánh, export dữ liệu đúng file/bộ lọc; thử tên đường dẫn tiếng Việt.
- Backtest/Optimizer: chọn dữ liệu thực, chạy/hủy, so sánh và xuất kết quả. Kết quả mô hình không phải cam kết có lời.
- Windows: đăng ký khởi động cùng Windows rồi kiểm ở lần đăng nhập do anh chủ động thực hiện; không cần đăng xuất ngay khi MT5 đang chạy.

Báo lỗi kèm phiên bản, SHA trong `build-manifest.json`, tab/hành động, mã lỗi và thời điểm; không gửi mật khẩu/token. Với lỗi lệnh, gửi intent ID/ticket và Journal/Experts đã che thông tin nhạy cảm.
