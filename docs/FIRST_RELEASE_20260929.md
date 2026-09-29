# XAUPY 1.0 RC1 — nhánh hoàn thiện riêng, 29/09/2026

Nhánh: `release/1.0-completion-20260929`.
Nguồn tiếp quản: `335fcd3caba4a4375df3e5dd404006a42d5919e6` của `work/desktop-completion-20260928`.
Phạm vi: hoàn thiện chức năng, kiểm thử cách ly, gói Windows đầy đủ để người dùng tải và nghiệm thu thực tế.
Không sửa nhánh cũ hoặc ghi đè dữ liệu đang chạy. Không tự bật REAL/AUTO hoặc gửi lệnh broker để tạo bằng chứng.

## Thay đổi thực thi

- Giá thực thi lấy từ tick của đúng phiên EA/tài khoản; đồng hồ packet và tuổi snapshot riêng, tăng theo monotonic. Tick mới không bị so với server_time cũ; tick/heartbeat không làm dữ liệu tài khoản cũ trở thành mới.
- Gate vào lệnh, gate quản lý vị thế, lỗi lần trước và quyền REAL được tách riêng. Chặn vào lệnh do rủi ro ngày không tự chặn thao tác giảm rủi ro. Mất kết nối vô hiệu hóa ngay toàn bộ cờ có thể thực thi.
- Xác nhận BUY/SELL nằm trên hai nút. Sửa lot/SL/TP, đổi mode, tài khoản hoặc profile hủy xác nhận đã xem. Yêu cầu gắn danh tính và hash profile đã xác nhận; Backend kiểm lại. Không bỏ xác nhận tài chính.
- SL nhập tay không bị âm thầm thay đổi hoặc fallback khi số sai. Profile chỉ dùng khi ô trống. BUY/SELL tắt trong profile không còn để nút tương ứng hoạt động.
- STOP_CONFIRM dùng high/low của nến tín hiệu đã đóng hoặc cực trị tick đã quan sát tại thời điểm tín hiệu; không dùng nến tương lai. Hết hạn theo khung Trigger thực. Pending hủy khi hướng/setup/phiên hết hiệu lực.
- Ngân sách rủi ro tính cả ENTRY đang xếp hàng và phí dự phòng. FIXED_LOT không còn bị phần trăm rủi ro không hoạt động âm thầm khống chế. EA tự kiểm tiền rủi ro với OrderCalcProfit trước lần gửi duy nhất.
- Sửa pending không được tăng khoảng rủi ro; SL/TP, tick grid, Stops/Freeze, thời hạn được kiểm ở Python và EA. Thu hẹp SL do BE không bị bước trailing không hoạt động cản trở.
- Kết quả CONFIRMED phải có ticket đúng, cờ đã gửi và chứng cứ broker, lượng khớp và mức bảo vệ phù hợp. Trailing bật cục bộ không được gọi là broker đã khớp. Batch rỗng không báo thành công; batch một phần giữ kết quả từng thao tác.
- Tiến trình lệnh mới: đọc, phân trang ổn định và xuất JSON trạng thái; không có nút gửi lại các lệnh UNKNOWN. Poll theo đúng intent ID thay vì chỉ tìm trong 100 mục mới nhất.

## Thao tác file và giao diện

- Export cục bộ ghi file tạm cùng thư mục, flush rồi thay file đích nguyên tử. Hủy/lỗi không làm mất file cũ. SET qua công cụ cũng được stage trước khi thay file.
- Báo cáo so preset không giữ đường dẫn profile cũ; báo cáo chỉ đọc không thể áp thành profile. Giữ nháp và kiểm xung đột giữa các tab.
- Phân trang lịch sử chống phản hồi cũ ghi đè tài khoản/bộ lọc mới. Export cố định report và tài khoản; không trộn dữ liệu khi có thay đổi trong lúc tải.
- Xuất lịch sử broker có JSON đầy đủ hoặc CSV UTF-8, giữ phí vào/ra và bảo vệ comment khỏi công thức bảng tính.
- Mọi trang dùng control/handler thật. Trạng thái chờ dữ liệu hoặc bị broker chặn không bị thay thành kết quả giả.

## Bằng chứng và giới hạn

`FIRST_RELEASE_FEATURE_MATRIX.csv` giữ đủ 172 mục từ ma trận tiếp quản và phân loại lại phạm vi kiểm. Cột baseline là lịch sử, không phải trạng thái hiện tại.

Các kiểm thử Python, IPC, Desktop, predicate MQL biên dịch trên Linux và packaged synthetic-EA xác minh từng phạm vi. Synthetic EA chỉ là fixture trên cổng ngẫu nhiên và kho tạm; không chứng nhận broker đã khớp. 10 ảnh headless từ fixture dùng để kiểm bố cục và control, không được gọi là ảnh native MT5 hoặc chứng nhận pixel 100%.

CI Windows phải build clean source, MetaEditor 0 errors/0 warnings, chạy full regression/smoke, build bộ cài, cài vào thư mục tạm, kiểm hash và gỡ. Mọi artifact phải ghi SHA nguồn và manifest. Kết quả cuối theo workflow `First release verification` trên chính nhánh này; không tái sử dụng bằng chứng RC1/RC2 cũ.

Trạng thái mục tiêu khi gói đạt: **READY_FOR_USER_TEST**. Người dùng nghiệm thu broker, file picker/Windows thực, đăng nhập Windows mới và giao diện trên máy của mình sau khi tải. Không đóng Task016 thành DONE bằng cách biến bằng chứng cách ly thành bằng chứng thực tế.
