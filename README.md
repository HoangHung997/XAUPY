# XAUPY

XAUPY là hệ thống giao dịch XAUUSD theo kiến trúc ba lớp:

1. Avalonia / C# Desktop — giao diện Control Center.
2. Python Engine — chiến lược, nghiên cứu, backtest và tối ưu.
3. MQL5 Bridge EA — dữ liệu MT5, execution và lớp an toàn broker-side.

Trạng thái hiện tại: TASK XAUPY-004 DONE. XAUPY-005/006/007 vẫn PLANNED và chưa bắt đầu.

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

## Task 004 đã hoàn thành

- schema profile versioned;
- 133 tham số canonical;
- Direction/Pullback/Trigger TF độc lập;
- exact TF options: M1, M3, M5, M15, M30, H1, H2, H4;
- JSON profile validation + atomic save/load;
- MT5 .set import/export;
- bảo toàn unknown keys, comments, order, encoding, line endings và optimizer suffix;
- packaged tools/xaupy-config.exe;
- Engine IPC: config_schema_get, config_defaults_get, config_validate;
- baseline JSON/.set được tạo sẵn trong full build;
- real-account unlock và các safety unlock bị validator từ chối;
- CI final: 46 Python tests PASS, C# 7/7 PASS, .NET 0 warnings/0 errors, MetaEditor 0 errors/0 warnings.

Xem evidence đầy đủ trong docs/IMPLEMENTATION_TASKS.md.
