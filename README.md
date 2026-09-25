# XAUPY

XAUPY là hệ thống giao dịch XAUUSD theo kiến trúc ba lớp:

1. Avalonia / C# Desktop — Control Center.
2. Python Engine — chiến lược, cấu hình, nghiên cứu, backtest và tối ưu.
3. MQL5 Bridge EA — dữ liệu MT5, execution và lớp an toàn broker-side.

Trạng thái hiện tại: TASK XAUPY-008 ACTIVE trên nhánh `task/008-strategy-monitoring-tabs`. XAUPY-001–007 đã DONE.

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
- [UI reference](docs/ui-reference/README.md)

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


## Task 008 đang triển khai

Phạm vi:

- tab Chiến lược realtime đọc typed StrategySnapshot từ Python Engine;
- tab Giám sát dùng quote/snapshot/bar thật từ MT5 Bridge/Overview;
- chart chỉ tích lũy snapshot mới trong phiên, không backfill giả;
- state/indicator/warm-up/signal evidence hiển thị read-only;
- backend Session/News/CPU/RAM chưa có được ghi rõ unavailable;
- execution tiếp tục hard-locked.
