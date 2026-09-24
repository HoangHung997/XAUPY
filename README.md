# XAUPY

XAUPY là hệ thống giao dịch XAUUSD theo kiến trúc ba lớp:

1. Avalonia / C# Desktop — giao diện Control Center.
2. Python Engine — chiến lược, nghiên cứu, backtest và tối ưu.
3. MQL5 Bridge EA — dữ liệu MT5, execution và lớp an toàn broker-side.

Trạng thái hiện tại: TASK XAUPY-004 — Canonical configuration/profile + MT5 .set compatibility.

## Tài liệu bắt buộc

- [Đặc tả sản phẩm](docs/PRODUCT_SPEC.md)
- [Kế hoạch triển khai theo task](docs/IMPLEMENTATION_TASKS.md)
- [IPC protocol](docs/IPC_PROTOCOL.md)
- [Canonical config/profile spec](docs/CONFIG_PROFILE_SPEC.md)
- [Task 004 config smoke test](docs/TASK004_CONFIG_TEST.md)
- [Task 003 MT5 Bridge](docs/TASK003_MT5_BRIDGE.md)
- [UI reference](docs/ui-reference/README.md)

## Nguyên tắc triển khai

- Chỉ làm một task tại một thời điểm.
- Task chỉ DONE khi code, tests, GitHub CI và full build artifact đều hoàn tất.
- Mọi task có UI/backend phải có Windows x64 full build trước khi giao người dùng test.
- Python là canonical owner của profile/strategy configuration.
- Full Avalonia parameter editor thuộc Task 006.
- Execution vẫn khóa; Task 004 không thêm đường đặt lệnh.

## Task 004

- schema profile versioned;
- hơn 100 tham số canonical;
- Direction/Pullback/Trigger TF độc lập;
- exact TF options: M1, M3, M5, M15, M30, H1, H2, H4;
- JSON profile validation/atomic save;
- MT5 .set import/export;
- bảo toàn unknown keys/comments/order/encoding/optimizer suffix;
- packaged tools/xaupy-config.exe;
- Engine IPC: config_schema_get, config_defaults_get, config_validate;
- real-account unlock bị validator khóa.
