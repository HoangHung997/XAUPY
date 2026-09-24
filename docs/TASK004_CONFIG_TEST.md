# XAUPY Task 004 — Configuration Backend Smoke Test

The normal user does not need to edit config through command line, but this build includes the backend diagnostic tool so Task 004 can be independently verified before Task 006 builds the full UI.

## Quick test

Extract the full Task 004 ZIP.

Open Command Prompt in the extracted folder.

### 1. Generate defaults

tools\xaupy-config.exe defaults --out test-default.json

Expected: test-default.json is created.

### 2. Validate

tools\xaupy-config.exe validate test-default.json

Expected:

VALID

### 3. Export MT5 set

tools\xaupy-config.exe export-set test-default.json --out test-default.set

Expected: test-default.set is created as UTF-16 LE/BOM.

### 4. Import it back

tools\xaupy-config.exe import-set test-default.set --out test-imported.json --report test-report.json

Expected: imported_count is greater than 100 and unknown_count is 0.

### 5. Safety check

Open test-default.json and change:

execution.allow_real_account

from false to true.

Run validate again.

Expected: validation fails. Task 004 must not permit a profile to enable real-account execution.

## Existing MT5 .set preservation test

You may use a copy of an existing .set:

tools\xaupy-config.exe import-set YOUR.set --out imported.json --report report.json

Then:

tools\xaupy-config.exe export-set imported.json --template YOUR.set --out updated.set

By default, unknown lines/comments/order/optimizer suffixes are preserved and missing XAUPY keys are not appended.

Use only copies of existing presets while testing.
