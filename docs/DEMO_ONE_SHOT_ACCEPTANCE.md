# One explicitly authorized DEMO entry — 0.17.0-demo1

This extension addresses the user's request to observe XAUPY until it places one
order. RC2's order controls were simulations and its EA had no broker send path.
This revision adds a separate bounded DEMO capability; it does not enable general
automatic trading, real-account trading or the manual simulation buttons.

## Scope

- A user-authorized arm binds one attempt UUID to the current account login,
  broker server, symbol, magic, EA session and exact normalized profile hash.
- The current profile is preserved. Only a genuinely new strategy signal after
  arming is eligible; bootstrap data, old signals, replays and reconnects cannot
  manufacture an entry. No indicator threshold is relaxed to obtain a trade.
- At most 0.01 lot, never rounded up to a broker minimum above that cap. Initial
  server-side SL and TP are required. Only MARKET entry and supported initial
  FIXED/STRUCTURE/ATR stops with FIXED/RR target are eligible.
- This acceptance tests entry and server stops. It does not execute break-even,
  trailing, partial closure or dynamic target management, even when those
  parameters exist in the canonical profile. Other EAs and positions are not
  modified. Any existing position/pending order on the symbol blocks entry,
  regardless of magic, to avoid modifying a netted position.
- The authorization lasts at most 24 hours. An Engine restart suspends an unused
  authorization. An EA identity or profile change also suspends it. Expiration,
  rejection or uncertainty is reported; no automatic rearm or retry occurs.

## Guards and durable consumption

Python checks current DEMO identity, EA capability, terminal/account trading
permissions, fresh quotes, spread, canonical trading sessions/day filters, daily
loss/trade/consecutive-loss limits, cooldown, exposure, volume, stop geometry,
planned risk and minimum net reward/risk. Missing broker history fails closed.
Enabled news filtering without a usable feed also fails closed.

Before returning its command, Python atomically persists a consumed allowance.
Only the owning capable Bridge connection can receive a command. Desktop/status
connections cannot report fills or take over that connection. The command carries
a five-second broker-time deadline and the authorization identity.

The EA parses structured JSON with exact types, duplicate-key rejection and
bounded size/depth. It independently checks DEMO, exact identity, permissions,
fresh quotes, any symbol exposure, broker volume/stop/filling rules, spread and
reference-price deviation. `OrderCalcProfit` checks planned loss and `OrderCheck`
checks the broker request. A terminal-wide exclusive file lock, flushed global
variable claim and permanent account/server/symbol claim file consume the EA's
allowance before its sole `OrderSend` call. A different UUID cannot restore it.

Uncertain outcomes remain consumed. Transport reconnects replay results only,
never an order. After EA restart, a persisted result may be reconciled through
the new owning connection only when both original authorization and fresh
account/server/symbol/magic match. An unresolved crash without a recorded ticket
needs read-only broker reconciliation, not another send.

Market-execution brokers may not enforce the deviation parameter as a hard fill
price bound. The EA checks the latest quote before sending and reports actual
slippage afterward. This is not a guarantee of fill price or realized loss.

## Completion and observation

`OrderSend=true` or `PLACED` alone is not completion. The EA checks matching
broker deal history, side, volume, order and actual SL/TP. Python only records
FILLED after a verified deal/protection result; a partial fill consumes the
entire allowance and exposes its actual volume. A 30-second missing receipt
becomes UNKNOWN without retry; a later verified result can resolve it.

The heartbeat exposes a separate `demo_once` record. Desktop shows its state
while retaining the general lock and the manual simulation labels. Invalid or
incomplete fill reports display UNKNOWN. Loss of IPC preserves the previous
report but marks it stale.

`scripts/demo_once.py status` and `watch` send read-only status/heartbeat requests.
Only the explicit `arm --attempt-id <stable UUID> --confirm-demo-one-order`
operation can authorize a new unused attempt. It obtains the exact current
identity/hash, enforces the 0.01-lot bound, and never creates a strategy signal.
The observer itself has no MT5 order API.

## Verification scope

- Isolated controller tests exercise both sides, fresh real StrategyEngine
  signal generation, durability, failed writes, restart, profile/account
  changes, broker/risk/session guards, partial fills and uncertain outcomes.
- Socket tests bind the Bridge connection, reject foreign result/ownership
  messages and duplicate JSON keys, and exercise a complete synthetic
  strategy-to-command-to-result flow. These fixtures never connect to MT5.
- The packaged one-shot smoke repeats that isolated socket flow with the actual
  executable. Existing data, simulation, backtest, optimization and UI checks
  retain their prior scopes.
- C# contracts cover optional/malformed/stale/filled status. Headless interaction
  checks verify status visibility and preserve manual simulation confirmation.
- Actual native deployment, explicit authorization and any broker receipt must
  be recorded separately below. Automated tests are not evidence of a live DEMO
  fill.

## Native checkpoint — 2026-09-28 08:42 ICT

- Source `89aea083c677a07621b04d7fa39af3c63dc29be5` was built locally with a clean
  working tree: 373 Python tests, 142 IPC contract checks and 84 desktop
  interaction assertions passed. All packaged smoke checks passed, including
  the 16-check isolated one-shot flow. MetaEditor reported zero errors/warnings.
- The packaged EA 1.017 and both helpers were deployed to the existing XAUUSD
  M30 Bridge chart. Its native OnInit JSON self-test passed all 23 cases. The
  unrelated M5 EA remains in its previous user-paused state.
- Desktop and Engine run from `dist/XAUPY-verified-demo1-win-x64`. The live
  Bridge reports DEMO, fresh quotes, complete broker-risk history, valid trading
  permissions and no XAUUSD position or pending order at authorization time.
- The user-requested one-shot allowance was armed at 08:39:20 ICT with a
  0.01-lot cap and a 24-hour expiry. The exact existing profile hash remains
  `04d944ec567a78ec2b368a00cb9dc271172cf4a73ec42fc28fa2e1d693a9ffe9`.
  Its baseline uses closed-bar RSI with Z disabled; this entry-path acceptance
  does not silently activate the separately implemented intrabar feature.
- At this checkpoint the allowance is **ARMED, not consumed**. Strategy state
  is `WAIT_PULLBACK_SELL`; no command or broker order has been sent. Trading
  sessions begin at 07:00 broker time, approximately 11:00 ICT with the observed
  broker offset. A read-only task heartbeat checks every five minutes while EA
  and Engine process market data continuously. It reports a verified fill or
  an actionable failure and never rearms or retries.
- Native Orders UI displays `DEMO 1 LỆNH · CHỜ TÍN HIỆU` and zero positions/
  pending orders. Manual controls still explicitly state simulation mode.

Local evidence is in `artifacts/demo1-build.log`, `demo1-live-arm.json`,
`demo1-live-watch.json` and `demo1-live-current.json`. Account identifiers and
raw broker evidence remain local. A broker fill remains pending; this checkpoint
does not claim full live execution acceptance or 100% reference-image parity.

References: [MetaQuotes OrderSend](https://www.mql5.com/en/docs/trading/ordersend),
[OrderCheck](https://www.mql5.com/en/docs/trading/ordercheck),
[atomic terminal global-variable claim](https://www.mql5.com/en/docs/globals/globalvariablesetoncondition).
