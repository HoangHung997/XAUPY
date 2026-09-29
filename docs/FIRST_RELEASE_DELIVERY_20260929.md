# XAUPY 1.0.0-rc1 — bản đầu tiên sẵn sàng tải và nghiệm thu

Trạng thái giao hàng: **READY_FOR_USER_TEST**. Đây là release candidate có chương trình đầy đủ, kiểm thử tự động, ZIP và bộ cài. Nghiệm thu MT5/broker, Windows thực tế và giao diện cuối cùng do người dùng thực hiện sau tải. Không dùng kiểm thử cách ly để chứng nhận DONE hoặc khớp UI 100%.

## Danh tính bản phát hành

- Nhánh riêng: `release/1.0-completion-20260929`.
- Nguồn chương trình đã build: `a1abc91d9b2d43888a4471bd28c6b6f2e8af0e0f`.
- CI: [First release verification, run 36507058142](https://github.com/HoangHung997/XAUPY/actions/runs/36507058142), attempt 1; validate và windows SUCCESS.
- Desktop/Engine/config: **1.0.0-rc1**. EA: **1.021**.
- Tag `v1.0.0-rc1` trỏ chính SHA ứng dụng trên. Commit tài liệu/phát hành sau đó không thay executable đã xác minh.
- Không merge hoặc sửa `main` / `work/desktop-completion-20260928`; không điều khiển MT5, đổi profile/quyền hoặc gửi lệnh trên máy người dùng.

## Phần hoàn thiện chính

1. Thống nhất giá mới và trạng thái thực thi: tick đúng phiên/tài khoản, đồng hồ packet, tuổi snapshot riêng. Gate vào lệnh và gate quản lý vị thế tách biệt. Tick mới không làm account snapshot cũ trở thành mới.
2. BUY/SELL: xác nhận nằm trên hai nút, gắn account/server/symbol/magic/profile đã xem; đổi lot/SL/TP hoặc profile thì yêu cầu xác nhận lại. Quyền REAL độc lập với OFF/MANUAL/AUTO; không bỏ guard tài chính.
3. Pending, STOP_CONFIRM, BE/partial/trailing/TP động: kiểm thời gian, giá/lot grid, stop/freeze, phí và ngân sách rủi ro. Kết quả broker đối chiếu receipt/ticket/protection; không coi gửi thành công là đã khớp. Batch rỗng/một phần không báo thành công giả.
4. Tiến trình lệnh: tra đúng intent ID, phân trang ổn định, xem chi tiết và xuất JSON; không gửi lại UNKNOWN. Trạng thái chặn hiện tại tách lỗi lần trước.
5. Luồng file/profile/báo cáo của mười tab: export cố định run/report/filter, chống phản hồi cũ ghi đè, ghi file tạm rồi thay đích; hủy/lỗi giữ file cũ. So preset là báo cáo đọc, không được áp nhầm thành profile.
6. Ma trận `FIRST_RELEASE_FEATURE_MATRIX.csv` giữ đủ 172 mục cùng phạm vi kiểm và mục cần nghiệm thu sau giao hàng. Bộ cài chương trình riêng, giữ dữ liệu ngoài thư mục cài, không tự khởi chạy app/giao dịch.

## Kiểm thử và phạm vi

- Kiểm tại máy cách ly: **502 Python tests, 163 IPC checks, 130 Desktop interaction assertions** đạt; **161 execution protocol checks** đạt với Engine và EA giả lập trên cổng ngẫu nhiên/kho tạm.
- CI Linux/Windows đã chạy lại kiểm thử, packaged regression, MetaEditor và bộ cài. Xem `CI_SUMMARY.txt` ở release để lấy các dòng tổng kết trực tiếp từ log đúng job. Các kiểm predicate phụ thuộc compiler C++ chạy ở Linux; skip trên Windows được giữ nguyên trong log, không tính là đã chạy.
- MetaEditor: **0 errors, 0 warnings**, EA 1.021; log compile đi cùng ZIP.
- Bộ cài Windows: cài vào thư mục CI riêng, kiểm tất cả file manifest và gỡ thành công.
- Đã xem mười ảnh control thực từ Windows headless với fixture 1672×941: không thấy chồng/ẩn thao tác chính trong những trạng thái đã chụp. Đây không phải dữ liệu MT5 của người dùng, không phải chứng nhận mọi viewport hoặc pixel 100%.

## Xác minh tải về độc lập — giá trị cuối cùng

Các giá trị dưới đây được tính trực tiếp từ artifact 11007772889 đã tải về. Lần xuất bản đầu đã dừng trước khi tạo release vì metadata checksum nhập sai; đã đối chiếu lại bytes, SHA256SUMS và manifest. Không đổi chương trình, không bỏ kiểm checksum.

- Artifact chương trình: `11007772889`, `XAUPY-1.0.0-rc1-win-x64`, **225647096 bytes**.
- Outer SHA-256: `a76c03da67eaca2c331f5b4abef11a8a7c0647821f8e1b0cfc83e749beb5ad2f`.
- Portable ZIP: **125267914 bytes**, SHA-256 `8c853c4145af5fc56dae8b18ded55360f927322cb98cd20f6cde12ffc1efed5d`.
- Setup EXE: **101113497 bytes**, SHA-256 `32330d13902d25f211344336dfa268c7433ca469d0b10f1489d372b95187e98f`.
- **305 ZIP files / 304 manifest hashes** đều khớp. Đã kiểm CRC, path traversal, symlink, duplicate/case collision, SHA nguồn/clean tree/tests, kiến trúc x64 Desktop/Engine/config, EX5, compile log, 10 ảnh tham chiếu, 172 mục và baseline safety. Không có database người dùng hoặc toolchain tạm trong gói.
- Source artifact `11006884296` được tải và đối chiếu: 65 file sửa khớp nguồn đã kiểm. Source ZIP SHA-256 `c1a1ed9db5cca52f860d647d94bde497fa00e0070a8e798a0549ff123d6ad678`.
- UI evidence artifact `11007683198`, SHA-256 `7c144513edb5d83844c43505a8f953494cec23d59a06bc43803c0514ad87a32b`. Scope: HEADLESS ISOLATED FIXTURE.

## Tải và chạy

Dùng `XAUPY-1.0.0-rc1-win-x64.zip` (giải nén đầy đủ, mở `XAUPY.Desktop.exe`) hoặc `XAUPY-1.0.0-rc1-Setup.exe`. Bộ cài chưa ký số.

Đọc `FIRST_RELEASE_USER_GUIDE.md`: sao lưu, dừng giao dịch và Engine bản cũ trước khi chạy bản mới; dùng đúng EA 1.021/cổng/symbol/magic. Dữ liệu người dùng không tự xóa. Nghiệm thu DEMO trước; không bật REAL chỉ để thử một nút.

Sau tải còn nghiệm thu broker BUY/SELL/pending/close/BE/partial/trailing/TP động và reconnect với receipt thực; file picker/native Windows, phiên đăng nhập Windows mới và UI trên máy người dùng. Không cam kết lợi nhuận, không tự gửi lệnh để tạo bằng chứng.
