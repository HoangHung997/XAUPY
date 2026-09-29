# XAUPY 1.0.0-rc1 — bản đầu tiên sẵn sàng tải và nghiệm thu

Trạng thái: **READY_FOR_USER_TEST**. Task016 đã có bản đầy đủ, CI và bộ cài được xác minh; nghiệm thu MT5/broker, Windows thực tế và giao diện cuối cùng do người dùng thực hiện sau tải. Không đánh dấu DONE bằng cách dùng kiểm thử cách ly thay cho nghiệm thu thực tế.

## Danh tính bản phát hành

- Nhánh riêng: `release/1.0-completion-20260929`.
- Nguồn chương trình đã build: `a1abc91d9b2d43888a4471bd28c6b6f2e8af0e0f`.
- CI: [First release verification, run 36507058142](https://github.com/HoangHung997/XAUPY/actions/runs/36507058142), attempt 1; validate và windows đều SUCCESS.
- Desktop/Engine/config: **1.0.0-rc1**. EA: **1.021**.
- Các commit tài liệu/phát hành sau SHA trên không thay đổi executable đã xác minh. Tag `v1.0.0-rc1` phải trỏ chính SHA trên.
- Không merge hoặc sửa `main` / nhánh `work/desktop-completion-20260928`; không điều khiển MT5 hay thay profile/quyền giao dịch trên máy người dùng.

## Các phần hoàn thiện chính

1. Thống nhất giá mới và trạng thái thực thi: tick đúng phiên/tài khoản, đồng hồ packet, tuổi snapshot riêng; trạng thái cho vào lệnh và cho quản lý vị thế tách biệt. Giá mới không làm account snapshot cũ thành mới.
2. BUY/SELL: xác nhận nằm trên hai nút, gắn account/server/symbol/magic/profile đã xem; sửa lot/SL/TP hay đổi profile thì yêu cầu xác nhận lại. Không tự bỏ guard tài chính. Quyền REAL độc lập với OFF/MANUAL/AUTO.
3. Pending, STOP_CONFIRM, BE/partial/trailing/TP động: kiểm thời gian, giá/lot grid, stop/freeze, phí và ngân sách rủi ro; đối chiếu receipt/ticket/protection, không coi gửi thành công là đã khớp; batch rỗng/một phần không báo thành công giả.
4. Tiến trình lệnh: tra cứu đúng intent ID, phân trang ổn định, chi tiết và xuất JSON; không gửi lại UNKNOWN. Trạng thái chặn hiện tại tách lỗi lần trước.
5. Hoàn thiện luồng file/profile/báo cáo của mười tab: export cố định run/report/filter, chống phản hồi cũ ghi đè, ghi file tạm rồi thay đích; hủy/lỗi giữ file cũ. So preset là báo cáo đọc, không được áp nhầm vào profile.
6. Giữ đủ 172 mục trong `FIRST_RELEASE_FEATURE_MATRIX.csv`, phân biệt phạm vi kiểm cách ly và mục cần nghiệm thu sau giao hàng. Bộ cài chương trình riêng, không tự khởi chạy giao dịch; giữ hướng dẫn sao lưu và dừng bản cũ trước đổi bản.

## Kiểm thử đúng nguồn trên CI

- Linux: **502 Python tests PASS**, gồm bộ predicate dùng chung với EA được biên dịch C++; **163 IPC checks PASS**; Desktop Release 0 warnings / 0 errors.
- Windows: **502 Python tests PASS** (3 kiểm phụ thuộc compiler C++ Linux được skip, đã chạy ở job Linux); **163 IPC checks PASS**; **133/133 Desktop interaction assertions PASS**.
- Engine đóng gói: **161 RC1 execution protocol checks PASS**, chạy EA giả lập trên cổng ngẫu nhiên/kho tạm, không MT5/broker thật. Cùng toàn bộ regression packaged strategy/manual simulation/journal/backtest/optimizer/dynamic/maintenance/config/intrabar.
- MetaEditor: **0 errors, 0 warnings**, EA 1.021.
- Bộ cài Windows: cài im lặng vào thư mục CI riêng, kiểm **330 manifest file hashes**, gỡ thành công.
- Chụp đủ **10 trang control thực** của Desktop bằng fixture trên Windows. Scope: HEADLESS ISOLATED FIXTURE; không phải MT5 native hoặc chứng nhận pixel 100%.

## Xác minh tải về độc lập

- Artifact chương trình: `11007772889`, `XAUPY-1.0.0-rc1-win-x64`, **247917426 bytes**.
- Outer artifact SHA-256: `a76c03da67eaca2c331f5b4abef11a8a7c0647821f8e1b0cfc83e749beb5ad2f`.
- Portable ZIP: **123574809 bytes**, SHA-256 `0d77dc48610b1d9af826614ce19c326791235b97933202653dc0a84d1d10674e`.
- Setup EXE: **124535528 bytes**, SHA-256 `d64e0b5de41761b582628a639b43592f09b90a471efb9df8f09106005dba3523`.
- Đã kiểm **331 ZIP files / 330 manifest hashes**, CRC, path traversal, symlink, duplicate/case collision, đúng SHA nguồn/clean tree/tests, kiến trúc x64 của Desktop/Engine/config, EX5, compile log, 10 ảnh tham chiếu, 172 mục, baseline safety. Không có database người dùng hay toolchain tạm trong gói.
- Source artifact `11006884296` cũng được tải/đối chiếu; 65 file đã sửa khớp byte-for-byte nguồn kiểm tại máy. Source ZIP SHA-256 `c1a1ed9db5cca52f860d647d94bde497fa00e0070a8e798a0549ff123d6ad678`.
- UI evidence artifact `11007683198`, SHA-256 `7c144513edb5d83844c43505a8f953494cec23d59a06bc43803c0514ad87a32b`. Đã xem đủ mười ảnh; không thấy chồng/ẩn thao tác chính trong trạng thái fixture 1672×941. Nhãn/counter fixture không phải dữ liệu giao dịch của người dùng.

## Tải và chạy

Dùng `XAUPY-1.0.0-rc1-win-x64.zip` (giải nén đầy đủ, mở `XAUPY.Desktop.exe`) hoặc `XAUPY-1.0.0-rc1-Setup.exe`. Bộ cài chưa ký số. Đọc `FIRST_RELEASE_USER_GUIDE.md`: sao lưu, dừng giao dịch và Engine bản cũ, dùng đúng EA 1.021/cổng/symbol/magic. Dữ liệu người dùng nằm ngoài thư mục cài, không tự xóa. Dùng DEMO trước; không bật REAL để chỉ kiểm một nút.

Còn nghiệm thu sau tải: broker BUY/SELL/pending/close/BE/partial/trailing/TP động và reconnect với receipt thực; file picker/native Windows và phiên đăng nhập Windows mới; đối chiếu UI trên máy người dùng. Không cam kết có lợi nhuận, không tự gửi lệnh để lấp bằng chứng.
