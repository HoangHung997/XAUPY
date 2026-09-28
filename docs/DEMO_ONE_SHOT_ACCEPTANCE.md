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

Initial implementation checkpoint: live authorization and live order receipt
are pending. Account identifiers and raw broker evidence remain local.

References: [MetaQuotes OrderSend](https://www.mql5.com/en/docs/trading/ordersend),
[OrderCheck](https://www.mql5.com/en/docs/trading/ordercheck),
[atomic terminal global-variable claim](https://www.mql5.com/en/docs/globals/globalvariablesetoncondition).
