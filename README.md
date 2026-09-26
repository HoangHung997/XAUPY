# XAUPY

XAUPY là hệ thống giao dịch XAUUSD theo kiến trúc ba lớp:

1. Avalonia / C# Desktop — Control Center.
2. Python Engine — chiến lược, cấu hình, nghiên cứu, backtest và tối ưu.
3. MQL5 Bridge EA — dữ liệu MT5, execution và lớp an toàn broker-side.

Trạng thái hiện tại: TASK XAUPY-012 DONE. XAUPY-013 vẫn PLANNED và chưa bắt đầu.

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

XAUPY-013 chưa bắt đầu.
