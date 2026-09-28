# Windows release and local acceptance

> Historical 0.16 acceptance below. The active 1.0 implementation and outstanding
> acceptance are tracked in [RELEASE_V1_COMPLETION.md](RELEASE_V1_COMPLETION.md)
> and [the 172-feature matrix](RELEASE_V1_FEATURE_MATRIX.csv). Prototype execution
> locks in this historical evidence do not define current user-controlled modes.

Version: 0.16.0-rc1. Build, installer and live connection verified. Task 016 stays
ACTIVE because strict 100% UI parity has not been met.

## Reproducible build

`scripts/build_windows.ps1` builds the self-contained Avalonia application,
the packaged Python engine/configuration utility, canonical profiles, and the
Bridge EA with the installed MetaEditor. It requires zero MetaEditor errors and
warnings, runs Python/C# tests and packaged regression smoke tests, then creates
the portable ZIP with a SHA-256 manifest. Pass `-Dotnet` for a private SDK path.
Pass `-Iscc` to build the per-user Inno Setup installer from `installer/XAUPY.iss`.

The installer does not request administrator rights, enable trading, modify MT5
network permissions, or automatically start the application. User state is outside
the install directory and is retained on uninstall. The unsigned installer is a
release candidate; a production signing certificate is not configured.

`desktop-release.yml` validates Python/C# on Linux and packages on Windows using
MetaEditor and the runner's Inno Setup compiler. It uploads both the portable ZIP
and installer. A successful local compile is not substituted for CI evidence.

## Real connection acceptance

1. Run `XAUPY.Desktop.exe` and verify Python Engine READY remains stable.
2. Copy the bundled `mt5/XAUPY_Bridge_EA.ex5` into the chosen terminal's
   `MQL5/Experts`, refresh Navigator, and attach to an XAUUSD chart.
3. MT5 requires the local connection address in Tools / Options / Expert Advisors:
   `http://127.0.0.1` (without the port). The user manages this terminal permission.
4. Verify DEMO, increasing snapshot count, authentic bid/ask and account data,
   closed-bar history, and persistent EXECUTION LOCKED.
5. `python scripts/probe_live_bridge.py --duration 10` records read-only protocol
   evidence with no account identity or trading requests.
6. Stop/restart Engine using the UI; verify stale prices are cleared and the EA
   reconnects. Restore the engine to READY afterwards.

## Visual acceptance

Run `XAUPY.Desktop.exe --capture-ui <absolute-output-directory>` to export all ten
rendered pages at the actual window size. These are real controls and runtime
state, not pasted reference images or fabricated trading fixtures.
Compare the resulting pages to `docs/ui-reference` for navigation, color, columns,
card grouping, typography, clipping, table alignment, and chart placement.

Exact equality of market values with the mockup is neither expected nor evidence
of correctness. Pixel-identical appearance has not been certified. Remaining
visible deviations must be recorded in the acceptance report rather than hidden.

## Local evidence — 2026-09-28

- Source baseline `71902a8`: 283 Python tests, 85 C# contract checks and eight
  packaged smoke categories passed. The clean portable build records these checks
  and SHA-256 hashes for every bundled file in `build-manifest.json`.
- MetaEditor: zero errors and zero warnings; the deployed Bridge is version 1.014.
- `artifacts/live-final.json` and `artifacts/live-after-ui-restart.json`: all 16
  read-only acceptance checks passed over 11 samples each. Every timeframe has
  256 authentic closed bars and all execution locks remain asserted.
- Native Avalonia stop/start clears unavailable quotes and account values, returns
  to READY and receives the EA's history again without manually reattaching it.
- Weekend prices stay labeled as the latest received price; their last tick time
  is available in the quote tooltip. Fresh heartbeats do not claim fresh ticks.
- The first CI run passed Linux validation but exposed a Windows temporary-path
  assertion issue. Its canonical-path comparison was corrected; the final run below passes.
- The final polish passes 283 Python tests, 90 C# contract checks and 20 headless
  Avalonia interaction checks. The new quote-age checks use the broker clock;
  the reconnect checks preserve an unsaved configuration draft.

## Final CI and downloaded build

- [GitHub run 36340716356](https://github.com/HoangHung997/XAUPY/actions/runs/36340716356):
  SUCCESS for Linux validation and Windows packaging on source
  `a9137702661c810b301d388ce23230791dcd137c`.
- 283 Python tests, 90 C# checks, 20 headless desktop interaction checks and all
  eight packaged smoke categories pass. MetaEditor reports zero errors/warnings.
- The per-user installer was installed, every installed file checked against
  the manifest, and uninstalled successfully on the Windows CI runner.
- Downloaded artifact 10939305308 was independently inspected: all 278 portable
  files and all 277 manifest hashes match, with self-contained x64 Desktop,
  Engine/config executables, EX5, profiles and ten UI references.
- Portable ZIP SHA-256:
  `f593f3ef32cc44932db5a1780fb2b6daac466b4807d8a87471e510b5ffee32d9`.
- Installer SHA-256:
  `572edb5ca3fb49977eab8dd1a87ee3d367828c446e95c6ad064c2d56dc8c5679`.
- The downloaded CI Desktop was launched locally against the already open MT5.
  `artifacts/live-ci-verified.json` passes 16/16 read-only checks in 11 samples.
  Its ten real rendered pages are in `artifacts/ui-audit-ci/`.
- Native Stop/Start was also exercised on the downloaded CI build. Quotes and
  balance clear on STOPPED. The immediate transition capture
  `artifacts/live-ci-after-restart.json` intentionally includes the initial waiting
  sample, so it does not pass the continuous-connected criterion; the next sample
  at 1.047 seconds already has the first real snapshot. After READY and Bridge
  recovery, `artifacts/live-ci-stable-after-restart.json` passes all 16 checks
  across another 11 samples. The application is left running and connected.
- Local application: `dist/XAUPY-verified-win-x64/XAUPY.Desktop.exe`.
  Delivery ZIP and installer are in `dist/`; independent verification is in
  `artifacts/ci-release-36340716356/verification.json`.
- Interactive local comparison: `artifacts/ui-comparison-report/index.html`.
  Its embedded images stay local; no account screenshots were uploaded to GitHub.

## Boundaries

Task013 is historical/broker simulation. Broker order placement, modification and
closure stay locked in every layer. Connection acceptance must not place a trade.
No production release or profitability claim follows from a successful build.
