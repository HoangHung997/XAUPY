# Kiểm tra chức năng XAUPY — 28/09/2026

**Kết luận: app chưa hoàn tất chức năng theo những gì giao diện/demo gợi ý.** Có phần chạy thật, phần mô phỏng, phần chỉ lưu tham số, nút chưa triển khai và lỗi có thể tái hiện. Không được dùng việc build/test xanh để kết luận toàn bộ app hoạt động đầy đủ.

Rà soát đủ 10 tab, thêm nhóm biểu đồ dùng chung: **172 mục chức năng**, **133 thông số cấu hình**, đối chiếu **259 khai báo nút/ô nhập trong AXAML**. Ô tạo động trong Cấu hình/Chiến lược và thao tác chart/hàng bảng được xét ở các nhóm tương ứng; 259 khai báo không phải 259 tính năng độc lập. Nguồn kiểm: `11d047f3a8d5` (mã runtime `4a51b28`), bản chạy `XAUPY-verified-tickui-final-win-x64`, EA 1.018.

## Bằng chứng chạy thực và phạm vi

- **Đường vào một lệnh DEMO đã chạy thật.** Lần kiểm tra chỉ đọc xác nhận BUY XAUUSD 0,01 lot, giá 4205,97; SL 4204,90, TP 4212,69. Broker đã đóng tại SL, P/L −1,07 USD (phí/swap trong các deal được đọc bằng 0). Ticket được lưu ở bằng chứng MT5 cục bộ. Quyền đã dùng, không còn vị thế của lệnh đó khi kiểm tra. Đây là một lần vào lệnh có xác nhận broker, không chứng minh hiệu quả chiến lược hoặc toàn bộ quản lý lệnh hoạt động.
- **02:00 đã vào profile đang dùng:** `sessions.session1_start=02:00`, timezone `BROKER`, hash `1e8eb3d4…`. Quyền mới do thao tác người dùng trong app đã gắn hash đó; lần audit không arm, không đặt/đóng/sửa lệnh và không đổi profile.
- Bộ hiện có: **386 kiểm tra Python + 148 kiểm tra hợp đồng IPC + 84 kiểm tra tương tác UI cách ly đều đạt**. Một số bài là kiểm cấu trúc nguồn; không phải 618 thao tác người dùng được bấm trên máy thật.
- Thêm **6 phép tái hiện UI** và **6 phép kiểm backend** trong môi trường cách ly. Các kết quả `reproduced=true` là xác nhận lỗi/giới hạn mô tả, **không phải** chứng nhận tính năng đạt yêu cầu.
- Không kiểm đăng nhập Windows mới, mọi hộp thoại hệ điều hành trên máy thật, mọi tổ hợp của 133 tham số, REAL execution hoặc giao diện ở mọi độ phân giải. Không chứng nhận UI giống ảnh 100%; [hồ sơ parity](UI_REFERENCE_PARITY_AUDIT.md) vẫn ghi các khác biệt.
- Mã nguồn sản phẩm, bản chạy và cấu hình giao dịch được giữ nguyên trong lần audit; chỉ thêm hồ sơ kiểm tra và chạy test cách ly.

## Các việc cần sửa theo ưu tiên

| Mức | Phát hiện | Tác động / điều kiện nghiệm thu |
| --- | --- | --- |
| P1 | Backtest giữ luồng xử lý IPC chung | Replay 3.000 nến giữ luồng 1,6117 s; timer 10 ms bị chậm thành 1,6118 s. Tách job và kênh xử lý; chứng minh tick/heartbeat vẫn chạy và có hủy backtest. Chưa đo độ trễ production vì không chạy thử chặn app đang hoạt động. |
| P1 | Backtest bỏ qua bốn giới hạn costs trong profile | Phép B06 siết trần spread=0, commission=0, min net RR=100 vẫn cho cùng trade và metrics. Cần dùng cùng quy tắc entry với executor; phân biệt phí đầu vào P/L với điều kiện lọc trước vào lệnh. |
| P1 | Người dùng bật BE/trailing/partial nhưng broker chưa có quản lý sau vào | Guard vẫn nhận profile có cờ bật. Phải triển khai executor quản lý vị thế và kiểm SL không bị nới, volume/step/partial đúng; hoặc UI phải nói rõ phạm vi mô phỏng. |
| P1 | DEMO/REAL và chạy theo thiết lập người dùng chưa có executor đầy đủ | Schema còn khóa DEMO, REAL=false; chỉ một lệnh DEMO. Cần kiến trúc thực thi/lifecycle theo quyền người dùng, không thể giải quyết bằng chỉ đổi checkbox. |
| P1 | Profile intrabar không dùng được với Backtest/Optimizer OHLC | Cần replay dữ liệu tick đúng thứ tự. Không được thay bằng nến đóng rồi gọi đó là cùng chiến lược. |
| P1 | Công cụ có thể làm mất bản nháp, không tham gia bảo vệ xung đột chung | Reload/đổi công cụ ghi đè; Ctrl+S áp active. Nghiệm thu giữ nháp, phát hiện thay đổi đồng thời, phân biệt lưu file/áp vào app. |
| P2 | Tham số đóng trước cuối tuần và comment không có tác dụng | Thêm consumer/test hành vi; chặn cấu hình chưa hỗ trợ hoặc nói rõ trạng thái. |
| P2 | Bộ lọc symbol giả; Symbol trong Công cụ đọc sai nhánh JSON | Kiểm danh sách nhiều symbol, lọc cả Bridge/UI đúng, hiển thị strategy.symbol. |
| P2 | Dòng lý do DEMO cũ còn lại khi đổi trạng thái | Đồng bộ trạng thái, reason, blocker và thời điểm; lỗi PROFILE_CHANGED không bị che bởi SESSION_TIME_BLOCKED cũ. |
| P2 | Các thao tác BUY/SELL/đóng/sửa/hủy còn mô phỏng; nút báo cáo/pending/default/compare chưa có | Hoàn thiện từng đường xử lý và đối chiếu broker; không tính simulator là broker execution. |
| P2 | Tối ưu còn thiếu tham số Z/RSI, ATR/dynamic TP bị vô hiệu trên UI | Nối UI với khả năng backend, thêm replay tick trước khi tìm bộ tham số cho chiến lược intrabar. |
| P2 | Cài đường dẫn MT5 chỉ lưu, lịch tin/telemetry/chỉ số ngày chưa nối | Cần nguồn dữ liệu hoặc hành động thực tương ứng với từng nhãn. |
| P3 | Giới hạn chart 64/180 nến, Journal 500 dòng, deal 50/7 ngày và các nhãn còn lệch nghĩa | Hiển thị phạm vi rõ, thêm phân trang/xuất đủ; không tuyên bố đã đọc/hiển thị toàn bộ. |

P1: ảnh hưởng độ tin cậy dữ liệu, thiết lập hoặc chức năng giao dịch cốt lõi. P2: thiếu chức năng/sai hành vi. P3: khả năng quan sát và cách diễn đạt.

## Cách đọc danh sách

**Đã triển khai** = có đường xử lý thật trong phạm vi được ghi, không có nghĩa đã kiểm mọi tình huống. **Một phần** = có xử lý nhưng hẹp hơn nhãn/yêu cầu. **Mô phỏng** = không thay đổi broker. **Chưa có** = thiếu chức năng. **Lỗi** = sai hành vi đã kiểm mã hoặc tái hiện. **Chưa nghiệm thu OS** = có mã nhưng cần kiểm hệ điều hành riêng.

Tổng hợp: Đã triển khai: 83, Chưa có: 24, Một phần: 40, Lỗi: 7, Mô phỏng: 17, Chưa nghiệm thu OS: 1. Đây là đếm mục chức năng để theo dõi, không phải phần trăm hoàn thiện sản phẩm.

## Danh sách từng chức năng


### Tổng quan

| Mã | Chức năng | Trạng thái | Kết luận / giới hạn | Bằng chứng |
| --- | --- | --- | --- | --- |
| UI-001 | Thu nhỏ, phóng to, đóng cửa sổ | **Đã triển khai** | Có xử lý cửa sổ native. | Mã; [nguồn](../src/XAUPY.Desktop/MainWindow.axaml.cs) |
| UI-002 | Điều hướng đủ 10 tab | **Đã triển khai** | Các tab thật được tạo và gắn với Engine. | Mã + 84 kiểm tra UI; [nguồn](../src/XAUPY.Desktop/MainWindow.axaml.cs) |
| UI-003 | Bắt đầu / dừng Python Engine | **Đã triển khai** | Khởi động, kết nối, dừng tiến trình Engine. Nút này không phải bật/tắt giao dịch tự động chung. | Mã + kiểm tra cách ly; [nguồn](../src/XAUPY.Desktop/MainWindow.axaml.cs) |
| UI-004 | Bid, Ask, spread, thời điểm giá | **Đã triển khai** | Dùng tick thật; có phân biệt giá gần nhất với trạng thái kết nối. | Mã + luồng đang chạy; [nguồn](../src/XAUPY.Desktop/MainWindow.axaml.cs) |
| UI-005 | Balance, equity, free margin, loại tài khoản | **Đã triển khai** | Đọc từ MT5 Bridge, không phải số mẫu trong ảnh. | Mã + luồng đang chạy; [nguồn](../src/XAUPY.Desktop/MainWindow.axaml.cs) |
| UI-006 | Lợi nhuận hôm nay | **Chưa có** | DailyProfitValue còn là dấu —, chưa cập nhật dù tab Lệnh có dữ liệu P/L. | Mã; [nguồn](../src/XAUPY.Desktop/MainWindow.axaml) |
| UI-007 | Số lệnh hôm nay | **Chưa có** | DailyTradeCountValue còn là dấu —. | Mã; [nguồn](../src/XAUPY.Desktop/MainWindow.axaml) |
| UI-008 | Drawdown lớn nhất hôm nay | **Chưa có** | DailyDrawdownValue còn là dấu —; chưa có bộ tính DD ngày tại sidebar. | Mã; [nguồn](../src/XAUPY.Desktop/MainWindow.axaml) |
| UI-009 | Đếm vị thế / lệnh chờ | **Đã triển khai** | Đếm snapshot thuộc symbol + magic của EA, không đại diện mọi EA trong tài khoản. | Mã; [nguồn](../src/XAUPY.Desktop/MainWindow.axaml.cs) |
| UI-010 | Danh sách lệnh gần đây | **Một phần** | Chỉ thông báo số position/order và hướng dẫn sang tab Lệnh; chưa có bảng lịch sử như demo. | Mã; [nguồn](../src/XAUPY.Desktop/MainWindow.axaml.cs) |
| UI-011 | Đồng hồ, account, leverage ở chân trang | **Đã triển khai** | Đồng hồ ghi Giờ máy; account/leverage từ Bridge. Không nhầm tên biến FooterServerTime với chức năng UI. | Mã; [nguồn](../src/XAUPY.Desktop/MainWindow.axaml.cs) |
| UI-012 | 3 timeframe nhanh | **Đã triển khai** | Direction/Pullback/Trigger đọc active, giữ bản nháp, áp dụng có kiểm xung đột. | Mã + UI cách ly; [nguồn](../src/XAUPY.Desktop/MainWindow.QuickConfiguration.cs) |
| UI-013 | Logic AND/OR nhanh và cho phép BUY/SELL | **Đã triển khai** | Sửa giá trị thực trong profile, không phải công tắc giả. | Mã + UI cách ly; [nguồn](../src/XAUPY.Desktop/MainWindow.QuickConfiguration.cs) |
| UI-014 | Áp dụng cấu hình nhanh | **Đã triển khai** | Chỉ vá giá trị đã sửa; kiểm bản nháp/xung đột với Cấu hình và Chiến lược. | Mã + UI cách ly; [nguồn](../src/XAUPY.Desktop/MainWindow.QuickConfiguration.cs) |
| UI-015 | Các lối tắt cài đặt, preset, 12 nhóm tham số | **Đã triển khai** | Đi đến trình cấu hình và nhóm tương ứng; không phải kho preset riêng. | Mã + UI cách ly; [nguồn](../src/XAUPY.Desktop/MainWindow.QuickConfiguration.cs) |
| UI-016 | Mở/lưu preset, JSON, SET ở lối tắt | **Đã triển khai** | Dùng các thao tác file của trình Cấu hình. | Mã + UI cách ly; [nguồn](../src/XAUPY.Desktop/MainWindow.QuickConfiguration.cs) |
| UI-017 | Hướng dẫn và log nhanh | **Một phần** | Có nội dung và log thật; một số thông báo khóa giao dịch tổng quát chưa diễn đạt rõ ngoại lệ DEMO một lệnh. | Mã; [nguồn](../src/XAUPY.Desktop/MainWindow.axaml.cs) |

### Biểu đồ dùng chung

| Mã | Chức năng | Trạng thái | Kết luận / giới hạn | Bằng chứng |
| --- | --- | --- | --- | --- |
| UI-018 | Nến, giá đóng, volume | **Đã triển khai** | Vẽ dữ liệu Bridge và nến đang hình thành riêng; không dùng nến giả để giống ảnh. | Mã + kiểm tra biểu đồ; [nguồn](../src/XAUPY.Desktop/MarketChartControl.cs) |
| UI-019 | Chọn timeframe bằng chuột / bàn phím | **Đã triển khai** | Đã gắn sự kiện động, dù AXAML không có Click trực tiếp. | Mã + kiểm tra biểu đồ; [nguồn](../src/XAUPY.Desktop/MarketChartControl.cs) |
| UI-020 | Nến Nhật / đường giá | **Đã triển khai** | Đổi kiểu biểu đồ, giữ lựa chọn khi có snapshot mới. | Mã + kiểm tra biểu đồ; [nguồn](../src/XAUPY.Desktop/MarketChartControl.cs) |
| UI-021 | Chỉ báo EMA | **Một phần** | Bật/tắt bộ EMA 10/20/50 cố định; chưa là thư viện chỉ báo tùy chỉnh. | Mã + kiểm tra biểu đồ; [nguồn](../src/XAUPY.Desktop/MarketChartControl.cs) |
| UI-022 | So sánh | **Một phần** | So sánh timeframe khác của cùng symbol, chuẩn hóa giá; chưa so nhiều tài sản. | Mã + kiểm tra biểu đồ; [nguồn](../src/XAUPY.Desktop/MarketChartControl.cs) |
| UI-023 | Xem toàn bộ lịch sử / zoom / pan | **Một phần** | Giữ tối đa 180 nến mỗi timeframe, vẽ 64 nến cuối; chưa có trình duyệt toàn bộ kho nến. | Mã; [nguồn](../src/XAUPY.Desktop/MarketChartControl.cs) |
| UI-024 | Chụp ảnh / fullscreen như hình demo | **Chưa có** | Chưa có thao tác tương ứng trên thanh công cụ chart. | Mã + hồ sơ parity; [nguồn](../src/XAUPY.Desktop/MarketChartControl.cs) |
| UI-025 | Hiển thị giá, RSI, Z theo tick | **Đã triển khai** | Đọc tick quan sát; EA gom khoảng 250 ms, app lấy cập nhật nhẹ khoảng 200 ms. Không vẽ riêng từng tick. | Mã + tick đang chạy; [nguồn](../src/XAUPY.Desktop/MainWindow.axaml.cs) |

### Cấu hình

| Mã | Chức năng | Trạng thái | Kết luận / giới hạn | Bằng chứng |
| --- | --- | --- | --- | --- |
| UI-026 | Sinh đủ 133 ô tham số | **Đã triển khai** | Schema sinh trường, kiểu, miền giá trị và trạng thái khóa; xem phụ lục riêng từng trường. | 133 ô được nạp qua IPC cách ly; [nguồn](../src/XAUPY.Desktop/ConfigurationEditor.axaml.cs) |
| UI-027 | Điều hướng nhóm / tìm kiếm | **Đã triển khai** | Nhảy đến nhóm và lọc tham số thật. | Mã + UI cách ly; [nguồn](../src/XAUPY.Desktop/ConfigurationEditor.axaml.cs) |
| UI-028 | MTF Pullback / MTF Trigger | **Một phần** | Đi đến thiết lập timeframe của một vai trò; chưa là nhiều điều kiện Pullback/Trigger đồng thời trên mọi khung. | Mã; [nguồn](../src/XAUPY.Desktop/ConfigurationEditor.axaml.cs) |
| UI-029 | Kiểm tra lại / báo lỗi tham số | **Đã triển khai** | Backend kiểm kiểu, giới hạn, ràng buộc chéo, trường khóa; chưa đồng nghĩa mọi chế độ hợp lệ đều thực thi được. | Mã + bộ kiểm cấu hình; [nguồn](../src/XAUPY.Desktop/ConfigurationEditor.axaml.cs) |
| UI-030 | Nhập JSON | **Đã triển khai** | Đọc và kiểm profile vào bản nháp, chưa đổi active trước khi Áp dụng. | Mã + UI cách ly; [nguồn](../src/XAUPY.Desktop/ConfigurationEditor.axaml.cs) |
| UI-031 | Lưu JSON / Lưu thành | **Một phần** | Cả hai mở hộp lưu file; chưa có hành vi ghi lại file hiện tại riêng. | Mã; [nguồn](../src/XAUPY.Desktop/ConfigurationEditor.axaml.cs) |
| UI-032 | Nhập / xuất SET | **Đã triển khai** | Codec SET, alias và kiểm cấu hình đã có. Không phải thao tác tự thay Inputs của EA đang gắn trên MT5. | Mã + kiểm codec; [nguồn](../src/XAUPY.Desktop/ConfigurationEditor.axaml.cs) |
| UI-033 | Mặc định / Hoàn tác | **Đã triển khai** | Nạp mặc định vào bản nháp hoặc tải active trở lại. | Mã + UI cách ly; [nguồn](../src/XAUPY.Desktop/ConfigurationEditor.axaml.cs) |
| UI-034 | Áp dụng / lưu bền / phục hồi sau restart | **Đã triển khai** | Profile chuẩn được lưu; đổi profile làm quyền DEMO đang chờ thành SUSPENDED để ràng buộc lại cấu hình. | Mã + API cách ly; [nguồn](../src/XAUPY.Desktop/ConfigurationEditor.axaml.cs) |
| UI-035 | Đóng trước cuối tuần | **Chưa có** | Có hai tham số nhận/lưu được nhưng không có nơi thực thi trong Python hoặc EA. | Quét consumer + B03; [nguồn](../python/xaupy_engine/config_schema.py) |
| UI-036 | Order comment tùy chỉnh | **Chưa có** | Giá trị lưu được; lệnh DEMO thực tế dùng comment X1:attempt, không đọc execution.order_comment. | Mã + deal MT5; [nguồn](../python/xaupy_engine/config_schema.py) |

### Chiến lược

| Mã | Chức năng | Trạng thái | Kết luận / giới hạn | Bằng chứng |
| --- | --- | --- | --- | --- |
| UI-037 | Sửa khung thời gian / chỉ báo / bộ lọc / SL-TP | **Đã triển khai** | Các ô tạo động sửa profile thật; phần mở rộng giữ các tùy chọn còn lại. | Mã + UI cách ly; [nguồn](../src/XAUPY.Desktop/StrategyDashboard.Editor.cs) |
| UI-038 | Áp dụng / Tải lại / bảo toàn bản nháp | **Đã triển khai** | Giữ thay đổi qua heartbeat và chặn xung đột với Cấu hình/Tổng quan. | Mã + UI cách ly; [nguồn](../src/XAUPY.Desktop/StrategyDashboard.Editor.cs) |
| UI-039 | Lưu chiến lược / Xuất cấu hình | **Một phần** | Xuất active profile; không xuất những sửa đổi chưa áp dụng trong bản nháp trên tab. | Mã; [nguồn](../src/XAUPY.Desktop/StrategyDashboard.axaml.cs) |
| UI-040 | Tải chiến lược JSON | **Đã triển khai** | Kiểm schema, hiện tóm tắt và xác nhận trước khi áp dụng. | Mã; [nguồn](../src/XAUPY.Desktop/StrategyDashboard.axaml.cs) |
| UI-041 | Đặt làm mặc định | **Chưa có** | Nút đang bị vô hiệu hóa; chưa có thao tác mặc định riêng. | Mã; [nguồn](../src/XAUPY.Desktop/StrategyDashboard.axaml) |
| UI-042 | Direction → Pullback → Trigger | **Đã triển khai** | Máy trạng thái và lý do điều kiện có thực; không lấy trạng thái đủ dữ liệu làm tín hiệu vào lệnh. | Mã + kiểm chiến lược; [nguồn](../src/XAUPY.Desktop/StrategyDashboard.axaml.cs) |
| UI-043 | RSI/Z động ghi nhớ vượt ngưỡng trong nến | **Đã triển khai** | Chế độ observed ticks ghi nhớ cực trị đã quan sát, xác nhận từ nến Trigger tiếp theo; mất liên tục dữ liệu không tự suy ra tick bị bỏ lỡ. | Kiểm thuật toán + tín hiệu đã tạo lệnh DEMO; [nguồn](../python/xaupy_engine/strategy_engine.py) |
| UI-044 | RSI/Z hiển thị khi bộ lọc tắt | **Đã triển khai** | Giá trị live để xem tách riêng khỏi chỉ báo dùng quyết định; tắt lọc không làm biến mất toàn bộ giá trị hiển thị. | Kiểm market_update; [nguồn](../src/XAUPY.Desktop/StrategyDashboard.axaml.cs) |
| UI-045 | Tự chọn RSI/Z tối ưu và áp vào app | **Chưa có** | Chưa có luồng tự hiệu chỉnh trong app. Nghiên cứu trước đó là công cụ riêng; chưa có bộ tham số chứng minh tốt nhất ngoài mẫu. | Mã + hồ sơ nghiên cứu; [nguồn](../src/XAUPY.Desktop/OptimizerDashboard.axaml.cs) |

### Giám sát

| Mã | Chức năng | Trạng thái | Kết luận / giới hạn | Bằng chứng |
| --- | --- | --- | --- | --- |
| UI-046 | Kết nối EA/Python, tuổi dữ liệu | **Đã triển khai** | Thông tin Bridge và số snapshot thật. | Mã + kết nối đang chạy; [nguồn](../src/XAUPY.Desktop/MonitoringDashboard.axaml.cs) |
| UI-047 | Latency | **Một phần** | Hiện tuổi snapshot (AgeMs), chưa đo độ trễ mạng khứ hồi. | Mã; [nguồn](../src/XAUPY.Desktop/MonitoringDashboard.axaml.cs) |
| UI-048 | Ma trận điều kiện đa khung | **Một phần** | Chỉ ba vai trò được cấu hình có kết quả; các khung khác Chưa xét, không quét độc lập cả bảy khung. | UI cách ly; [nguồn](../src/XAUPY.Desktop/MonitoringDashboard.axaml.cs) |
| UI-049 | Đồng hồ đo RSI/Z/ADX/ATR và MA | **Đã triển khai** | RSI/Z live; ADX/ATR/MA là chỉ báo chiến lược tại chu kỳ đánh giá tương ứng, có trạng thái thiếu dữ liệu. | UI cách ly; [nguồn](../src/XAUPY.Desktop/MonitoringDashboard.axaml.cs) |
| UI-050 | Phiên Sydney/Tokyo/London/New York | **Chưa có** | Chưa có dữ liệu/trạng thái phiên độc lập đầy đủ cho các ô minh họa. | Mã; [nguồn](../src/XAUPY.Desktop/MonitoringDashboard.axaml) |
| UI-051 | Lịch tin tức | **Chưa có** | Không có nguồn lịch tin trực tiếp; UI báo chưa tải lịch. | Mã; [nguồn](../src/XAUPY.Desktop/MonitoringDashboard.axaml) |
| UI-052 | CPU / RAM / Disk | **Chưa có** | Vòng đo chưa được nối tới bộ thu thông số máy; không có số sử dụng thực. | Mã + diagnostics; [nguồn](../src/XAUPY.Desktop/MonitoringDashboard.axaml) |
| UI-053 | Bộ đếm thực thi / từ chối / chờ | **Một phần** | Một số ô vẫn — hoặc LOCKED; chưa là bảng số liệu đầy đủ của đường DEMO một lệnh. | Mã; [nguồn](../src/XAUPY.Desktop/MonitoringDashboard.axaml) |
| UI-054 | Bảng cảnh báo | **Một phần** | Hiện câu trạng thái mới nhất; chưa là danh sách cảnh báo đầy đủ như Journal. | Mã; [nguồn](../src/XAUPY.Desktop/MonitoringDashboard.axaml.cs) |

### Lệnh & Vị thế

| Mã | Chức năng | Trạng thái | Kết luận / giới hạn | Bằng chứng |
| --- | --- | --- | --- | --- |
| UI-055 | Đọc vị thế / lệnh chờ MT5 | **Đã triển khai** | Đọc ticket thật, lọc sẵn theo symbol EA và magic; không tác động EA khác. | Mã + MT5 đọc trực tiếp; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.axaml.cs) |
| UI-056 | P/L, exposure, rủi ro theo SL | **Đã triển khai** | Tính từ snapshot, báo không đủ nếu thiếu SL/tick metadata; không mặc định rủi ro bằng 0. | Mã + kiểm snapshot; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.axaml.cs) |
| UI-057 | Hiển thị tất cả symbol | **Lỗi** | Checkbox không được dùng để lọc; cả hai trạng thái cho cùng danh sách. Bridge cũng chỉ gửi một symbol. | F02 tái hiện; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.axaml.cs) |
| UI-058 | Lịch sử deal đóng | **Một phần** | EA gửi tối đa 50 deal đóng trong 7 ngày theo symbol/magic; chưa là lịch sử toàn tài khoản. Giá vào có thể thiếu nếu deal vào ngoài cửa sổ 7 ngày. | Mã JsonDeals/HistoryPositionEntryPrice; [nguồn](../mql5/XAUPY_Bridge_EA.mq5) |
| UI-059 | Hiển thị symbol hiện tại ở lịch sử | **Lỗi** | Checkbox không có xử lý lọc; danh sách dùng nguyên snapshot đã lọc từ EA. | Mã; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.axaml) |
| UI-060 | Cột P/L pips / khoảng cách pips | **Một phần** | Phép tính chia cho Point; thực chất là point, chưa định nghĩa pip riêng theo symbol. | Mã; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.axaml.cs) |
| UI-061 | Đóng một vị thế | **Mô phỏng** | Gửi yêu cầu mô phỏng và báo kết quả; không gửi đóng broker. | Mã + kiểm simulator; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.axaml.cs) |
| UI-062 | Đóng 1/2 vị thế | **Mô phỏng** | Mô phỏng một phần; không giảm volume tại MT5. | Mã + kiểm simulator; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.axaml.cs) |
| UI-063 | Chuyển một SL về BE | **Mô phỏng** | Không sửa SL broker. | Mã + kiểm simulator; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.axaml.cs) |
| UI-064 | Trailing một vị thế | **Mô phỏng** | Không bật vòng trailing trên vị thế broker. | Mã + kiểm simulator; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.axaml.cs) |
| UI-065 | Sửa / hủy một pending | **Mô phỏng** | Hai thao tác hàng dùng simulator, không sửa/hủy tại MT5. | Mã + kiểm simulator; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.axaml.cs) |
| UI-066 | Đóng tất cả | **Mô phỏng** | Chỉ mô phỏng các ticket thuộc snapshot. | Mã + kiểm simulator; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.axaml.cs) |
| UI-067 | Đóng lãi | **Mô phỏng** | Lọc và mô phỏng, không đóng broker. | Mã + kiểm simulator; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.axaml.cs) |
| UI-068 | Đóng lỗ | **Mô phỏng** | Lọc và mô phỏng, không đóng broker. | Mã + kiểm simulator; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.axaml.cs) |
| UI-069 | Đóng một phần hàng loạt | **Mô phỏng** | Mô phỏng 50%, chưa cho tùy chọn tỷ lệ riêng trong nút này. | Mã + kiểm simulator; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.axaml.cs) |
| UI-070 | Chuyển BE hàng loạt | **Mô phỏng** | Không sửa SL tại MT5. | Mã + kiểm simulator; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.axaml.cs) |
| UI-071 | Trailing hàng loạt | **Mô phỏng** | Không có quản lý broker liên tục. | Mã + kiểm simulator; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.axaml.cs) |
| UI-072 | Hủy tất cả pending | **Mô phỏng** | Không hủy lệnh tại MT5. | Mã + kiểm simulator; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.axaml.cs) |
| UI-073 | Xác nhận trước đóng/sửa/hủy | **Đã triển khai** | Là điều kiện xác nhận cho simulator, không cấp quyền giao dịch thật. | Mã + kiểm simulator; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.axaml.cs) |
| UI-074 | Nhập lot, SL, TP và năm nút lot nhanh | **Đã triển khai** | Thay đổi tham số yêu cầu mô phỏng, có kiểm volume/stops. | Mã + kiểm simulator; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.axaml.cs) |
| UI-075 | BUY thủ công | **Mô phỏng** | Chỉ MarketBuy → SimulateManualAction, không phải đường DEMO một lệnh. | Mã + kiểm simulator; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.axaml.cs) |
| UI-076 | SELL thủ công | **Mô phỏng** | Chỉ MarketSell → SimulateManualAction. | Mã + kiểm simulator; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.axaml.cs) |
| UI-077 | Form đặt lệnh chờ / tab Thông tin | **Chưa có** | Hai nút bị vô hiệu hóa; chưa có form đặt pending thực. | Mã; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.axaml) |
| UI-078 | Xuất báo cáo lệnh | **Chưa có** | Nút bị vô hiệu hóa, chưa có handler xuất. | Mã; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.axaml) |
| UI-079 | Bắt đầu chờ tín hiệu DEMO một lệnh | **Đã triển khai** | Có đường EA OrderSend thực, tối đa 0,01 lot, tín hiệu mới, SL/TP broker, dùng quyền một lần. | Đã đối chiếu broker fill trong lần audit này; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.DemoOnce.cs) |
| UI-080 | Dừng chờ DEMO / làm mới trạng thái | **Đã triển khai** | Hủy quyền chờ ARMED hoặc đọc lại trạng thái; không đóng vị thế đã khớp. | Mã + kiểm giao thức; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.DemoOnce.cs) |
| UI-081 | Giới hạn lot / thời hạn chờ | **Đã triển khai** | Gửi ràng buộc cụ thể vào quyền DEMO, nhận trạng thái thực. | Mã + UI cách ly; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.DemoOnce.cs) |
| UI-082 | Lý do chờ DEMO tự cập nhật | **Lỗi** | Heartbeat đổi nhãn trạng thái nhưng không đổi dòng DemoOnceMessage; reason cũ còn lại đến khi refresh. LastBlocker cũng được ưu tiên trước Reason. | F03 tái hiện; [nguồn](../src/XAUPY.Desktop/OrdersPositionsDashboard.DemoOnce.cs) |
| UI-083 | Thực thi liên tục nhiều lệnh DEMO | **Chưa có** | Hiện là entry acceptance một lần, không phải robot chạy nhiều lệnh theo profile. | Mã + budget_consumed thực; [nguồn](../python/xaupy_engine/demo_once.py) |
| UI-084 | Chọn DEMO/REAL và quyền giao dịch theo người dùng | **Chưa có** | Chưa đạt yêu cầu người dùng: demo_only/allow_real vẫn khóa trong schema; không có executor REAL. | Mã; [nguồn](../python/xaupy_engine/config_schema.py) |
| UI-085 | BE, partial, trailing tự động sau khi khớp | **Mô phỏng** | Có trong backtest, chưa có vòng quản lý vị thế broker. Profile guard vẫn chấp nhận các cờ này, dễ gây hiểu nhầm đã hoạt động. | B02 + chỉ có một vị trí OrderSend trong EA; [nguồn](../python/xaupy_engine/demo_once.py) |
| UI-086 | MARKET, STOP_CONFIRM, TP động khi chạy broker | **Một phần** | DEMO thực chỉ MARKET và TP FIXED/RR; STOP_CONFIRM, ZRSI_DYNAMIC bị từ chối rõ. SL FIXED/STRUCTURE/ATR đã có. | Mã + kiểm guard; [nguồn](../python/xaupy_engine/demo_once.py) |
| UI-087 | Sizing theo % rủi ro | **Một phần** | DEMO chọn volume trong trần 0,01 rồi kiểm giới hạn lỗ; chưa sizing theo % giống backtest. max_open_positions>1 cũng không mở nhiều vị thế. | Mã _volume/_risk_guard/_command; [nguồn](../python/xaupy_engine/demo_once.py) |
| UI-088 | Giờ phiên / ngày / spread / rủi ro trước lệnh | **Đã triển khai** | Có kiểm phiên, ngày, cooldown, lỗ ngày, chuỗi lỗ, mục tiêu ngày, spread, phí dự phòng, SL và RR. Không phải bật REAL. | Mã + kiểm guard + fill đúng active profile; [nguồn](../python/xaupy_engine/demo_once.py) |

### Backtest

| Mã | Chức năng | Trạng thái | Kết luận / giới hạn | Bằng chứng |
| --- | --- | --- | --- | --- |
| UI-089 | Chọn file JSON/CSV M1 | **Đã triển khai** | Nạp dữ liệu lịch sử thật, kiểm OHLC và metadata. Không tự lấy toàn bộ kho đã tải nếu chưa chọn file. | Mã + kiểm dữ liệu; [nguồn](../src/XAUPY.Desktop/BacktestDashboard.axaml.cs) |
| UI-090 | Ngày bắt đầu/kết thúc, vốn, spread, commission | **Đã triển khai** | Được truyền vào bộ replay, kiểm định dạng và giới hạn. | Mã + kiểm backtest; [nguồn](../src/XAUPY.Desktop/BacktestDashboard.axaml.cs) |
| UI-091 | Chạy M1 OHLC | **Đã triển khai** | Có replay, giao dịch mô phỏng, metrics và lưu lịch sử. Không phải mô hình Every Tick. | 386 tests gồm backtest + B05 chạy thực 3.000 nến; [nguồn](../python/xaupy_engine/backtest.py) |
| UI-092 | Các giới hạn chi phí trong profile | **Lỗi** | Backtest không đọc nhóm costs: trần spread/commission, min net RR, max slippage. Đặt spread tối đa 0 và RR tối thiểu 100 vẫn có cùng giao dịch/metrics. Spread/commission nhập tay vẫn được tính vào P/L. | B06 tái hiện + quét consumer; [nguồn](../python/xaupy_engine/backtest.py) |
| UI-093 | Chọn timeframe/model khác | **Chưa có** | Chỉ M1 OHLC; các bộ chọn khác bị khóa. | Mã; [nguồn](../src/XAUPY.Desktop/BacktestDashboard.axaml) |
| UI-094 | Chạy profile RSI/Z intrabar đang dùng | **Chưa có** | Bị từ chối vì OHLC không chứa thứ tự tick. Cần dữ liệu tick và mô hình replay tick; không được coi nến đóng là tương đương. | B01 tái hiện với bản sao active; [nguồn](../python/xaupy_engine/backtest.py) |
| UI-095 | Dữ liệu live tiếp tục cập nhật trong lúc backtest | **Lỗi** | Dispatch backtest chạy đồng bộ trong luồng IPC chung. 3.000 nến giữ luồng 1,6117 s; timer 10 ms chạy sau 1,6118 s. IPC desktop còn dùng chung khóa I/O. | B05 tái hiện cách ly; [nguồn](../python/xaupy_engine/server.py) |
| UI-096 | Dừng / hủy backtest từ UI | **Chưa có** | Không có nút hủy và job riêng như Optimizer. | Mã; [nguồn](../src/XAUPY.Desktop/BacktestDashboard.axaml.cs) |
| UI-097 | SL ATR/structure/fixed, TP dynamic/fixed/RR | **Mô phỏng** | Đã triển khai trong replay, không chứng minh các chế độ đó đã dùng trên broker. | Kiểm backtest + B04; [nguồn](../python/xaupy_engine/backtest.py) |
| UI-098 | BE / partial / trailing / STOP_CONFIRM | **Mô phỏng** | Đã có trong backtest, chỉ mô phỏng. | Kiểm backtest; [nguồn](../python/xaupy_engine/backtest.py) |
| UI-099 | Equity / balance / cả hai | **Đã triển khai** | Vẽ kết quả thực của lần chạy, đổi series và giữ lựa chọn. | Kiểm chart; [nguồn](../src/XAUPY.Desktop/BacktestChartControl.cs) |
| UI-100 | Drawdown / histogram / KPI | **Đã triển khai** | Tính từ kết quả mô phỏng, không lấy số trong ảnh demo. | Kiểm backtest + chart; [nguồn](../src/XAUPY.Desktop/BacktestDashboard.axaml.cs) |
| UI-101 | So sánh kết quả | **Chưa có** | Nút bị vô hiệu hóa; chưa có màn hình compare hai lần chạy. | Mã; [nguồn](../src/XAUPY.Desktop/BacktestDashboard.axaml) |
| UI-102 | Lưu kết quả JSON | **Đã triển khai** | Xuất kết quả và lấy đủ các trang giao dịch. | Mã + kiểm API; [nguồn](../src/XAUPY.Desktop/BacktestDashboard.axaml.cs) |
| UI-103 | Xuất báo cáo CSV | **Một phần** | CSV danh sách trade; chưa là báo cáo tổng hợp PDF/HTML riêng. | Mã; [nguồn](../src/XAUPY.Desktop/BacktestDashboard.axaml.cs) |
| UI-104 | Làm mới / chọn / xem / xóa lịch sử | **Đã triển khai** | Đọc và xóa kết quả đã lưu; UI lấy tối đa 50 lần chạy gần nhất. | Mã + kiểm repository; [nguồn](../src/XAUPY.Desktop/BacktestDashboard.axaml.cs) |
| UI-105 | Phân trang giao dịch | **Đã triển khai** | 8 trade mỗi trang, có trước/sau và tổng trang. | Mã + kiểm API; [nguồn](../src/XAUPY.Desktop/BacktestDashboard.axaml.cs) |

### Tối ưu hóa

| Mã | Chức năng | Trạng thái | Kết luận / giới hạn | Bằng chứng |
| --- | --- | --- | --- | --- |
| UI-106 | Chọn dataset, ngày, vốn, chi phí | **Đã triển khai** | Bộ chọn dữ liệu M1 và tham số chạy thật; chịu giới hạn replay giống Backtest. | Mã + kiểm optimizer; [nguồn](../src/XAUPY.Desktop/OptimizerDashboard.axaml.cs) |
| UI-107 | Dải ba timeframe | **Đã triển khai** | Min/max các khung hợp lệ tạo tập ứng viên. | Mã + kiểm ranges; [nguồn](../src/XAUPY.Desktop/OptimizerDashboard.axaml.cs) |
| UI-108 | Dải ngưỡng RSI BUY/SELL | **Đã triển khai** | Min/max/step dùng khi RSI Pullback bật. | Mã + kiểm ranges; [nguồn](../src/XAUPY.Desktop/OptimizerDashboard.axaml.cs) |
| UI-109 | Delta RSI / Z | **Một phần** | Chỉ có một hàng delta; ưu tiên RSI nếu cả RSI và Z bật, chưa tối ưu riêng cả hai qua UI. | Mã; [nguồn](../src/XAUPY.Desktop/OptimizerDashboard.axaml.cs) |
| UI-110 | Chu kỳ RSI / chu kỳ Z / ngưỡng Z | **Chưa có** | Chưa có hàng dải tương ứng trên UI; API backend tổng quát hơn UI. | Mã; [nguồn](../src/XAUPY.Desktop/OptimizerDashboard.axaml.cs) |
| UI-111 | Dải MA period | **Đã triển khai** | Có dải chu kỳ khi Direction MA bật. | Mã; [nguồn](../src/XAUPY.Desktop/OptimizerDashboard.axaml.cs) |
| UI-112 | Dải SL fixed / structure | **Đã triển khai** | Hai chế độ có ô dải tương ứng. | Mã; [nguồn](../src/XAUPY.Desktop/OptimizerDashboard.axaml.cs) |
| UI-113 | Dải SL ATR | **Một phần** | Backend hỗ trợ, UI vô hiệu hóa và ghi Task 011 chưa hỗ trợ. | F06 + B04; [nguồn](../src/XAUPY.Desktop/OptimizerDashboard.axaml.cs) |
| UI-114 | Dải TP fixed / RR | **Đã triển khai** | Có dải theo chế độ active. | Mã; [nguồn](../src/XAUPY.Desktop/OptimizerDashboard.axaml.cs) |
| UI-115 | Dải TP ZRSI_DYNAMIC | **Một phần** | Backend hỗ trợ, UI chưa có range editor, còn nhãn cũ. | F07 + B04; [nguồn](../src/XAUPY.Desktop/OptimizerDashboard.axaml.cs) |
| UI-116 | Bắt đầu sweep / workers / min trades | **Đã triển khai** | Có hàng đợi ứng viên, worker và tiêu chí đủ số lệnh. | Kiểm optimizer; [nguồn](../src/XAUPY.Desktop/OptimizerDashboard.axaml.cs) |
| UI-117 | Dừng job / xem tiến độ | **Đã triển khai** | Có cancel và progress thật; khác Backtest đơn lẻ. | Kiểm optimizer; [nguồn](../src/XAUPY.Desktop/OptimizerDashboard.axaml.cs) |
| UI-118 | Top 10 / xem tham số ứng viên | **Đã triển khai** | Xếp hạng và mở JSON cấu hình ứng viên. Chưa kết luận có lợi nhuận tương lai. | Kiểm optimizer; [nguồn](../src/XAUPY.Desktop/OptimizerDashboard.axaml.cs) |
| UI-119 | Áp dụng ứng viên tốt nhất trực tiếp | **Chưa có** | Chưa có nút đưa ứng viên đã chọn vào active profile. | Mã; [nguồn](../src/XAUPY.Desktop/OptimizerDashboard.axaml.cs) |
| UI-120 | Heatmap X/Y/metric | **Đã triển khai** | Đọc dữ liệu tối ưu và đổi trục/metric thật. | Kiểm heatmap; [nguồn](../src/XAUPY.Desktop/OptimizerDashboard.axaml.cs) |
| UI-121 | Walk-forward: folds, ratio, rolling/expanding | **Đã triển khai** | Có chia train/test và chạy ngoài mẫu; vẫn là M1 OHLC, không chạy intrabar active hiện tại. | Kiểm walk-forward; [nguồn](../src/XAUPY.Desktop/OptimizerDashboard.axaml.cs) |
| UI-122 | Lưu / tải preset tối ưu | **Đã triển khai** | Lưu file mô tả ranges/context. Combo không phải thư viện nhiều preset dựng sẵn. | Kiểm preset; [nguồn](../src/XAUPY.Desktop/OptimizerDashboard.axaml.cs) |
| UI-123 | CPU/RAM/Disk và hiệu suất worker | **Một phần** | Có số worker/tiến độ; chưa có telemetry CPU/RAM/Disk thật. Hai loại số liệu không tương đương. | Mã; [nguồn](../src/XAUPY.Desktop/OptimizerDashboard.axaml.cs) |

### Nhật ký

| Mã | Chức năng | Trạng thái | Kết luận / giới hạn | Bằng chứng |
| --- | --- | --- | --- | --- |
| UI-124 | Log thật / tự cập nhật | **Đã triển khai** | Structured journal từ Engine, tải lại khi latest sequence thay đổi. | Mã + kiểm journal; [nguồn](../src/XAUPY.Desktop/JournalDashboard.axaml.cs) |
| UI-125 | 7 nguồn log | **Một phần** | Bộ lọc hoạt động theo source; mục MT5 là sự kiện được XAUPY ghi, không phải bộ đọc toàn bộ Experts/Journal của terminal. | Mã + kiểm journal; [nguồn](../src/XAUPY.Desktop/JournalDashboard.axaml.cs) |
| UI-126 | INFO / WARN / ERROR / DEBUG | **Đã triển khai** | Các checkbox được đưa vào truy vấn backend. | Mã + kiểm journal; [nguồn](../src/XAUPY.Desktop/JournalDashboard.axaml.cs) |
| UI-127 | Tìm kiếm và phạm vi ngày | **Đã triển khai** | Tìm kiếm trễ 350 ms, chọn Hôm nay/Tất cả và làm mới. | Mã + kiểm journal; [nguồn](../src/XAUPY.Desktop/JournalDashboard.axaml.cs) |
| UI-128 | Chọn dòng / chi tiết JSON | **Đã triển khai** | Hiện nội dung sự kiện, nguồn, tag, sequence, chi tiết. | Mã; [nguồn](../src/XAUPY.Desktop/JournalDashboard.axaml.cs) |
| UI-129 | Thêm / bỏ / lọc dấu trang | **Đã triển khai** | Lưu dấu trang, truy vấn lại và phục hồi từ journal. | Kiểm journal; [nguồn](../src/XAUPY.Desktop/JournalDashboard.axaml.cs) |
| UI-130 | Xem tất cả cảnh báo / dấu trang | **Một phần** | Đổi bộ lọc hoạt động nhưng truy vấn vẫn tối đa 500 dòng, không có phân trang tiếp. | Mã limit:500; [nguồn](../src/XAUPY.Desktop/JournalDashboard.axaml.cs) |
| UI-131 | Xuất log | **Một phần** | Xuất JSONL các dòng đang tải, tối đa 500; không xuất toàn bộ số TotalMatched nếu vượt giới hạn. | Mã ExportLog; [nguồn](../src/XAUPY.Desktop/JournalDashboard.axaml.cs) |
| UI-132 | Replay / nhận diện log lỗi, trùng | **Đã triển khai** | Có kiểm schema, duplicate và bộ đếm integrity. | Kiểm journal; [nguồn](../python/xaupy_engine/journal.py) |

### Công cụ

| Mã | Chức năng | Trạng thái | Kết luận / giới hạn | Bằng chứng |
| --- | --- | --- | --- | --- |
| UI-133 | Trình JSON: nhập/sửa, màu cú pháp, số dòng | **Đã triển khai** | Editor native thực, có cập nhật số dòng và thông tin file. | 84 kiểm tra UI; [nguồn](../src/XAUPY.Desktop/ToolsDashboard.axaml.cs) |
| UI-134 | Tìm kiếm / tìm tiếp / đóng tìm kiếm | **Đã triển khai** | Ctrl+F, chọn kết quả và wrap tìm tiếp. | UI cách ly; [nguồn](../src/XAUPY.Desktop/ToolsDashboard.axaml.cs) |
| UI-135 | Định dạng JSON / kiểm cú pháp và schema | **Đã triển khai** | Có format, parse, validate profile. File tin có bộ kiểm riêng. | Mã + UI cách ly; [nguồn](../src/XAUPY.Desktop/ToolsDashboard.axaml.cs) |
| UI-136 | Mở file / Lưu thành | **Đã triển khai** | Đọc/ghi JSON trên máy; SaveAs là lưu file, không phải áp dụng. | Mã; [nguồn](../src/XAUPY.Desktop/ToolsDashboard.axaml.cs) |
| UI-137 | Lưu thay đổi / Áp dụng / Ctrl+S | **Một phần** | Cả hai gọi Apply active profile; Ctrl+S cũng có thể áp dụng cấu hình đang chạy, không chỉ lưu file. | Mã; [nguồn](../src/XAUPY.Desktop/ToolsDashboard.axaml.cs) |
| UI-138 | Bảo toàn bản nháp khi Tải lại/đổi công cụ | **Lỗi** | Không có dirty guard; tải lại ghi đè nội dung đang sửa mà không báo trước. | F05 tái hiện; [nguồn](../src/XAUPY.Desktop/ToolsDashboard.axaml.cs) |
| UI-139 | Chặn xung đột với bản nháp tab khác | **Một phần** | Tools không tham gia HasConflictingDraft của Cấu hình/Chiến lược/Tổng quan; còn đường áp dụng ngoài cơ chế bảo vệ chung. | Mã; [nguồn](../src/XAUPY.Desktop/ToolsDashboard.axaml.cs) |
| UI-140 | Ô Symbol thông tin file | **Lỗi** | Đọc active.symbol thay vì active.strategy.symbol, nên profile EURUSD vẫn hiện XAUUSD. | F04 tái hiện; [nguồn](../src/XAUPY.Desktop/ToolsDashboard.axaml.cs) |
| UI-141 | Mặc định / Tải lại | **Đã triển khai** | Nạp default/active thật; lưu ý lỗi mất bản nháp ở dòng riêng. | Mã; [nguồn](../src/XAUPY.Desktop/ToolsDashboard.axaml.cs) |
| UI-142 | Toàn màn hình editor | **Một phần** | Mở rộng vùng soạn thảo bằng F11, không chuyển toàn app sang fullscreen hệ điều hành. | UI cách ly; [nguồn](../src/XAUPY.Desktop/ToolsDashboard.axaml.cs) |
| UI-143 | So sánh Preset | **Một phần** | Chỉ so DEFAULT với ACTIVE, chưa chọn hai file tùy ý. | Mã; [nguồn](../src/XAUPY.Desktop/ToolsDashboard.axaml.cs) |
| UI-144 | Kiểm tra chỉ báo | **Một phần** | Xem diagnostics.strategy; chưa là đối chiếu độc lập công thức/indicator giữa MT5 và Python. | Mã; [nguồn](../src/XAUPY.Desktop/ToolsDashboard.axaml.cs) |
| UI-145 | Tính lot theo rủi ro | **Một phần** | Tính theo tiền rủi ro, SL, tick size/value nhập tay; chưa làm tròn broker step và chưa tính spread/phí/trượt giá. | Mã; [nguồn](../src/XAUPY.Desktop/ToolsDashboard.axaml.cs) |
| UI-146 | Thông tin Symbol & Phiên | **Một phần** | Hiện overview + sessions; chưa là trang đủ thuộc tính broker và lịch phiên từng thị trường. | Mã; [nguồn](../src/XAUPY.Desktop/ToolsDashboard.axaml.cs) |
| UI-147 | Kiểm tra file tin tức | **Một phần** | Đọc và kiểm định dạng JSON; không nhập thành nguồn news guard giao dịch. | Mã; [nguồn](../src/XAUPY.Desktop/ToolsDashboard.axaml.cs) |
| UI-148 | Chẩn đoán hệ thống | **Đã triển khai** | Có kiểm môi trường, kết nối, cấu hình, đường dẫn và journal; phạm vi không bao gồm CPU/RAM/Disk live. | Kiểm maintenance; [nguồn](../src/XAUPY.Desktop/ToolsDashboard.axaml.cs) |
| UI-149 | Kiểm tra Bridge | **Đã triển khai** | Đọc trạng thái Bridge thật qua diagnostics, không tạo tín hiệu hoặc lệnh. | Kiểm maintenance; [nguồn](../src/XAUPY.Desktop/ToolsDashboard.axaml.cs) |
| UI-150 | Quản lý hồ sơ | **Một phần** | Cùng editor active profile; chưa có thư viện profile đặt tên, chuyển hàng loạt hoặc quản lý phiên bản riêng. | Mã; [nguồn](../src/XAUPY.Desktop/ToolsDashboard.axaml.cs) |
| UI-151 | Xuất / nhập dữ liệu | **Một phần** | Xuất diagnostics JSON / nhập cấu hình JSON; tải lịch sử là luồng riêng. Chưa là bộ nhập/xuất mọi dữ liệu giao dịch. | Mã; [nguồn](../src/XAUPY.Desktop/ToolsDashboard.axaml.cs) |
| UI-152 | Tải lịch sử MT5 và xem tiến độ | **Đã triển khai** | Job riêng tải các timeframe tới giới hạn MT5/broker trả về, có terminal/symbol đầu vào; không làm việc chặn đồng bộ trong IPC. | Mã + bằng chứng tải lịch sử trước audit; [nguồn](../python/xaupy_engine/history_jobs.py) |
| UI-153 | Tự nối kho lịch sử vào Backtest/Optimizer | **Chưa có** | Sau tải vẫn cần chọn dataset M1; chưa có quy trình liền mạch chọn kho/chạy nghiên cứu/áp kết quả. | Mã; [nguồn](../src/XAUPY.Desktop/ToolsDashboard.axaml.cs) |
| UI-154 | Hướng dẫn | **Đã triển khai** | Có hướng dẫn thao tác và shortcut trong app. | Mã; [nguồn](../src/XAUPY.Desktop/ToolsDashboard.axaml.cs) |

### Cài đặt

| Mã | Chức năng | Trạng thái | Kết luận / giới hạn | Bằng chứng |
| --- | --- | --- | --- | --- |
| UI-155 | Đọc tài khoản / loại tài khoản / probe | **Đã triển khai** | Dùng phiên MT5 qua EA đang kết nối; không có đăng nhập bằng mật khẩu trong app. | Kiểm maintenance + live; [nguồn](../src/XAUPY.Desktop/SettingsDashboard.axaml.cs) |
| UI-156 | Chọn / lưu đường dẫn MT5 | **Một phần** | Có hộp chọn và lưu; chưa có consumer dùng setting này để mở/chuyển terminal kết nối. HistoryTerminal là trường khác. | Quét tham chiếu mt5_path; [nguồn](../src/XAUPY.Desktop/SettingsDashboard.axaml.cs) |
| UI-157 | Chế độ Bridge / host / port | **Một phần** | Chỉ một chế độ Python Bridge và loopback/39421 cố định; không phải lựa chọn nhiều backend. | Mã; [nguồn](../src/XAUPY.Desktop/SettingsDashboard.axaml) |
| UI-158 | Tự khởi động Engine | **Đã triển khai** | Preference được đọc khi mở MainWindow. | Mã + UI/API cách ly; [nguồn](../src/XAUPY.Desktop/SettingsDashboard.axaml.cs) |
| UI-159 | Tự khởi động lại Engine khi lỗi | **Đã triển khai** | Preference được truyền vào supervisor; chưa có nghĩa tự bật giao dịch sau lỗi. | Mã + UI/API cách ly; [nguồn](../src/XAUPY.Desktop/SettingsDashboard.axaml.cs) |
| UI-160 | Đường dẫn dữ liệu/log/backtest/history/backup | **Đã triển khai** | Các ô chỉ đọc và nút mở thư mục thật, không phải các đường dẫn cho sửa. | Mã; [nguồn](../src/XAUPY.Desktop/SettingsDashboard.axaml.cs) |
| UI-161 | Theme / ngôn ngữ / tỷ lệ chữ | **Một phần** | Mỗi combo chỉ một lựa chọn cố định N30 Dark/Tiếng Việt/100%; chưa có đổi theme, dịch hay scale. | Mã; [nguồn](../src/XAUPY.Desktop/SettingsDashboard.axaml) |
| UI-162 | Hiện lỗi hệ thống / thay đổi kết nối | **Một phần** | Hai preference thực sự lọc log nhanh; chưa phải thông báo toast, âm thanh hoặc email. | Mã + kiểm lưu preference; [nguồn](../src/XAUPY.Desktop/MainWindow.axaml.cs) |
| UI-163 | Giới hạn rủi ro hiển thị | **Đã triển khai** | Đọc từ active profile; muốn sửa phải vào Cấu hình, ô Settings chỉ đọc. | Mã; [nguồn](../src/XAUPY.Desktop/SettingsDashboard.axaml.cs) |
| UI-164 | Khởi động cùng Windows | **Chưa nghiệm thu OS** | Đã có ghi/xóa HKCU Run và rollback nếu lưu lỗi; chưa kiểm nghiệm một phiên Windows đăng nhập mới trong audit này. | Đọc mã, không sửa registry máy đang dùng; [nguồn](../src/XAUPY.Desktop/SettingsDashboard.axaml.cs) |
| UI-165 | Bắt buộc đồng bộ Bridge lúc mở | **Một phần** | Checkbox khóa true; Engine chờ dữ liệu mới. Không là tùy chọn người dùng có thể bỏ. | Mã; [nguồn](../src/XAUPY.Desktop/SettingsDashboard.axaml) |
| UI-166 | Tự động chạy giao dịch | **Chưa có** | Checkbox bị khóa false; chưa có general autotrading lifecycle. | Mã; [nguồn](../src/XAUPY.Desktop/SettingsDashboard.axaml) |
| UI-167 | Quyền tài khoản thật | **Chưa có** | Đã đổi UI thành mô tả chưa triển khai; không có nút bật REAL hoạt động. Yêu cầu người dùng tự quyết định còn chưa hoàn tất. | Mã; [nguồn](../src/XAUPY.Desktop/SettingsDashboard.axaml) |
| UI-168 | Sao lưu trước thay đổi / giữ tối đa | **Đã triển khai** | Preference, giới hạn 1–100 và retention có xử lý thực. | Kiểm settings/backup; [nguồn](../src/XAUPY.Desktop/SettingsDashboard.axaml.cs) |
| UI-169 | Sao lưu ngay / danh sách backup | **Đã triển khai** | Tạo và đọc bản backup thật trong thư mục dữ liệu. | Kiểm maintenance; [nguồn](../src/XAUPY.Desktop/SettingsDashboard.axaml.cs) |
| UI-170 | Khôi phục backup | **Đã triển khai** | Validate rồi khôi phục profile/settings; không khôi phục quyền gửi DEMO đã dùng thành quyền mới. | Kiểm maintenance; [nguồn](../src/XAUPY.Desktop/SettingsDashboard.axaml.cs) |
| UI-171 | Mặc định / Hủy thay đổi / Lưu cài đặt | **Đã triển khai** | Đọc/ghi cấu hình hệ thống thực và giữ độc lập với strategy profile. | UI/API cách ly; [nguồn](../src/XAUPY.Desktop/SettingsDashboard.axaml.cs) |
| UI-172 | Thông tin hệ thống / execution summary | **Một phần** | Có phiên bản và diagnostics; một số nhãn LOCKED tổng quát chưa trình bày đầy đủ ngoại lệ DEMO một lệnh. | Mã; [nguồn](../src/XAUPY.Desktop/SettingsDashboard.axaml.cs) |

## Phụ lục: từng thông số cấu hình

Tất cả 133 trường được trình Cấu hình đọc/validate/lưu; bảng dưới nói về tác dụng sau khi lưu. Tham số con chỉ có tác dụng khi nhóm/mode cha được bật. Cột DEMO chỉ nói về executor một lệnh hiện tại, không đại diện REAL. Các kết hợp không được liệt kê là đã thử mọi trường hợp.

| Thông số | Trạng thái | Ô sửa | DEMO/luồng đang chạy | Backtest/Optimizer | Nguồn |
| --- | --- | --- | --- | --- | --- |
| `profile.name` | Thông tin | Sửa/lưu được | Lưu/tên/ghi chú, không tạo tín hiệu | Không ảnh hưởng thuật toán | `config_schema.py` |
| `profile.notes` | Thông tin | Sửa/lưu được | Lưu/tên/ghi chú, không tạo tín hiệu | Không ảnh hưởng thuật toán | `config_schema.py` |
| `strategy.symbol` | Có điều kiện | Sửa/lưu được | Phải khớp symbol EA đang gắn; không tự đổi chart MT5 | Phải khớp symbol dataset | `demo_once.py` |
| `strategy.allow_buy` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `strategy.allow_sell` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `timeframes.direction` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `timeframes.pullback` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `timeframes.trigger` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `direction.ma_enabled` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `direction.ma_type` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `direction.ma_period` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `direction.price_source` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `direction.require_close_side` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `direction.open_filter_enabled` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `direction.open_reference_mode` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `pullback.logic` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `pullback.rsi_enabled` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `pullback.rsi_period` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `pullback.rsi_buy_level` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `pullback.rsi_sell_level` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `pullback.z_enabled` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `pullback.z_period` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `pullback.z_buy_level` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `pullback.z_sell_level` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `trigger.logic` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `trigger.rsi_enabled` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `trigger.rsi_period` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `trigger.rsi_reversal_delta` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `trigger.z_enabled` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `trigger.z_period` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `trigger.z_reversal_delta` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `trigger.confirm_closed_bar` | Một phần | Sửa/lưu được | True: nến đóng; False: tick quan sát + xác nhận từ nến tiếp theo | Chỉ hỗ trợ true; false bị từ chối | `strategy_engine.py; backtest.py` |
| `filters.adx.enabled` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `filters.adx.timeframe` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `filters.adx.period` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `filters.adx.min` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `filters.adx.max` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `filters.atr.enabled` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `filters.atr.timeframe` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `filters.atr.period` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `filters.atr.min_price_units` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `filters.atr.max_price_units` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `filters.open.enabled` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `filters.open.reference_mode` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `filters.open.buffer_price_units` | Đã có | Sửa/lưu được | Dùng trong tín hiệu theo vai trò/filter đang bật; không tự bật quyền broker | Dùng trong replay nến đóng; filter tắt thì tham số phụ không lọc | `strategy_engine.py` |
| `entry.mode` | Một phần | Sửa/lưu được | Chỉ MARKET; STOP_CONFIRM bị từ chối | MARKET và STOP_CONFIRM | `demo_once.py; backtest.py` |
| `entry.pending_buffer_price_units` | Chỉ mô phỏng | Sửa/lưu được | Không áp dụng vì DEMO chưa hỗ trợ pending | Dùng cho STOP_CONFIRM/pending khi chế độ đó bật | `backtest.py` |
| `entry.pending_expiration_minutes` | Chỉ mô phỏng | Sửa/lưu được | Không áp dụng vì DEMO chưa hỗ trợ pending | Dùng cho STOP_CONFIRM/pending khi chế độ đó bật | `backtest.py` |
| `entry.cancel_on_opposite_setup` | Chỉ mô phỏng | Sửa/lưu được | Không áp dụng vì DEMO chưa hỗ trợ pending | Dùng cho STOP_CONFIRM/pending khi chế độ đó bật | `backtest.py` |
| `entry.cancel_on_direction_change` | Chỉ mô phỏng | Sửa/lưu được | Không áp dụng vì DEMO chưa hỗ trợ pending | Dùng cho STOP_CONFIRM/pending khi chế độ đó bật | `backtest.py` |
| `entry.max_signal_age_bars` | Đã có | Sửa/lưu được | Giới hạn tuổi setup intrabar; đường gửi còn kiểm độ mới tín hiệu | Giới hạn tuổi tín hiệu trong replay | `strategy_engine.py; backtest.py` |
| `risk.sizing_mode` | Một phần | Sửa/lưu được | Trần DEMO ≤0,01; risk_percent kiểm tiền lỗ, chưa tính lot theo % đầy đủ | Sizing theo % hoặc lot cố định | `demo_once.py; backtest.py` |
| `risk.risk_percent` | Một phần | Sửa/lưu được | Trần DEMO ≤0,01; risk_percent kiểm tiền lỗ, chưa tính lot theo % đầy đủ | Sizing theo % hoặc lot cố định | `demo_once.py; backtest.py` |
| `risk.fixed_lot` | Có điều kiện | Sửa/lưu được | Có guard tiền/lot/ngày/cooldown tương ứng; vẫn chỉ một lần gửi DEMO | Có dùng khi điều kiện cha áp dụng | `demo_once.py; backtest.py` |
| `risk.max_lot` | Có điều kiện | Sửa/lưu được | Có guard tiền/lot/ngày/cooldown tương ứng; vẫn chỉ một lần gửi DEMO | Có dùng khi điều kiện cha áp dụng | `demo_once.py; backtest.py` |
| `risk.max_daily_loss_pct` | Có điều kiện | Sửa/lưu được | Có guard tiền/lot/ngày/cooldown tương ứng; vẫn chỉ một lần gửi DEMO | Có dùng khi điều kiện cha áp dụng | `demo_once.py; backtest.py` |
| `risk.max_trades_per_day` | Có điều kiện | Sửa/lưu được | Có guard tiền/lot/ngày/cooldown tương ứng; vẫn chỉ một lần gửi DEMO | Có dùng khi điều kiện cha áp dụng | `demo_once.py; backtest.py` |
| `risk.max_open_positions` | Một phần | Sửa/lưu được | Không cho thêm lệnh khi symbol đã có vị thế/lệnh chờ; giá trị >1 chưa mở rộng được | Có giới hạn vị thế trong replay | `demo_once.py; backtest.py` |
| `risk.cooldown_minutes` | Có điều kiện | Sửa/lưu được | Có guard tiền/lot/ngày/cooldown tương ứng; vẫn chỉ một lần gửi DEMO | Có dùng khi điều kiện cha áp dụng | `demo_once.py; backtest.py` |
| `risk.max_consecutive_losses` | Có điều kiện | Sửa/lưu được | Có guard tiền/lot/ngày/cooldown tương ứng; vẫn chỉ một lần gửi DEMO | Có dùng khi điều kiện cha áp dụng | `demo_once.py; backtest.py` |
| `risk.stop_after_daily_target` | Có điều kiện | Sửa/lưu được | Có guard tiền/lot/ngày/cooldown tương ứng; vẫn chỉ một lần gửi DEMO | Có dùng khi điều kiện cha áp dụng | `demo_once.py; backtest.py` |
| `risk.daily_target_pct` | Có điều kiện | Sửa/lưu được | Có guard tiền/lot/ngày/cooldown tương ứng; vẫn chỉ một lần gửi DEMO | Có dùng khi điều kiện cha áp dụng | `demo_once.py; backtest.py` |
| `stop_loss.mode` | Đã có | Sửa/lưu được | Dùng trong tính SL ban đầu theo mode FIXED/STRUCTURE/ATR; không phải trailing | Có dùng theo mode SL và miền min/max | `demo_once.py; backtest.py` |
| `stop_loss.fixed_price_units` | Đã có | Sửa/lưu được | Dùng trong tính SL ban đầu theo mode FIXED/STRUCTURE/ATR; không phải trailing | Có dùng theo mode SL và miền min/max | `demo_once.py; backtest.py` |
| `stop_loss.atr_timeframe` | Đã có | Sửa/lưu được | Dùng trong tính SL ban đầu theo mode FIXED/STRUCTURE/ATR; không phải trailing | Có dùng theo mode SL và miền min/max | `demo_once.py; backtest.py` |
| `stop_loss.atr_period` | Đã có | Sửa/lưu được | Dùng trong tính SL ban đầu theo mode FIXED/STRUCTURE/ATR; không phải trailing | Có dùng theo mode SL và miền min/max | `demo_once.py; backtest.py` |
| `stop_loss.atr_multiplier` | Đã có | Sửa/lưu được | Dùng trong tính SL ban đầu theo mode FIXED/STRUCTURE/ATR; không phải trailing | Có dùng theo mode SL và miền min/max | `demo_once.py; backtest.py` |
| `stop_loss.structure_timeframe` | Đã có | Sửa/lưu được | Dùng trong tính SL ban đầu theo mode FIXED/STRUCTURE/ATR; không phải trailing | Có dùng theo mode SL và miền min/max | `demo_once.py; backtest.py` |
| `stop_loss.structure_lookback` | Đã có | Sửa/lưu được | Dùng trong tính SL ban đầu theo mode FIXED/STRUCTURE/ATR; không phải trailing | Có dùng theo mode SL và miền min/max | `demo_once.py; backtest.py` |
| `stop_loss.structure_buffer_price_units` | Đã có | Sửa/lưu được | Dùng trong tính SL ban đầu theo mode FIXED/STRUCTURE/ATR; không phải trailing | Có dùng theo mode SL và miền min/max | `demo_once.py; backtest.py` |
| `stop_loss.min_price_units` | Đã có | Sửa/lưu được | Dùng trong tính SL ban đầu theo mode FIXED/STRUCTURE/ATR; không phải trailing | Có dùng theo mode SL và miền min/max | `demo_once.py; backtest.py` |
| `stop_loss.max_price_units` | Đã có | Sửa/lưu được | Dùng trong tính SL ban đầu theo mode FIXED/STRUCTURE/ATR; không phải trailing | Có dùng theo mode SL và miền min/max | `demo_once.py; backtest.py` |
| `take_profit.mode` | Một phần | Sửa/lưu được | Chỉ FIXED/RR; ZRSI_DYNAMIC bị từ chối | FIXED/RR/ZRSI_DYNAMIC | `demo_once.py; backtest.py` |
| `take_profit.fixed_price_units` | Đã có | Sửa/lưu được | Tính TP ban đầu theo FIXED hoặc RR | Có dùng theo mode TP | `demo_once.py; backtest.py` |
| `take_profit.rr_ratio` | Đã có | Sửa/lưu được | Tính TP ban đầu theo FIXED hoặc RR | Có dùng theo mode TP | `demo_once.py; backtest.py` |
| `take_profit.dynamic.near_tp_distance` | Chỉ mô phỏng | Sửa/lưu được | Chưa có quản lý TP động broker | Có dùng khi TP ZRSI_DYNAMIC bật | `backtest.py` |
| `take_profit.dynamic.extend_use_z` | Chỉ mô phỏng | Sửa/lưu được | Chưa có quản lý TP động broker | Có dùng khi TP ZRSI_DYNAMIC bật | `backtest.py` |
| `take_profit.dynamic.extend_use_rsi` | Chỉ mô phỏng | Sửa/lưu được | Chưa có quản lý TP động broker | Có dùng khi TP ZRSI_DYNAMIC bật | `backtest.py` |
| `take_profit.dynamic.extend_logic` | Chỉ mô phỏng | Sửa/lưu được | Chưa có quản lý TP động broker | Có dùng khi TP ZRSI_DYNAMIC bật | `backtest.py` |
| `take_profit.dynamic.exit_z_reverse_delta` | Chỉ mô phỏng | Sửa/lưu được | Chưa có quản lý TP động broker | Có dùng khi TP ZRSI_DYNAMIC bật | `backtest.py` |
| `take_profit.dynamic.exit_rsi_reverse_delta` | Chỉ mô phỏng | Sửa/lưu được | Chưa có quản lý TP động broker | Có dùng khi TP ZRSI_DYNAMIC bật | `backtest.py` |
| `take_profit.dynamic.lock_sl_at_original_tp` | Chỉ mô phỏng | Sửa/lưu được | Chưa có quản lý TP động broker | Có dùng khi TP ZRSI_DYNAMIC bật | `backtest.py` |
| `take_profit.dynamic.lock_profit_buffer` | Chỉ mô phỏng | Sửa/lưu được | Chưa có quản lý TP động broker | Có dùng khi TP ZRSI_DYNAMIC bật | `backtest.py` |
| `take_profit.dynamic.max_extension_price_units` | Chỉ mô phỏng | Sửa/lưu được | Chưa có quản lý TP động broker | Có dùng khi TP ZRSI_DYNAMIC bật | `backtest.py` |
| `take_profit.dynamic.max_extension_minutes` | Chỉ mô phỏng | Sửa/lưu được | Chưa có quản lý TP động broker | Có dùng khi TP ZRSI_DYNAMIC bật | `backtest.py` |
| `take_profit.dynamic.emergency_server_tp_enabled` | Chỉ mô phỏng | Sửa/lưu được | Chưa có quản lý TP động broker | Có dùng khi TP ZRSI_DYNAMIC bật | `backtest.py` |
| `take_profit.dynamic.emergency_server_tp_price_units` | Chỉ mô phỏng | Sửa/lưu được | Chưa có quản lý TP động broker | Có dùng khi TP ZRSI_DYNAMIC bật | `backtest.py` |
| `management.breakeven_enabled` | Chỉ mô phỏng | Sửa/lưu được | Không có vòng quản lý broker; các cờ bật vẫn qua được profile guard | Có BE/partial/trailing/tighten theo cờ và mode; ZRSI_ASSIST cần dynamic TP | `backtest.py; demo_once.py` |
| `management.breakeven_trigger_rr` | Chỉ mô phỏng | Sửa/lưu được | Không có vòng quản lý broker; các cờ bật vẫn qua được profile guard | Có BE/partial/trailing/tighten theo cờ và mode; ZRSI_ASSIST cần dynamic TP | `backtest.py; demo_once.py` |
| `management.breakeven_offset_price_units` | Chỉ mô phỏng | Sửa/lưu được | Không có vòng quản lý broker; các cờ bật vẫn qua được profile guard | Có BE/partial/trailing/tighten theo cờ và mode; ZRSI_ASSIST cần dynamic TP | `backtest.py; demo_once.py` |
| `management.partial_close_enabled` | Chỉ mô phỏng | Sửa/lưu được | Không có vòng quản lý broker; các cờ bật vẫn qua được profile guard | Có BE/partial/trailing/tighten theo cờ và mode; ZRSI_ASSIST cần dynamic TP | `backtest.py; demo_once.py` |
| `management.partial_close_at_rr` | Chỉ mô phỏng | Sửa/lưu được | Không có vòng quản lý broker; các cờ bật vẫn qua được profile guard | Có BE/partial/trailing/tighten theo cờ và mode; ZRSI_ASSIST cần dynamic TP | `backtest.py; demo_once.py` |
| `management.partial_close_percent` | Chỉ mô phỏng | Sửa/lưu được | Không có vòng quản lý broker; các cờ bật vẫn qua được profile guard | Có BE/partial/trailing/tighten theo cờ và mode; ZRSI_ASSIST cần dynamic TP | `backtest.py; demo_once.py` |
| `management.trailing_enabled` | Chỉ mô phỏng | Sửa/lưu được | Không có vòng quản lý broker; các cờ bật vẫn qua được profile guard | Có BE/partial/trailing/tighten theo cờ và mode; ZRSI_ASSIST cần dynamic TP | `backtest.py; demo_once.py` |
| `management.trailing_mode` | Chỉ mô phỏng | Sửa/lưu được | Không có vòng quản lý broker; các cờ bật vẫn qua được profile guard | Có BE/partial/trailing/tighten theo cờ và mode; ZRSI_ASSIST cần dynamic TP | `backtest.py; demo_once.py` |
| `management.trailing_atr_multiplier` | Chỉ mô phỏng | Sửa/lưu được | Không có vòng quản lý broker; các cờ bật vẫn qua được profile guard | Có BE/partial/trailing/tighten theo cờ và mode; ZRSI_ASSIST cần dynamic TP | `backtest.py; demo_once.py` |
| `management.trailing_structure_lookback` | Chỉ mô phỏng | Sửa/lưu được | Không có vòng quản lý broker; các cờ bật vẫn qua được profile guard | Có BE/partial/trailing/tighten theo cờ và mode; ZRSI_ASSIST cần dynamic TP | `backtest.py; demo_once.py` |
| `management.trailing_step_price_units` | Chỉ mô phỏng | Sửa/lưu được | Không có vòng quản lý broker; các cờ bật vẫn qua được profile guard | Có BE/partial/trailing/tighten theo cờ và mode; ZRSI_ASSIST cần dynamic TP | `backtest.py; demo_once.py` |
| `management.sl_tighten_mode` | Chỉ mô phỏng | Sửa/lưu được | Không có vòng quản lý broker; các cờ bật vẫn qua được profile guard | Có BE/partial/trailing/tighten theo cờ và mode; ZRSI_ASSIST cần dynamic TP | `backtest.py; demo_once.py` |
| `sessions.timezone` | Một phần | Sửa/lưu được | BROKER/UTC; UTC cần offset broker; các chuỗi khác bị từ chối lúc arm | BROKER/UTC; các chuỗi khác bị từ chối | `demo_once.py; backtest.py` |
| `sessions.session1_enabled` | Đã có | Sửa/lưu được | Kiểm ngày và hai cửa sổ phiên theo timezone; không phải giờ máy nếu BROKER | Có lọc ngày/phiên | `demo_once.py; backtest.py` |
| `sessions.session1_start` | Đã có | Sửa/lưu được | Kiểm ngày và hai cửa sổ phiên theo timezone; không phải giờ máy nếu BROKER | Có lọc ngày/phiên | `demo_once.py; backtest.py` |
| `sessions.session1_end` | Đã có | Sửa/lưu được | Kiểm ngày và hai cửa sổ phiên theo timezone; không phải giờ máy nếu BROKER | Có lọc ngày/phiên | `demo_once.py; backtest.py` |
| `sessions.session2_enabled` | Đã có | Sửa/lưu được | Kiểm ngày và hai cửa sổ phiên theo timezone; không phải giờ máy nếu BROKER | Có lọc ngày/phiên | `demo_once.py; backtest.py` |
| `sessions.session2_start` | Đã có | Sửa/lưu được | Kiểm ngày và hai cửa sổ phiên theo timezone; không phải giờ máy nếu BROKER | Có lọc ngày/phiên | `demo_once.py; backtest.py` |
| `sessions.session2_end` | Đã có | Sửa/lưu được | Kiểm ngày và hai cửa sổ phiên theo timezone; không phải giờ máy nếu BROKER | Có lọc ngày/phiên | `demo_once.py; backtest.py` |
| `sessions.monday` | Đã có | Sửa/lưu được | Kiểm ngày và hai cửa sổ phiên theo timezone; không phải giờ máy nếu BROKER | Có lọc ngày/phiên | `demo_once.py; backtest.py` |
| `sessions.tuesday` | Đã có | Sửa/lưu được | Kiểm ngày và hai cửa sổ phiên theo timezone; không phải giờ máy nếu BROKER | Có lọc ngày/phiên | `demo_once.py; backtest.py` |
| `sessions.wednesday` | Đã có | Sửa/lưu được | Kiểm ngày và hai cửa sổ phiên theo timezone; không phải giờ máy nếu BROKER | Có lọc ngày/phiên | `demo_once.py; backtest.py` |
| `sessions.thursday` | Đã có | Sửa/lưu được | Kiểm ngày và hai cửa sổ phiên theo timezone; không phải giờ máy nếu BROKER | Có lọc ngày/phiên | `demo_once.py; backtest.py` |
| `sessions.friday` | Đã có | Sửa/lưu được | Kiểm ngày và hai cửa sổ phiên theo timezone; không phải giờ máy nếu BROKER | Có lọc ngày/phiên | `demo_once.py; backtest.py` |
| `sessions.saturday` | Đã có | Sửa/lưu được | Kiểm ngày và hai cửa sổ phiên theo timezone; không phải giờ máy nếu BROKER | Có lọc ngày/phiên | `demo_once.py; backtest.py` |
| `sessions.sunday` | Đã có | Sửa/lưu được | Kiểm ngày và hai cửa sổ phiên theo timezone; không phải giờ máy nếu BROKER | Có lọc ngày/phiên | `demo_once.py; backtest.py` |
| `sessions.weekend_close_enabled` | Chưa có | Sửa/lưu được | Chỉ lưu, không có consumer thực thi | Cũng không có consumer đóng trước cuối tuần | `config_schema.py` |
| `sessions.weekend_close_minutes_before` | Chưa có | Sửa/lưu được | Chỉ lưu, không có consumer thực thi | Cũng không có consumer đóng trước cuối tuần | `config_schema.py` |
| `news.enabled` | Chưa có | Sửa/lưu được | Bật news bị chặn: NEWS_GUARD_UNAVAILABLE; không có lịch tin | Bật news bị từ chối vì thiếu lịch sử tin | `demo_once.py; backtest.py` |
| `news.minutes_before` | Chưa có | Sửa/lưu được | Bật news bị chặn: NEWS_GUARD_UNAVAILABLE; không có lịch tin | Bật news bị từ chối vì thiếu lịch sử tin | `demo_once.py; backtest.py` |
| `news.minutes_after` | Chưa có | Sửa/lưu được | Bật news bị chặn: NEWS_GUARD_UNAVAILABLE; không có lịch tin | Bật news bị từ chối vì thiếu lịch sử tin | `demo_once.py; backtest.py` |
| `news.high_impact_only` | Chưa có | Sửa/lưu được | Bật news bị chặn: NEWS_GUARD_UNAVAILABLE; không có lịch tin | Bật news bị từ chối vì thiếu lịch sử tin | `demo_once.py; backtest.py` |
| `costs.max_spread_price_units` | Lỗi lệch phạm vi | Sửa/lưu được | Có spread/deviation/RR và phí dự phòng; trần commission là dự phòng, không đo mức phí tương lai | Nhóm costs trong profile không được đọc; chỉ spread/commission nhập tay được tính. B06: siết trần vẫn cùng giao dịch | `demo_once.py; backtest.py` |
| `costs.max_commission_per_lot` | Lỗi lệch phạm vi | Sửa/lưu được | Có spread/deviation/RR và phí dự phòng; trần commission là dự phòng, không đo mức phí tương lai | Nhóm costs trong profile không được đọc; chỉ spread/commission nhập tay được tính. B06: siết trần vẫn cùng giao dịch | `demo_once.py; backtest.py` |
| `costs.min_net_rr` | Lỗi lệch phạm vi | Sửa/lưu được | Có spread/deviation/RR và phí dự phòng; trần commission là dự phòng, không đo mức phí tương lai | Nhóm costs trong profile không được đọc; chỉ spread/commission nhập tay được tính. B06: siết trần vẫn cùng giao dịch | `demo_once.py; backtest.py` |
| `costs.max_slippage_points` | Lỗi lệch phạm vi | Sửa/lưu được | Có spread/deviation/RR và phí dự phòng; trần commission là dự phòng, không đo mức phí tương lai | Nhóm costs trong profile không được đọc; chỉ spread/commission nhập tay được tính. B06: siết trần vẫn cùng giao dịch | `demo_once.py; backtest.py` |
| `execution.magic` | Có điều kiện | Sửa/lưu được | Phải khớp InpMagic ở EA; đổi profile không tự đổi Inputs EA | Dữ liệu cấu hình của lần replay, không điều khiển MT5 | `demo_once.py` |
| `execution.order_comment` | Chưa có | Sửa/lưu được | Bị bỏ qua; EA dùng X1:attempt để đối chiếu | Không có consumer cho comment tùy chỉnh | `config_schema.py; ../../mql5/XAUPY_DemoOnce.mqh` |
| `execution.max_retry_count` | Khóa cố định | Khóa | max_retry=0; demo_only=true; allow_real=false; không phải tùy chọn người dùng tự quyết | Replay không cần quyền giao dịch broker | `config_schema.py` |
| `execution.demo_only` | Khóa cố định | Khóa | max_retry=0; demo_only=true; allow_real=false; không phải tùy chọn người dùng tự quyết | Replay không cần quyền giao dịch broker | `config_schema.py` |
| `execution.allow_real_account` | Khóa cố định | Khóa | max_retry=0; demo_only=true; allow_real=false; không phải tùy chọn người dùng tự quyết | Replay không cần quyền giao dịch broker | `config_schema.py` |
| `safety.never_widen_sl` | Khóa cố định | Khóa | Luôn true; stale/server SL có guard cứng. never_widen không tạo ra vòng quản lý SL broker | Replay giữ nguyên tắc bảo vệ; không được phép thay cờ false | `config_schema.py; demo_once.py; backtest.py` |
| `safety.require_server_sl` | Khóa cố định | Khóa | Luôn true; stale/server SL có guard cứng. never_widen không tạo ra vòng quản lý SL broker | Replay giữ nguyên tắc bảo vệ; không được phép thay cờ false | `config_schema.py; demo_once.py; backtest.py` |
| `safety.block_on_stale_market_data` | Khóa cố định | Khóa | Luôn true; stale/server SL có guard cứng. never_widen không tạo ra vòng quản lý SL broker | Replay giữ nguyên tắc bảo vệ; không được phép thay cờ false | `config_schema.py; demo_once.py; backtest.py` |
| `logging.csv_enabled` | Đã có | Sửa/lưu được | CSV log / decision trace được đọc tại server | Không phải một tham số tạo lợi nhuận | `server.py` |
| `logging.decision_trace_enabled` | Đã có | Sửa/lưu được | CSV log / decision trace được đọc tại server | Không phải một tham số tạo lợi nhuận | `server.py` |

## Hồ sơ đi kèm

- [Danh sách chức năng dạng CSV](FEATURE_FUNCTION_AUDIT_20260928.csv).
- [133 thông số dạng CSV](CONFIG_FUNCTION_AUDIT_20260928.csv).
- [Bản đọc có tìm kiếm và bộ lọc](FEATURE_FUNCTION_AUDIT_20260928.html).
- Bằng chứng cục bộ: `artifacts/feature-audit-20260928/`: `control-inventory.json/csv`, `python-tests.log`, `contracts.log`, `desktop-interactions.log`, `ui-characterization.json`, `backend-characterization.json`, `live-status.json`, `broker-fill-verification.json`.
- Probe tái hiện: `probe/Program.cs`, `backend_probe.py`, `cost_probe.py`; state test dùng thư mục riêng, không kết nối MT5. `broker_read.py` chỉ đối chiếu đọc MT5, không chứa API gửi/sửa/đóng lệnh.
- Các task trước ghi DONE mô tả phạm vi từng đợt (có đợt read-only/simulation), không phải chứng nhận toàn bộ chức năng hiển thị trên UI đã dùng được.
