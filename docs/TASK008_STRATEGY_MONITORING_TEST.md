# XAUPY Task 008 — Strategy + Monitoring Acceptance

## Automated gate

Task 008 CI must run:

1. all Python regression/source tests;
2. C# IPC projection/self-tests;
3. Avalonia Release build;
4. packaged Python Engine strategy/safety smoke;
5. packaged config-tool regression smoke;
6. MetaEditor compile of the locked MT5 Bridge with 0 errors / 0 warnings;
7. self-contained Windows x64 Desktop publish;
8. complete Task 008 ZIP assembly and artifact upload.

## UI evidence rules

Automated source tests verify that:

- the approved Strategy and Monitoring PNGs exist;
- both tabs are hosted real controls;
- Strategy binds to StrategySnapshot;
- Monitoring consumes Overview snapshot timestamps and closed bars;
- no mock/backfill path is used to make missing market data look live;
- Session/News and CPU/RAM are explicitly marked unavailable until their tasks;
- execution remains locked.

## Optional user smoke after download

1. run XAUPY.Desktop.exe;
2. verify Tổng quan and Cấu hình still work;
3. open Chiến lược and confirm stale/warm-up/active states match the Engine;
4. open Giám sát and confirm quote chart starts from observed session data rather
   than a pre-filled fake chart;
5. attach the existing demo MT5 Bridge if desired and confirm BID/ASK, bars,
   Bridge status and strategy state update;
6. confirm EXECUTION LOCKED remains visible.

No real-money acceptance is part of Task 008.
