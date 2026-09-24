# XAUPY

XAUPY là hệ thống giao dịch XAUUSD theo kiến trúc ba lớp:

1. Avalonia / C# Desktop — giao diện Control Center.
2. Python Engine — chiến lược, nghiên cứu, backtest và tối ưu.
3. MQL5 Bridge EA — dữ liệu MT5, execution và lớp an toàn broker-side.

Trạng thái hiện tại: TASK XAUPY-002 — Versioned local IPC & process lifecycle.

## Tài liệu bắt buộc

- [Đặc tả sản phẩm](docs/PRODUCT_SPEC.md)
- [Kế hoạch triển khai theo task](docs/IMPLEMENTATION_TASKS.md)
- [IPC protocol](docs/IPC_PROTOCOL.md)
- [UI reference](docs/ui-reference/README.md)

## Nguyên tắc triển khai

- Chỉ làm một task tại một thời điểm.
- Task chỉ DONE khi code, test, GitHub CI và build artifact đều hoàn tất.
- Task có UI/build phải tạo artifact Windows x64 đầy đủ trước khi chuyển task tiếp theo.
- Python là strategy authority; MQL5 Bridge sau này vẫn là broker safety authority.
- Real trading tiếp tục bị khóa trong Task 002.

## Task 002

Task 002 triển khai IPC v1 qua TCP loopback giữa Avalonia Desktop và Python Engine:

- chỉ bind localhost;
- JSON Lines có schema version;
- request_id để correlation/idempotency ở các task sau;
- hello/heartbeat/shutdown lifecycle;
- Desktop tự khởi động Python Engine đóng gói sẵn;
- reconnect và restart khi engine mất kết nối;
- Python Engine build thành xaupy-engine.exe bằng PyInstaller;
- GitHub CI kiểm tra contract, heartbeat, reconnect và executable smoke test.
