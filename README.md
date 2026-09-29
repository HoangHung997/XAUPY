> **1.0.0-rc1 READY_FOR_USER_TEST** — [Verified delivery](docs/FIRST_RELEASE_DELIVERY_20260929.md) · [Download release](https://github.com/HoangHung997/XAUPY/releases/tag/v1.0.0-rc1). Exact application source: `a1abc91d9b2d43888a4471bd28c6b6f2e8af0e0f`.

# XAUPY — 1.0.0 RC1

Nhánh phát hành riêng: `release/1.0-completion-20260929`. Xem [thay đổi và phạm vi kiểm](docs/FIRST_RELEASE_20260929.md), [hướng dẫn tải/test](docs/FIRST_RELEASE_USER_GUIDE.md) và [ma trận 172 chức năng](docs/FIRST_RELEASE_FEATURE_MATRIX.csv). Bằng chứng các phiên bản dưới đây là lịch sử, không thay cho CI/artifact của nhánh RC1. Bản đầu tiên để người dùng nghiệm thu thực tế; không tự bật giao dịch hoặc gửi lệnh.

# XAUPY

Đợt tiếp theo: **0.17.0-demo1** bổ sung một lần vào lệnh DEMO theo yêu cầu người dùng, tối đa 0,01 lot, có SL/TP và chỉ theo tín hiệu mới sau khi kích hoạt. Khóa giao dịch chung, tài khoản thật và nút lệnh mô phỏng vẫn giữ nguyên. Đây là ngoại lệ kiểm thử vào lệnh riêng, chưa phải bật hệ thống tự động giao dịch đầy đủ. Xem [phạm vi và nghiệm thu một lệnh DEMO](docs/DEMO_ONE_SHOT_ACCEPTANCE.md); bằng chứng RC2 dưới đây được giữ riêng.

XAUPY là hệ thống giao dịch XAUUSD theo kiến trúc ba lớp:

1. Avalonia / C# Desktop — Control Center.
2. Python Engine — chiến lược, cấu hình, nghiên cứu, backtest và tối ưu.
3. MQL5 Bridge EA — dữ liệu MT5, execution và lớp an toàn broker-side.

Trạng thái tiếp quản 28/09/2026: Task 013–015 hoàn thành trên bản Windows 0.16.0-rc1. Bản 0.16.0-rc2 bổ sung tải lịch sử MT5 vào ổ đĩa, phân tích RSI/Z theo tick quan sát được và chỉnh sửa cấu hình chiến lược. RC2 tại `7f968266` đã qua CI, bộ cài và kết nối MT5 thực; bản chỉnh giao diện tiếp theo tại `5dc7a6e` cũng đã qua CI, xác minh gói độc lập và đạt 19/19 kiểm tra với MT5 thật trên đúng bản tải về. Task 016 vẫn ACTIVE, chưa chứng nhận khớp UI 100%. Xem [nghiệm thu RC2](docs/TASK_016_UAT_AUDIT.md), [bằng chứng RC1](docs/TASK016_RELEASE_ACCEPTANCE.md) và [đối chiếu giao diện](docs/UI_REFERENCE_PARITY_AUDIT.md).

## Tài liệu bắt buộc

- [Product spec](docs/PRODUCT_SPEC.md)
- [Implementation tasks](docs/IMPLEMENTATION_TASKS.md)
- [Overview UI spec](docs/OVERVIEW_UI_SPEC.md)
- [Overview smoke test](docs/TASK005_OVERVIEW_TEST.md)
- [Configuration UI spec](docs/CONFIGURATION_UI_SPEC.md)
- [Configuration UI smoke test](docs/TASK006_CONFIGURATION_TEST.md)
- [Canonical config/profile spec](docs/CONFIG_PROFILE_SPEC.md)
- [IPC protocol](docs/IPC_PROTOCOL.md)
- [Task 007 strategy spec](docs/TASK007_STRATEGY_ENGINE.md)
- [Task 007 acceptance](docs/TASK007_STRATEGY_TEST.md)
- [Strategy + Monitoring UI spec](docs/STRATEGY_MONITORING_UI_SPEC.md)
- [Task 008 acceptance](docs/TASK008_STRATEGY_MONITORING_TEST.md)
- [Task 009 Orders & Positions spec](docs/TASK009_ORDERS_POSITIONS_SPEC.md)
- [Task 009 acceptance](docs/TASK009_ORDERS_POSITIONS_TEST.md)
- [Task 010 structured Journal spec](docs/TASK010_STRUCTURED_LOGGING_JOURNAL_SPEC.md)
- [Task 010 acceptance](docs/TASK010_STRUCTURED_LOGGING_JOURNAL_TEST.md)
- [Task 011 Backtest parity spec](docs/TASK011_BACKTEST_PARITY_SPEC.md)
- [Task 011 acceptance](docs/TASK011_BACKTEST_PARITY_TEST.md)
- [Task 012 Optimizer + Walk-Forward spec](docs/TASK012_OPTIMIZER_WALK_FORWARD_SPEC.md)
- [Task 012 acceptance](docs/TASK012_OPTIMIZER_WALK_FORWARD_TEST.md)
- [UI reference](docs/ui-reference/README.md)
- [Lịch sử đầy đủ theo khả năng MT5 và luồng tick](docs/MT5_HISTORY_AND_TICKS.md)
- [RSI/Z intrabar: ngưỡng, cực trị và xác nhận](docs/INTRABAR_THRESHOLD_LATCH.md)
- [Kết quả nghiên cứu RSI/Z trên 598.794 nến](docs/RSI_Z_CALIBRATION_20260928.md)
- [Nghiệm thu RC2](docs/TASK_016_UAT_AUDIT.md)

## Nguyên tắc triển khai

- Chỉ làm một task tại một thời điểm.
- Task chỉ DONE khi code, tests, GitHub CI và full Windows build đều hoàn tất.
- Overview chỉ hiển thị dữ liệu thật từ MT5 Bridge / Python Engine / canonical config.
- Không dùng số liệu mockup làm dữ liệu runtime.
- Những backend chưa tồn tại phải hiện rõ chưa chạy/chưa triển khai.
- Execution vẫn khóa.

## Task 005 đã hoàn thành

Overview Avalonia hiện có:

- XAUUSD BID/ASK/spread;
- Desktop / Python Engine / MT5 Bridge status;
- balance/equity/free margin/account mode;
- live BID-history chart từ dữ liệu Bridge thật;
- canonical Direction/Pullback/Trigger profile summary;
- real position/order counters;
- quick local event log;
- placeholder rõ ràng cho các tab chưa tới task;
- stale MT5 data bị xoá khỏi Overview thay vì tiếp tục hiển thị như dữ liệu live.

Visual source-of-truth:

docs/ui-reference/Tab Tổng Quan.png

Final CI:

- Python tests 55/55 PASS;
- C# IPC + Overview parser 17/17 PASS;
- Avalonia/.NET 0 warnings / 0 errors;
- MetaEditor MT5 Bridge regression 0 errors / 0 warnings;
- full Windows x64 artifact produced and independently inspected.

Xem bằng chứng đầy đủ trong docs/IMPLEMENTATION_TASKS.md.


## Task 006 đã hoàn thành

Configuration tab Avalonia được xây theo schema canonical thay vì hard-code từng tham số.

Đã hoàn thành:

- render đủ 133 field theo schema Python;
- search/filter tham số;
- exact TF M1/M3/M5/M15/M30/H1/H2/H4;
- Defaults / Revert Active / Validate / Apply Active;
- active-profile lifecycle do Python Engine quản lý;
- JSON load/save;
- MT5 .set import/export qua xaupy-config.exe;
- locked safety fields không chỉnh được trong UI và vẫn bị Python validator bảo vệ;
- Overview phản ánh active profile sau Apply;
- execution tiếp tục bị khóa;
- final CI: 66 Python tests PASS, 23 C# checks PASS, Avalonia/.NET 0 warnings / 0 errors, MetaEditor 0 errors / 0 warnings.


## Task 007 đã hoàn thành

Phạm vi hiện tại:

- Python Strategy Engine Direction → Pullback → Trigger dùng closed bars thật từ Bridge;
- MA / RSI / Z-Score cùng optional ADX / ATR / Open filters;
- tích lũy lịch sử theo timestamp, không bịa historical bars;
- deterministic state machine và signal evidence;
- heartbeat/bridge acknowledgement có read-only strategy projection;
- profile/reconnect reset để không phát tín hiệu từ setup cũ;
- execution vẫn hard-locked, không có trade_intent hay OrderSend.

Xem chi tiết tại docs/TASK007_STRATEGY_ENGINE.md.

Final Task 007 evidence:

- 78/78 Python tests PASS;
- 23/23 C# IPC checks PASS;
- Avalonia Release build: 0 warnings / 0 errors;
- packaged Engine deterministic strategy/safety smoke: PASS;
- packaged Config regression smoke: PASS;
- MetaEditor Bridge regression: 0 errors / 0 warnings;
- verified Windows x64 artifact: XAUPY-Task007-win-x64.


## Task 008 đã hoàn thành

Phạm vi:

- tab Chiến lược realtime đọc typed StrategySnapshot từ Python Engine;
- tab Giám sát dùng quote/snapshot/bar thật từ MT5 Bridge/Overview;
- chart chỉ tích lũy snapshot mới trong phiên, không backfill giả;
- state/indicator/warm-up/signal evidence hiển thị read-only;
- backend Session/News/CPU/RAM chưa có được ghi rõ unavailable;
- execution tiếp tục hard-locked.


Final Task 008 evidence:

- 87/87 Python regression/source tests PASS;
- 33/33 C# IPC contract checks PASS;
- Avalonia Release build: 0 warnings / 0 errors;
- packaged Task 007 Engine strategy/safety regression smoke: PASS;
- packaged Config regression smoke: PASS;
- MetaEditor Bridge regression: 0 errors / 0 warnings;
- verified Windows x64 artifact: XAUPY-Task008-win-x64.


## Task 009 đã hoàn thành

Phạm vi:

- tab **Lệnh & Vị thế** bám ảnh `docs/ui-reference/Tab Lệnh & Vị thế.png`;
- đọc position, pending order và realized deal thật theo symbol + magic từ MT5;
- KPI open P/L, realized P/L, exposure và risk dựa trên server SL thật;
- stale market snapshot bị xoá dù Bridge heartbeat vẫn còn;
- các nút BUY/SELL/Close/Partial/BE/Trailing/Modify/Cancel chạy qua
  **guarded execution simulator**;
- explicit confirmation + DEMO-only + volume/ownership/max-position/server-SL/
  never-widen-SL guard;
- duplicate `intent_id` idempotent, conflict bị từ chối;
- broker execution vẫn hard-locked và `trade_intent` vẫn unsupported.

Final Task 009 evidence:

- 122/122 Python regression/source tests PASS;
- 42/42 C# IPC/order-book checks PASS;
- Avalonia Release build: 0 warnings / 0 errors;
- packaged Task 009 order-book/manual-simulation safety smoke: PASS;
- packaged Task 007 strategy/safety regression smoke: PASS;
- packaged Config regression smoke: PASS;
- MetaEditor Task 009 Bridge: 0 errors / 0 warnings;
- verified Windows x64 artifact: XAUPY-Task009-win-x64;
- direct build SHA-256: fcd3ec52ac23453605758573d2f07c176f61218cdcb159d61792a2303437b41a.



## Task 010 đã hoàn thành

Phạm vi:

- persistent structured journal schema v1 theo dạng append-only JSONL;
- replay/sequence continuation qua restart và bỏ qua dòng hỏng có đếm lỗi;
- bookmark sidecar persisted;
- CSV mirror tùy chọn theo `logging.csv_enabled`;
- log evidence cho MT5, EA Bridge, Python Engine, Strategy, Orders và Alerts;
- decision trace được deduplicate theo closed-bar/decision change, không log spam mỗi timer;
- heartbeat chỉ mang journal summary nhỏ;
- query/search/filter/date/bookmark qua IPC;
- tab **Nhật ký** full-width bám `docs/ui-reference/Tab Nhật Kí.png`;
- source filters đúng mockup, INFO/WARN/ERROR/DEBUG, search, date scope,
  log table, structured detail, summary, recent alerts, bookmarks và JSONL export;
- không hard-code message/số liệu mẫu từ ảnh;
- broker execution vẫn hard-locked.

Final Task 010 evidence:

- 146/146 Python regression/source tests PASS;
- 53/53 C# IPC/journal checks PASS;
- Avalonia Release build: 0 warnings / 0 errors;
- packaged Task 010 structured journal replay/bookmark smoke: PASS;
- packaged Task 009 execution-simulation regression smoke: PASS;
- packaged Task 007 strategy/safety regression smoke: PASS;
- packaged Config regression smoke: PASS;
- MetaEditor Bridge regression: 0 errors / 0 warnings;
- verified Windows x64 artifact: XAUPY-Task010-win-x64;
- branch direct build SHA-256:
  9cf6f5bb97f4328f0dcff0cb1d975d9cc6a66f253f978dd808d52d2d3b61eee8.

## Task 011 đã hoàn thành

Phạm vi:

- Backtest dùng đúng `StrategyEngine` live của Task 007, không có state machine riêng;
- dữ liệu đầu vào M1 JSON/CSV có metadata point/tick/volume + SHA-256 fingerprint;
- deterministic aggregation M1 → M3/M5/M15/M30/H1/H2/H4;
- next-bar MARKET entry, không look-ahead;
- conservative SL-first nếu cùng M1 bar chạm cả SL và TP;
- FIXED/STRUCTURE SL, FIXED/RR TP, fixed-lot/risk-percent sizing;
- risk/session/cooldown/daily guards, MAE/MFE, equity/drawdown;
- persisted run history + result_hash reproducible;
- Journal ghi BACKTEST_DATASET/BACKTEST_RUN evidence;
- tab **Backtest** bám `docs/ui-reference/Tab BackTest.png`;
- UI ghi rõ `M1 OHLC deterministic parity`, không claim Every tick;
- runtime không hard-code profit/chart/trade demo từ ảnh;
- broker execution vẫn hard-locked.

Final Task 011 evidence:

- 178/178 Python regression/source/backtest tests PASS;
- 63/63 C# IPC/Backtest checks PASS;
- Avalonia Release build: 0 warnings / 0 errors;
- packaged Task 011 deterministic Backtest parity/restart smoke: PASS;
- packaged Task 010 Journal regression smoke: PASS;
- packaged Task 009 execution-simulation regression smoke: PASS;
- packaged Task 007 strategy/safety regression smoke: PASS;
- packaged Config regression smoke: PASS;
- MetaEditor Bridge: 0 errors / 0 warnings;
- verified Windows x64 artifact: XAUPY-Task011-win-x64;
- branch direct ZIP SHA-256:
  59f5fc95ce8c4444a7ca2b707cf46f5078ec656e1019090dec0bdf43bbb266d9.

## Task 012 đã hoàn thành

Phạm vi:

- parameter sweep dùng chính Task 011 `BacktestEngine`, không có strategy riêng;
- canonical optimizer allow-list + validation/relevance/combination limit;
- deterministic `ROBUST_SCORE_V1`, optimizer hash/ranking độc lập worker order;
- background worker pool có progress/ETA/throughput và cooperative cancel;
- persisted optimizer history/result/delete + restart replay;
- heatmap chỉ tổng hợp candidate thật, không interpolation;
- Walk-Forward rolling/anchored với `selection_source=TRAIN_ONLY`;
- leakage guard bắt buộc `train_to < test_from`;
- out-of-sample aggregate/stability metrics;
- Journal evidence OPTIMIZER/WALK_FORWARD;
- tab **Tối ưu** bám `docs/ui-reference/Tab Tối Ưu.png`;
- mock CPU/RAM/Disk không được bịa; diagnostics thật thuộc Task014;
- runtime không hard-code profit/score/progress/heatmap demo từ ảnh;
- broker execution vẫn hard-locked.

Final Task 012 evidence:

- 225/225 Python regression/source/optimizer tests PASS;
- 74/74 C# IPC/Optimizer checks PASS;
- Avalonia Release build: 0 warnings / 0 errors;
- packaged Task 012 optimizer/walk-forward reproducibility/restart smoke: PASS;
- packaged Task 011/010/009/007/config regression smokes: PASS;
- MetaEditor Bridge: 0 errors / 0 warnings;
- verified Windows x64 artifact: XAUPY-Task012-win-x64;
- branch direct ZIP SHA-256:
  d821d039b1c2a74deb7ec87fb1cbd8c401e35e2a717e2cc0e9e50f1ebc0a9b91.

## Bản Windows 0.16.0-rc1 đã xác minh

- [Dynamic management và STOP_CONFIRM](docs/TASK013_DYNAMIC_MANAGEMENT_SPEC.md)
- [Công cụ và chẩn đoán](docs/TASK014_TOOLS_DIAGNOSTICS_SPEC.md)
- [Cài đặt và sao lưu/khôi phục](docs/TASK015_SETTINGS_RECOVERY_SPEC.md)
- [Build, installer và nghiệm thu](docs/TASK016_RELEASE_ACCEPTANCE.md)
- [Lịch sử nến thật EA → Python → Avalonia](docs/LIVE_HISTORY_SYNC.md)

Build trên Windows bằng `./scripts/build_windows.ps1`, với .NET 10,
Python/PyInstaller và MetaEditor. Bản portable nằm trong `dist/XAUPY-win-x64`.
Broker execution vẫn khóa; Task013 sử dụng mô phỏng deterministic.

MT5 cần cho phép địa chỉ `http://127.0.0.1` trong Tools → Options → Expert Advisors.
Socket sử dụng cổng 39421 riêng.

## Thay đổi trong Windows 0.16.0-rc2

- **Công cụ → Xuất / Nhập dữ liệu → Tải lịch sử MT5** tải nến đóng của 8 khung thời gian vào SQLite và CSV. Collector chạy trên tiến trình riêng để kết nối EA/ứng dụng tiếp tục phản hồi. Nút **Tiến độ** hiển thị thư mục kết quả, số nến và giới hạn từ terminal/provider.
- Bộ nhớ 256 nến cho giao diện và 4.096 nến cho chiến lược không còn là giới hạn của bản lưu lịch sử. Bản lưu trên đĩa không áp trần số nến của ứng dụng; vẫn phụ thuộc Max bars và dữ liệu MT5/broker cung cấp. Nến đang hình thành bị loại, timestamp gốc được giữ nguyên và manifest ghi độ phủ/khoảng trống.
- Sau khi MT5 báo Max bars 100.000.000, lần thu thập được cố định cho nghiên cứu có **598.794 nến đóng** trên M1/M3/M5/M15/M30/H1/H2/H4. Provider dừng trả thêm dữ liệu sau các lần thử lại; không khẳng định đã lấy toàn bộ lịch sử broker. Các lần tải sau có thể có thêm nến mới.
- EA gửi các lô tick có thứ tự, tối đa 1.000 tick mỗi gói. `heartbeat.tick_transport` cho biết luồng tick thực có đến Engine ngay cả khi đang dùng chế độ nến đóng. Mất kết nối, thiếu gói hoặc dữ liệu stale làm mất tính liên tục và reset setup.
- `trigger.confirm_closed_bar=true` vẫn là mặc định. Chỉ khi người dùng đặt `false`, chiến lược mới giữ ngưỡng RSI/Z đã chạm và cực trị quan sát được trong nến; xác nhận đảo chiều phải thuộc nến Trigger tiếp theo trong giới hạn tuổi tín hiệu. Không tự đổi profile đang chạy. Backtest M1 OHLC từ chối chế độ này vì không biết thứ tự tick thật.
- Tab Chiến lược có chỉnh sửa và lưu cấu hình, bảo toàn bản nháp khi heartbeat/reconnect; các thay đổi không xung đột từ nguồn khác được gộp, xung đột phải xử lý trước khi ghi đè. Broker execution vẫn khóa.

RC2 từ commit `7f968266` đã qua [CI 36359181671](https://github.com/HoangHung997/XAUPY/actions/runs/36359181671): 324 Python test, 102 kiểm tra C# contract, 51 kiểm tra giao diện, chín nhóm packaged smoke gồm 16 kiểm tra intrabar, cùng kiểm tra MT5/NumPy và vòng cài/gỡ bộ cài trên Windows CI. Bản build trên máy đạt 19/19 kiểm tra MT5 trước và sau Stop/Start, mỗi lần 16 mẫu; EA tự kết nối lại trong khoảng ba giây. Xem bằng chứng và phạm vi trong [báo cáo RC2](docs/TASK_016_UAT_AUDIT.md).

Bản CI tải về đã được đối chiếu toàn bộ 282 tệp và 281 SHA-256 trong manifest. ZIP và bộ cài nằm riêng ở `dist/rc2-ci/`; ứng dụng giải nén đã xác minh ở `dist/XAUPY-verified-rc2-win-x64/`. Chính bản CI này đã chạy với MT5 thật: 19/19 kiểm tra đạt qua 21 mẫu trong 20 giây, số gói tick tăng 50→70 và số tick tăng 232→429; EA và Engine đang chạy có SHA-256 trùng manifest. Desktop hiển thị READY và cả 10 trang đã được chụp kiểm tra riêng. Bản build tại máy và RC1 được giữ nguyên.

Build Windows RC2 cần .NET 10, MetaEditor, Python/PyInstaller và package chính thức `MetaTrader5==5.0.6231` cùng NumPy. `scripts/build_windows.ps1` kiểm tra dependency trong executable, chạy smoke intrabar và tạo tên mới `XAUPY-0.16.0-rc2-win-x64.zip`; Inno Setup tạo `XAUPY-0.16.0-rc2-Setup.exe` khi truyền `-Iscc`. Bản RC1 đã xác minh được giữ riêng.

### Đợt chỉnh giao diện RC2 tại `5dc7a6e`

Bản này bổ sung JSON tô màu và số dòng với trình nhập văn bản thật, tìm kiếm/định dạng/phím tắt, công tắc Cài Đặt có lưu trạng thái, ma trận Giám Sát có thêm khung đang sử dụng và đồng hồ chỉ báo theo dữ liệu thực. Các trang còn lại được căn lại bố cục, khoảng cách và kiểu điều khiển; trạng thái chờ tín hiệu không còn bị hiểu là mọi điều kiện đã đạt.

[CI 36361798910](https://github.com/HoangHung997/XAUPY/actions/runs/36361798910) của commit `5dc7a6ea1f4cafe50e9316028a19c797830457b9` đạt **324 Python, 102 C# contract, 76 kiểm tra giao diện và 16 intrabar**, cùng toàn bộ packaged smoke và vòng cài/đối chiếu hash/gỡ bộ cài trên Windows CI. Sau tải về, 282 tệp và 281 hash manifest đều khớp; executable đọc được MetaTrader5 5.0.6231 và NumPy 2.5.3.

Gói mới nằm riêng ở `dist/rc2-refined-ci/`, bản chạy đã xác minh ở `dist/XAUPY-verified-rc2-refined-win-x64/`; bằng chứng CI trong `artifacts/ci-rc2-refined-download/`. ZIP có SHA-256 `9216a86e2bbc82bca52a31b0d914f0f312483a7c04745e05605110df9e0ad5f5`; bộ cài có SHA-256 `18ccdd0f4a7f67bcf2eea4b85d1ec29ee26a755d41a0183f25be849a6307984d`. Bộ cài không chạy trên máy người dùng; các gói trước được giữ riêng.

Chính bản CI mới đạt **19/19 kiểm tra MT5 qua 21 mẫu trong 20 giây**: gói tick tăng **32→53**, số tick tăng **321→614**. EA đã cài và Engine đang chạy trùng hash manifest; execution vẫn khóa. Kết quả trong `artifacts/live-bridge-rc2-refined-ci.json` và `artifacts/rc2-refined-ci-live-summary.json`. Cả 10 trang native của bản này được chụp tại `artifacts/ui-audit-rc2-refined-ci/`; ảnh và kiểm tra kết nối không phải chứng nhận khớp UI 100%.
