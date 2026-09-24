# XAUPY

XAUPY là hệ thống giao dịch XAUUSD theo kiến trúc ba lớp:

1. Avalonia / C# Desktop — giao diện Control Center.
2. Python Engine — chiến lược, nghiên cứu, backtest và tối ưu.
3. MQL5 Bridge EA — dữ liệu MT5, execution và lớp an toàn broker-side.

Trạng thái hiện tại: TASK XAUPY-002 DONE. Task XAUPY-003 vẫn PLANNED và chưa bắt đầu.

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
- Real trading vẫn bị khóa.

## Task 002 đã hoàn thành

IPC v1 qua TCP loopback giữa Avalonia Desktop và Python Engine đã có:

- localhost-only;
- JSON Lines + schema_version=1;
- request_id correlation;
- hello/heartbeat/shutdown lifecycle;
- Desktop tự khởi động Python Engine đóng gói sẵn;
- reconnect và bounded restart;
- Python Engine đóng gói thành xaupy-engine.exe;
- GitHub CI kiểm tra protocol, heartbeat, reconnect, shutdown và executable smoke test;
- Windows x64 self-contained full build.

Xem bằng chứng đầy đủ trong docs/IMPLEMENTATION_TASKS.md.
