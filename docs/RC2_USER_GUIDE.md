# XAUPY 1.0 RC2 — chuyển bản và kiểm tra trên máy thật

## Bản dùng

- Desktop/Engine/config: **1.0.0-rc2**.
- EA: **XAUPY_Bridge_EA 1.022** trong thư mục `mt5` của gói RC2.
- `build-manifest.json` chứa SHA nguồn và hash các file. Dùng đúng gói của cùng
  một lần build; không ghép Engine/EA cũ với Desktop mới.
- Đây là release candidate sau sửa lỗi, không phải chứng nhận giao dịch REAL,
  lợi nhuận, mọi broker hoặc giao diện pixel-perfect 100%.

## Trước khi mở RC2

1. Chọn **Dừng giao dịch** trong Lệnh & Vị thế của bản cũ. Kiểm tra MT5 và xử lý
   các vị thế/lệnh chờ theo quyết định của anh; Dừng không tự đóng lệnh ở broker.
2. Sao lưu dữ liệu, rồi dừng Engine và đóng app cũ. Không chạy đồng thời hai
   bản trên cùng cổng/kho dữ liệu. Dữ liệu không tự xóa khi cài/gỡ ứng dụng.
3. Giải nén ZIP đầy đủ vào thư mục mới, hoặc dùng Setup RC2. Setup dùng thư mục
   riêng và không tự chạy app. Bộ cài chưa ký số.
4. Thay EA bằng file **1.022** đi kèm; kiểm InpPort/symbol/magic khớp app. Đừng
   giữ EA1.021 khi đã thay EngineRC2: capability thiếu sẽ bị chặn an toàn.
5. Mở đúng `XAUPY.Desktop.exe`, kiểm phiên bản và trạng thái trong Cài đặt.
   Các lựa chọn startup đã được anh lưu trước đó có thể được nạp; vì vậy phải
   dừng bản cũ và kiểm trạng thái tài khoản/chế độ trước khi thử chức năng.

## Thử luồng đặt lệnh trên DEMO

Dùng tài khoản DEMO để nghiệm thu trước, không bật REAL chỉ để thử nút.
Kiểm symbol, server, account, magic, lot/SL/TP và chế độ Thủ công. Tích ô xác
nhận ngay phía trên BUY/SELL; đổi biểu mẫu/profile sẽ yêu cầu xác nhận lại.
Nếu nút bị khóa, đọc lý do hiện tại. Không bỏ guard giá mới, quyền AlgoTrading,
lot tối thiểu, mức SL hoặc netting để làm nút chạy được.

Mỗi thao tác có intent trong **Tiến trình lệnh**. Chờ trạng thái và đối chiếu
MT5 order/deal/position. QUEUED/DISPATCHED không có nghĩa đã khớp. UNKNOWN phải
được đối chiếu, không bấm lặp để gửi lại một yêu cầu chưa rõ kết quả.

Các thao tác hàng loạt chỉ thuộc symbol đang kết nối + magic, dù bảng đang xem
mọi symbol XAUPY. Kiểu pending cần expiry được broker hỗ trợ. Tài khoản netting
đã có vị thế cùng symbol không được gộp thêm một cách âm thầm.

## Kiểm tra hai lỗi RC1 đã sửa

**Lot nhỏ + partial + BE:** khi lượng đóng một phần không đạt bước/tối thiểu,
app báo bỏ qua partial nhưng vẫn đánh giá BE/trailing/TP động. Không tự nâng lot
hoặc đóng toàn bộ. Giữ đối chiếu các điều kiện/SL thực trên MT5.

**Khôi phục backup:** sao lưu không đồng nghĩa cấp quyền giao dịch. RC2 hiển thị
preview trước/sau, bảo vệ các bản nháp; cần xác nhận riêng. Backup không tăng
REAL; khôi phục đưa giao dịch về OFF và tắt tự chạy giao dịch khi khởi động.
Để giao dịch lại, xem lại cấu hình/account rồi chủ động chọn chế độ. Dữ liệu
UNKNOWN hoặc đã gửi broker không bị xóa bởi khôi phục profile.

## UI và tiện ích

Drawdown có hai đơn vị %/tiền. Preset optimizer được kiểm đầy đủ trước khi nạp;
file khác cấu trúc phạm vi UI bị từ chối thay vì nạp một phần. Biểu đồ hỗ trợ
CSV/JSON có metadata hợp lệ; so tài sản qua file không phải đăng ký giá live
cho symbol khác. Ô account/path chỉ đọc; nút folder mở nơi lưu, không di chuyển
kho dữ liệu. Ở cửa sổ nhỏ, dùng thanh cuộn để tới lịch sử và vùng nhập lệnh.

## Gửi lỗi kèm bằng chứng

Ghi phiên bản/SHA trong manifest, tab+nút, trạng thái trước/sau, mã lỗi, giờ,
account DEMO/server/symbol/magic (che thông tin cần giữ riêng), intentID và
ảnh MT5 đối chiếu. Xuất JSON tiến trình lệnh/nhật ký khi cần. Không gửi mật khẩu
MT5 hoặc quyền truy cập máy chỉ để báo lỗi.

Ảnh so sánh demo/control, bản đồ action-handler và kết quả CI được giao riêng
trong gói evidence. Chụp headless không thay thế kiểm giao diện/file picker
Windows thực hoặc xác nhận 100% giống demo. Native broker acceptance vẫn mở.
