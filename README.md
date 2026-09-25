# XAUPY

XAUPY là hệ thống giao dịch XAUUSD theo kiến trúc ba lớp:

1. Avalonia / C# Desktop — Control Center.
2. Python Engine — chiến lược, cấu hình, nghiên cứu, backtest và tối ưu.
3. MQL5 Bridge EA — dữ liệu MT5, execution và lớp an toàn broker-side.

Trạng thái hiện tại: TASK XAUPY-006 — Full Configuration tab. XAUPY-007 vẫn PLANNED và chưa bắt đầu.

## Tài liệu bắt buộc

- [Product spec](docs/PRODUCT_SPEC.md)
- [Implementation tasks](docs/IMPLEMENTATION_TASKS.md)
- [Overview UI spec](docs/OVERVIEW_UI_SPEC.md)
- [Overview smoke test](docs/TASK005_OVERVIEW_TEST.md)
- [Configuration UI spec](docs/CONFIGURATION_UI_SPEC.md)
- [Configuration UI smoke test](docs/TASK006_CONFIGURATION_TEST.md)
- [Canonical config/profile spec](docs/CONFIG_PROFILE_SPEC.md)
- [IPC protocol](docs/IPC_PROTOCOL.md)
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


## Task 006 đang triển khai

Configuration tab Avalonia được xây theo schema canonical thay vì hard-code từng tham số.

Mục tiêu:

- render đủ 133 field;
- search/filter tham số;
- exact TF M1/M3/M5/M15/M30/H1/H2/H4;
- Defaults / Revert Active / Validate / Apply Active;
- JSON load/save;
- MT5 .set import/export qua xaupy-config.exe;
- locked safety fields không chỉnh được trong UI và vẫn bị Python validator bảo vệ;
- Overview phản ánh active profile sau Apply;
- execution tiếp tục bị khóa.
