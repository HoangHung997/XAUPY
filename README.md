# XAUPY

XAUPY là hệ thống giao dịch XAUUSD theo kiến trúc ba lớp:

1. Avalonia / C# Desktop — giao diện Control Center.
2. Python Engine — chiến lược, nghiên cứu, backtest và tối ưu.
3. MQL5 Bridge EA — dữ liệu MT5, execution và lớp an toàn broker-side.

Trạng thái hiện tại: TASK XAUPY-003 — MT5 Bridge Data Channel & Execution Guardian.

## Tài liệu bắt buộc

- [Đặc tả sản phẩm](docs/PRODUCT_SPEC.md)
- [Kế hoạch triển khai theo task](docs/IMPLEMENTATION_TASKS.md)
- [IPC protocol](docs/IPC_PROTOCOL.md)
- [Task 003 MT5 Bridge](docs/TASK003_MT5_BRIDGE.md)
- [Task 003 demo test](docs/TASK003_MT5_DEMO_TEST.md)
- [UI reference](docs/ui-reference/README.md)

## Nguyên tắc triển khai

- Chỉ làm một task tại một thời điểm.
- Task chỉ DONE khi code, test, GitHub CI và build artifact đều hoàn tất.
- Mọi task có UI/bridge phải có Windows x64 full build trước khi giao người dùng test.
- Python là strategy authority; MQL5 Bridge là broker/safety boundary.
- Task 003 chỉ truyền dữ liệu và đánh giá guardian. Execution bị khóa cứng.

## Task 003

- MQL5 Bridge EA kết nối localhost qua Socket API.
- Snapshot account/symbol/broker rules + 8 timeframe M1/M3/M5/M15/M30/H1/H2/H4.
- Python Engine lưu bridge state và chiếu health sang Avalonia.
- Desktop hiển thị MT5 Bridge CONNECTED/WAITING và guardian.
- EA không chứa OrderSend, OrderSendAsync hoặc CTrade.
- GitHub CI dùng MetaEditor thật để compile .mq5 thành .ex5.
