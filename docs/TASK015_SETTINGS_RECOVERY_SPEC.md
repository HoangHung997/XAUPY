# XAUPY-015 — Settings, startup, backup and fail-safe recovery

Status: IMPLEMENTED_CI_PENDING — implemented and locally verified; GitHub
CI/artifact evidence and final packaged UI acceptance remain pending.

The Settings surface follows `docs/ui-reference/Tab Cài Đặt.png`: four-column
connection, Bridge, paths and appearance cards; notifications, safety, storage and
startup; permissions, backup/restore and runtime information. Unsupported live
execution permissions remain disabled. Credentials are not collected or stored.

## Persistence and startup

The Engine owns `runtime-v1.json`, containing schema v1 system settings and the
validated active profile. The default Windows location is
`%LOCALAPPDATA%/XAUPY/state`; `XAUPY_STATE_DIR` overrides it. Explicit test
`state_dir` isolates tests; when `journal_dir` is explicitly provided, the default
state directory for that Engine is its `state` subdirectory.

Writes use a same-directory temporary file, flush/fsync and atomic replacement.
Failed writes do not mutate the running settings/profile. Startup validates both
objects before accepting them. A corrupt/invalid state loads safe defaults and
surfaces an explicit recovery diagnostic; the damaged file is preserved at
startup. The in-memory strategy always starts fresh and requires new Bridge data.

Desktop reads auto-start/restart preferences. Engine restart can be disabled.
The Windows-startup checkbox registers only the current `XAUPY.Desktop.exe` in
the current user's Run key; no elevation is required. Failed settings persistence
rolls that registration change back. Automatic trading is never enabled.
Notification toggles affect optional in-app alerts, never health indicators or
persistent journal evidence.

## Instance ownership

Every supervised process receives a fresh `XAUPY_INSTANCE_ID` environment value,
inherited by a PyInstaller child. Engine replies echo `engine_instance_id`.
Desktop validates that identity before READY and on subsequent replies, refuses
non-handshake requests before validation, and sends shutdown only to a verified
instance. An orphaned/older engine occupying the port is reported as a collision;
Desktop never adopts or shuts down that foreign instance.

The empty Strategy warm-up projection no longer throws on absent indicator
objects. Shared optional JSON readers guard object kinds and finite numbers, so
waiting for the first real snapshot does not trigger a reconnect loop.

## Backup and fail-safe rules

`settings_get`, `settings_defaults_get`, `settings_set`, `backup_create` and
`backup_restore` return corresponding `_ack` messages with `ok` and `errors`.
All replies retain `trading_enabled=false` and `execution_enabled=false`.

Backups contain settings and profile, not trading history. Journal files remain
untouched. Generated backups live exclusively under the state `backups` folder,
are bounded to 1–100 copies, and can be created manually or before saved changes.
Restore accepts only a managed backup ID, rejects traversal/symlinks/invalid
schema and locked-safety violations before mutation, backs up the previous state,
then resets the strategy with `BACKUP_RESTORED`. Retention is reapplied after a
changed limit or restoration. Backup does not reinstate pending broker intents.

Hard settings locks:

- Loopback endpoint `127.0.0.1:39421`.
- Block new entries on disconnect, preserve server stops and require reconciliation.
- Real account permission and automatic trading remain false.
- N30 Dark / Vietnamese / 100% appearance is the supported presentation.

## Verification

The maintenance tests cover persistence/restart, corrupt state, atomic failure,
safety rejection, backup retention, path traversal, validating restore before
mutation, real diagnostics when Bridge is absent, transport correlation and
captured process identity. IPC contract tests include missing warm-up indicators
and owned/foreign/legacy process identities.

Run full Python tests, the IPC contract executable and a clean Release build.
For live acceptance, save a profile, create a backup, change a harmless profile
name, restore, restart the desktop, and verify the restored profile plus fresh
Bridge status. Separately test a second desktop against an occupied port: it must
show a collision and must not stop the first desktop's engine.

GitHub CI and packaged/live evidence are recorded with XAUPY-016; local test
success alone is not the project's DONE definition.

Local evidence on 2026-09-28: 11 maintenance tests passed, with the recorded
combined run passing 278 Python tests and 85 C# contract checks. Packaged
Task 010/011/012 restart/replay smokes passed. All packaged smoke processes now
use temporary state/log/backtest/optimizer directories, preserving their own
restart paths without changing the user's persisted profile.
