# XAUPY

XAUPY là hệ thống giao dịch XAUUSD theo kiến trúc ba lớp:

1. Avalonia / C# Desktop — giao diện Control Center.
2. Python Engine — chiến lược, nghiên cứu, backtest và tối ưu.
3. MQL5 Bridge EA — dữ liệu MT5, execution và lớp an toàn broker-side.

Trạng thái hiện tại: TASK XAUPY-001 — Foundation & Build Pipeline.

## Tài liệu bắt buộc

- [Đặc tả sản phẩm](docs/PRODUCT_SPEC.md)
- [Kế hoạch triển khai theo task](docs/IMPLEMENTATION_TASKS.md)
- [UI reference](docs/ui-reference/README.md)

## Nguyên tắc triển khai

- Chỉ làm một task tại một thời điểm.
- Task chỉ được đánh dấu DONE khi acceptance criteria và GitHub CI đều pass.
- Task có UI/build phải tạo được artifact tải về trước khi chuyển task tiếp theo.
- Không đưa logic giao dịch thật vào task nền tảng.
- Real trading mặc định phải khóa cho tới khi có task safety/execution riêng.

## Build Task 001

GitHub Actions workflow task-001-foundation-ci.yml sẽ chạy Python unit tests, restore/build Avalonia, publish Windows x64 self-contained và upload artifact XAUPY-Task001-win-x64.zip.
