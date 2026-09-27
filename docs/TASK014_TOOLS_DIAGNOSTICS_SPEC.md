# XAUPY-014 — Tools and diagnostics

Status: IMPLEMENTED_CI_PENDING — implemented and locally verified; GitHub
CI/artifact evidence and final packaged UI acceptance remain pending.

The Tools surface follows `docs/ui-reference/Tab Công Cụ.png`: ten-tool navigation,
central configuration editor with file information and quick actions, validation
result, selected-tool help and local action history. Runtime values are actual
Engine/Bridge values; the reference's fictional trading figures are not reused.

Implemented workflows:

- Open, format, canonical-schema validate, apply and export profile JSON.
- Show field differences between the default and active profile.
- Probe Strategy indicators and current Symbol/session configuration.
- Calculate theoretical lots from user-entered budget, SL distance, tick size and
  tick value; explicitly excludes fees/slippage and requires broker lot rounding.
- Validate a local news JSON array (`timestamp_utc`, `currency`, `impact`, `title`).
  This does not claim to supply a live economic-calendar feed.
- Read real system, Bridge, MT5, market freshness, profile, journal and recovery
  diagnostics; export the report as JSON.
- Keep a bounded session-local history of tool actions.

`diagnostics_get` returns `diagnostics_get_ack` with `ok`, `diagnostics` or `errors`.
Diagnostics contain current checks, runtime/platform/version, uptime, Bridge,
Overview, Strategy and actual storage paths. Missing Bridge and market snapshots
produce `WAIT`, not fabricated healthy statuses. Guardian remains `LOCKED`.

Profile application uses the existing canonical validation path and now persists
atomically via XAUPY-015. No tool sends a broker operation.

Verification: `python -m unittest discover -s python/tests -p test_task014_015_maintenance.py -v`.
Full Python regression, IPC contract self-tests and Windows build must also pass.
Capture the live Tools view after the matching Engine package is launched; older
engines intentionally do not implement these maintenance messages.

Local evidence on 2026-09-28: the shared Task 014/015 maintenance suite passes
11 tests; the recorded combined suite passes 278 Python tests and 85 C# IPC
checks. Read-only live MT5 transport/history is verified separately in
`docs/LIVE_HISTORY_SYNC.md`. Neither diagnostic success nor a fresh IPC snapshot
claims that the market is currently open or that a trade was executed.
