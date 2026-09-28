"""Shared pre-entry cost model for historical replay and broker planning.

Configured slippage is a worst-case allowance, not a fabricated observed fill.
Commission ceiling is reserved in sizing/RR even when actual historical fees
are known; actual fees remain the amount deducted from backtest P/L.
"""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EntryCostPlan:
    loss_per_lot: float
    reward_per_lot: float
    net_rr: float
    blocker: str | None


def entry_cost_plan(profile: dict[str, Any], *, risk_distance: float,
                    target_distance: float, spread_price: float,
                    point: float, tick_size: float, tick_value: float,
                    actual_commission_per_lot: float | None = None) -> EntryCostPlan:
    costs = profile["costs"]
    commission = float(costs["max_commission_per_lot"])
    slippage = float(costs["max_slippage_points"]) * point
    loss = (risk_distance + slippage) / tick_size * tick_value + commission
    reward = (target_distance - slippage) / tick_size * tick_value - commission
    rr = reward / loss if loss > 0 else 0.0
    blocker = None
    if spread_price > float(costs["max_spread_price_units"]) + 1e-12:
        blocker = "SPREAD_LIMIT"
    elif actual_commission_per_lot is not None and actual_commission_per_lot > commission + 1e-12:
        blocker = "COMMISSION_LIMIT"
    elif loss <= 0 or rr + 1e-12 < float(costs["min_net_rr"]):
        blocker = "MIN_NET_RR"
    return EntryCostPlan(loss, reward, rr, blocker)
