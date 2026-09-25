# XAUPY Task 006 — Configuration UI Smoke Test

Use only the complete Task 006 Windows build.

## 1. Open the app

1. Extract the whole ZIP.
2. Run XAUPY.Desktop.exe.
3. Wait until Python Engine shows READY.
4. Click Cấu hình.

Expected:

- header says full configuration center;
- field count shows 133;
- active profile loads;
- quick TF shows M30 / M5 / M1;
- REAL ACCOUNT LOCKED is visible.

## 2. Search

Type:

risk

Expected: only matching Risk-related rows/groups remain visible.

Clear search.

Expected: all 133 rows become available again.

## 3. Change a safe setting

Change:

timeframes.direction = H1
timeframes.pullback = M15
timeframes.trigger = M3

Expected:

- UNSAVED CHANGES appears;
- quick TF values update;
- Xác thực returns VALID;
- Áp dụng Active succeeds;
- Overview strategy summary updates to H1 / M15 / M3;
- execution remains locked.

The application must also allow unusual ordering such as M1 / H4 / M3.

## 4. Safety lock

Find:

execution.allow_real_account

Expected:

- editor is disabled;
- LOCKED = false is visible.

Also inspect:

execution.demo_only
safety.never_widen_sl
safety.require_server_sl

Expected: locked controls cannot be changed.

## 5. JSON

Click Lưu JSON and save a copy.

Then click Mặc định, change a value, and use Mở JSON to load the saved file.

Expected:

- saved values return as draft;
- file loads only if Python validation passes;
- loading does not silently start trading.

## 6. MT5 .set

Click Xuất .set with no prior import.

Expected: canonical .set is created.

Then click Nhập .set and choose that copy.

Expected:

- import succeeds;
- draft values appear;
- unknown count is reported;
- imported file is remembered as export template.

## 7. Regression

Click Tổng quan.

Expected: Task 005 Overview still works.

Other future tabs still show explicit placeholders.

Task 006 must not place, modify or close any order.
