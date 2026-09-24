# XAUPY

XAUPY là hệ thống giao dịch XAUUSD theo kiến trúc ba lớp:

1. Avalonia / C# Desktop — Control Center.
2. Python Engine — chiến lược, cấu hình, nghiên cứu, backtest và tối ưu.
3. MQL5 Bridge EA — dữ liệu MT5, execution và lớp an toàn broker-side.

Trạng thái hiện tại: TASK XAUPY-005 — Overview tab.

## Tài liệu bắt buộc

- [Product spec](docs/PRODUCT_SPEC.md)
- [Implementation tasks](docs/IMPLEMENTATION_TASKS.md)
- [Overview UI spec](docs/OVERVIEW_UI_SPEC.md)
- [Overview smoke test](docs/TASK005_OVERVIEW_TEST.md)
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

## Task 005

Overview Avalonia triển khai các nhóm đã duyệt:

- XAUUSD BID/ASK/spread;
- Desktop / Python Engine / MT5 Bridge status;
- balance/equity/free margin/account mode;
- live BID history chart;
- configured Direction/Pullback/Trigger summary;
- real position/order counters;
- quick local event log;
- explicit placeholders cho các tab chưa tới task.

Visual source-of-truth:

docs/ui-reference/Tab Tổng Quan.png
