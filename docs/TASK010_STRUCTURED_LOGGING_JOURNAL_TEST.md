# XAUPY Task 010 — Structured Logging + Journal Test

Status: implementation acceptance  
Visual source-of-truth: docs/ui-reference/Tab Nhật Kí.png

## Automated acceptance

Task 010 is DONE only when all are green:

- structured journal schema tests;
- append/filter/search/date tests;
- corrupt-line recovery tests;
- replay + sequence continuation across restart;
- bookmark persistence/replay;
- Engine journal_query and journal_bookmark_set IPC tests;
- heartbeat journal summary tests;
- Strategy / Bridge / Orders evidence tests with correlation ids;
- approved Journal UI source hierarchy test;
- C# journal parser contract checks;
- all previous Python regressions;
- Avalonia Release with 0 warnings / 0 errors;
- packaged Task 010 replay smoke across two Engine launches;
- packaged Task 009 execution-simulation smoke;
- packaged Task 007 strategy smoke;
- packaged config smoke;
- locked MT5 Bridge compile with 0 errors / 0 warnings;
- complete Windows x64 artifact.

## Manual Journal smoke after delivery

1. Launch XAUPY.Desktop.exe from the full Task 010 build.
2. Open **Nhật ký**.
3. Confirm layout follows docs/ui-reference/Tab Nhật Kí.png:
   - seven source filters;
   - INFO/WARN/ERROR/DEBUG filters;
   - search + date scope;
   - log table;
   - detail area;
   - right summary / recent alerts / bookmarks.
4. Confirm rows are real Engine journal records, not example messages from the PNG.
5. Trigger a config apply, Bridge connect/reconnect, strategy state change or
   Task 009 manual simulation and verify matching journal evidence appears.
6. Search/filter by source, severity and text.
7. Bookmark a row, restart XAUPY, reopen Journal and confirm bookmark persists.
8. Export the current filtered rows to JSONL and verify sequence/message/details
   match the UI rows.
9. Stop MT5 long enough for stale market data and verify a WARN/Alerts journal
   entry is created when the stale state changes.
10. Confirm Journal never claims a real broker fill/action during Task 010.

## Hard boundary

Task 010 does not enable real broker execution.

- demo_only=true;
- allow_real_account=false;
- max_retry_count=0;
- never_widen_sl=true;
- require_server_sl=true;
- block_on_stale_market_data=true;
- trading_enabled=false;
- execution_enabled=false;
- no OrderSend / OrderSendAsync / CTrade mutation path.
