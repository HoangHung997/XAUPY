# XAUPY 1.0 — hoàn thiện bản phát hành đầy đủ đầu tiên

Yêu cầu ngày 28/09/2026: hoàn thiện toàn bộ các mục Chưa có, Một phần, Mô phỏng và Chưa nghiệm thu OS của báo cáo chức năng. Đây là phạm vi phát triển tiếp, không phải chứng nhận đã hoàn tất.

## Quyết định sản phẩm thay thế giới hạn prototype

- Quyền giao dịch do người dùng chọn trong app: tắt, thủ công hoặc tự động; DEMO/REAL theo tài khoản thực và quyền người dùng lưu cho đúng danh tính tài khoản. Không còn khóa DEMO/REAL cứng trong sản phẩm.
- Nhập profile không tự cấp quyền giao dịch hoặc bật REAL. App thực hiện thiết lập đã áp dụng; trạng thái dừng do người dùng, không kết nối, dữ liệu cũ và broker từ chối được trình bày riêng.
- EA kiểm điều kiện broker, danh tính, symbol, magic, lot/step, margin, SL/TP; không dùng thành công của OrderSend làm bằng chứng đã khớp. Mọi ý định có ID bền vững, không gửi lại khi kết quả chưa rõ.
- Bản đang chạy 0.17.2 tiếp tục được giữ trong lúc phát triển. Dữ liệu/quyền một lệnh đã dùng của phiên cũ không bị reset; không tự kích hoạt giao dịch REAL trong nghiệm thu.
- Nút nghiên cứu chọn ứng viên theo dữ liệu, phí và kiểm ngoài mẫu; “không có ứng viên đạt” là kết quả hợp lệ. Không hứa tìm được tham số có lời.

## Trình tự triển khai và bằng chứng

1. Thực thi broker, vòng đời lệnh, quyền theo tài khoản, quản lý sau vào và đối chiếu khi reconnect/restart.
2. Dữ liệu đầy đủ: lịch sử, lịch tin, thống kê ngày, telemetry, phiên thị trường, ma trận đa khung.
3. Backtest tick/khung nến, nghiên cứu/so sánh/áp ứng viên, nối kho lịch sử.
4. Hoàn thiện các thao tác chart, profile, file, journal, settings và thông báo.
5. Đối chiếu 10 ảnh tham chiếu, kiểm từng mục trong ma trận nghiệm thu, CI Windows, bộ cài, hash/artifact, chạy kết nối thật trên đúng gói phát hành.

Danh sách theo dõi từng mục nằm ở `RELEASE_V1_FEATURE_MATRIX.csv`. Chỉ chuyển thành đạt khi có đường xử lý, kiểm hành vi và bằng chứng phù hợp. Các bài kiểm cách ly không thay thế giao dịch broker hoặc đăng nhập Windows thật. Mục phụ thuộc thao tác người dùng phải được ghi rõ, không tự đổi thành hoàn thành.

Tài liệu API: [MetaQuotes OrderSend](https://www.mql5.com/en/docs/trading/ordersend), [MqlTradeRequest](https://www.mql5.com/en/docs/constants/structures/mqltraderequest), [CalendarValueHistory](https://www.mql5.com/en/docs/calendar/calendarvaluehistory).

## Checkpoint 28/09, 17:30 — nghiệm thu gói, chưa chứng nhận bản chuẩn

- Đã triển khai các đường xử lý trong ma trận 172 mục. Trạng thái kiểm cách ly, dữ liệu live, thao tác native và broker được ghi riêng; không gộp chúng thành chứng nhận hoàn tất.
- Kiểm nguồn hiện tại: 466 Python, 151 hợp đồng IPC, 123 tương tác Desktop đạt. Bản đầy đủ đang đóng gói lại để chứa các sửa cuối; con số này chưa thay thế kiểm chính artifact mới.
- EA 1.020 đã chạy trên chart XAUPY H1 với gói mới, cổng thử 39451 và mode OFF. Bản cũ, EA khác và sổ quyền đã dùng được giữ riêng. Không gửi lệnh mới trong nghiệm thu.
- Nghiệm thu dữ liệu thực 18/18 đạt: tick mới, 9 khung nến đóng/đang hình thành, scanner 9 khung, 45/45 đối chiếu chỉ báo MT5/Python, lịch MT5 92 sự kiện, phiên broker, đồng hồ thị trường, ping, CPU/RAM/Disk, Journal/Experts và thống kê ngày. Bằng chứng: `artifacts/release-v1-live-services.json`.
- Các lỗi phát hiện trực tiếp đã sửa: khóa JSON terminal_data_path trùng làm rớt snapshot, D1 bị bỏ khi chiếu dữ liệu, giờ lịch sử lệch theo múi giờ Windows, lý do thoát chỉ hiện số, thiếu SL/TP trong giao dịch gần đây. Native MT5 History dùng để đối chiếu thời gian và mức giá.
- Nghiên cứu 9.898.349 tick/15 ngày hoàn tất. Không bộ nào đạt; báo cáo trong app, file JSON xuất từ UI và kết quả gốc trùng nhau. Chi tiết trong [báo cáo nghiên cứu](RESEARCH_20260928.md). Kết quả thuộc cấu hình đầu vào M1/M1/M1, không suy rộng cho cấu hình đang dùng M30/M5/M1.
- Xuất HTML Backtest và xuất/nhập ZIP trên giao diện đã chạy thành công. ZIP chứa 8 file, 9.859.191 byte nguồn; manifest/hash được kiểm, không tự áp profile/quyền. Các sửa tiếp theo bổ sung đầy đủ profile và giả định vào HTML, giữ nguyên evidence khi xuất JSON, thống nhất giờ dữ liệu/nhãn Tick và trục chart.
- Các sửa UI mới nhất: panel Công cụ có cuộn riêng khi mở lịch sử để không chồng thông tin; mô tả công cụ đổi theo lựa chọn; chỉ báo có tóm tắt số phép đối chiếu đạt. Cần xác nhận trên gói vừa build lại.
- Bộ cài Inno đã qua cài/gỡ ở thư mục riêng với 298 file khớp hash ở mốc trước. Bộ cài chứa sửa mới phải kiểm lại. Khóa Run Windows đã qua ghi/đọc/xóa giá trị thử riêng; chưa kiểm một phiên đăng nhập Windows mới.
- Runtime production có sự kiện đổi timeframe sang M30/M5/M1 lúc 17:01:21; không quy kết người thực hiện khi chưa có bằng chứng. Giữ cấu hình hiện tại. Hash runtime tại 17:28: `875a679593bc906af501bd834cdc7a45a4f28e4413d6843b9c498282d4662f65`; sổ quyền đã dùng: `4dd9956539b5cb1e0935ee57b2ec5c9e168f3ce778776e60bfe0149f32cbbf93`.

## Điều kiện còn lại trước bản phát hành chuẩn

1. Build đầy đủ từ nguồn đã lưu, CI Windows và kiểm installer mới; chạy lại gói đó với MT5.
2. Hoàn tất kiểm các thao tác native còn lại và đối chiếu mười ảnh mới với ảnh tham chiếu. Chưa chứng nhận UI giống 100%.
3. Executor chung đã có OrderSend thật và kiểm cách ly. Cần phiên nghiệm thu broker riêng cho các hành động mới: vào/đóng, sửa/hủy pending, BE/partial/trailing/TP động. Quyền một lệnh cũ đã dùng; không arm lại hoặc tự gửi thêm lệnh để lấp bằng chứng.
4. Xác nhận khởi động trong một phiên đăng nhập Windows mới khi người dùng thực hiện. Không tự đăng xuất máy đang chạy MT5.

Các mốc lịch sử trong tài liệu khác không được dùng để thay thế các điều kiện này. Danh sách hiện tại và bằng chứng từng mục nằm trong [ma trận nghiệm thu](RELEASE_V1_FEATURE_MATRIX.csv).
