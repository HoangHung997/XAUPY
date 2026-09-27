"""Causal RSI/Z research on OHLC; deliberately not a tick-execution backtest.

An OHLC extreme can establish that a CLOSE-based indicator crossed a level,
but cannot establish the order of high/low or an intrabar reversal fill. We
therefore confirm only at a later bar's close and enter at the following open.
The last 20% is held out from all parameter selection.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import hashlib
import itertools
import math
from pathlib import Path
import statistics
from typing import Any

from .strategy_engine import Bar


@dataclass(frozen=True)
class Candidate:
    family: str
    rsi_period: int = 14
    rsi_sell: float = 65.0
    rsi_delta: float = 5.0
    z_period: int = 20
    z_sell: float = 2.5
    z_delta: float = 0.3


@dataclass(frozen=True)
class Event:
    arm: int
    confirmation: int
    entry: int
    exit: int
    side: int
    gross: float
    cost: float

    @property
    def net(self) -> float:
        return self.gross - self.cost


def read_candles(path: Path) -> tuple[list[Bar], list[float]]:
    bars, spreads = [], []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            bar = Bar.from_payload(row)
            if bars and bar.time <= bars[-1].time:
                raise ValueError("candle timestamps must strictly increase")
            spread = float(row.get("spread") or 0)
            if not math.isfinite(spread) or spread < 0:
                raise ValueError("invalid historical spread")
            bars.append(bar)
            spreads.append(spread)
    if len(bars) < 300:
        raise ValueError("at least 300 closed bars required for three chronological samples")
    return bars, spreads


def _rsi_value(gain: float, loss: float) -> float:
    if loss == 0:
        return 50.0 if gain == 0 else 100.0
    return 100.0 - 100.0 / (1.0 + gain / loss)


def rsi_series(bars: list[Bar], period: int) -> tuple[list[float], ...]:
    """Wilder seed, then provisional high/low/close from the same prior state."""
    high, low, close = ([math.nan] * len(bars) for _ in range(3))
    gain = loss = 0.0
    for i in range(1, len(bars)):
        previous = bars[i - 1].close
        change = bars[i].close - previous
        if i < period:
            gain += max(change, 0)
            loss += max(-change, 0)
            continue
        for target, price in ((high, bars[i].high), (low, bars[i].low), (close, bars[i].close)):
            delta = price - previous
            prior_factor = 1 if i == period else period - 1
            g = (gain * prior_factor + max(delta, 0)) / period
            l = (loss * prior_factor + max(-delta, 0)) / period
            target[i] = _rsi_value(g, l)
        prior_factor = 1 if i == period else period - 1
        gain = (gain * prior_factor + max(change, 0)) / period
        loss = (loss * prior_factor + max(-change, 0)) / period
    return high, low, close


def z_series(bars: list[Bar], period: int) -> tuple[list[float], ...]:
    """Population standard deviation, matching the canonical engine."""
    high, low, close = ([math.nan] * len(bars) for _ in range(3))
    for i in range(period - 1, len(bars)):
        # Centered summation avoids cancellation at large quote magnitudes.
        origin = bars[i - 1].close
        prior = [bar.close - origin for bar in bars[i - period + 1:i]]
        total, squares = math.fsum(prior), math.fsum(x * x for x in prior)
        for target, price in ((high, bars[i].high), (low, bars[i].low), (close, bars[i].close)):
            x = price - origin
            mean = (total + x) / period
            variance = max(0.0, (squares + x * x) / period - mean * mean)
            target[i] = (x - mean) / math.sqrt(variance) if variance else 0.0
    return high, low, close


def candidates() -> list[Candidate]:
    result = [Candidate("RSI", rsi_period=p, rsi_sell=l, rsi_delta=d)
              for p, l, d in itertools.product((7, 14, 21), (60., 65., 70.), (3., 5., 8.))]
    result += [Candidate("Z", z_period=p, z_sell=l, z_delta=d)
               for p, l, d in itertools.product((20, 30, 50), (1.5, 2., 2.5), (0.2, 0.3, 0.5))]
    result += [Candidate("RSI_AND_Z", rsi_sell=r, rsi_delta=rd, z_sell=z, z_delta=zd)
               for r, z, rd, zd in itertools.product((60., 65., 70.), (1.5, 2., 2.5), (3., 5.), (0.3, 0.5))]
    return result


def collect_events(
    bars: list[Bar], spreads: list[float], candidate: Candidate,
    rsi: tuple[list[float], ...], z: tuple[list[float], ...], *,
    start: int, end: int, point_size: float, horizon: int = 5,
    expiry: int = 2, use_extremes: bool = True, extra_cost: float = 0.0,
    timeframe_seconds: int | None = None,
) -> list[Event]:
    """Non-overlapping events; no arm, label or return crosses sample boundary."""
    use_rsi, use_z = candidate.family != "Z", candidate.family != "RSI"
    rh, rl, rc = rsi
    zh, zl, zc = z
    if not use_extremes:
        rh = rl = rc
        zh = zl = zc
    interval = timeframe_seconds or min(b.time-a.time for a, b in zip(bars, bars[1:]))
    gap_prefix = [0]
    for previous, current in zip(bars, bars[1:]):
        gap_prefix.append(gap_prefix[-1] + (current.time - previous.time != interval))
    side, armed = 0, -1
    r_extreme = z_extreme = 0.0
    result: list[Event] = []
    i = start
    while i < end - horizon:
        if i > start and gap_prefix[i] != gap_prefix[i-1]:
            side = 0
        if (use_rsi and not math.isfinite(rc[i])) or (use_z and not math.isfinite(zc[i])):
            i += 1
            continue
        if side and i - armed > expiry:
            side = 0
        if not side:
            sell = (not use_rsi or rh[i] >= candidate.rsi_sell) and (not use_z or zh[i] >= candidate.z_sell)
            buy = (not use_rsi or rl[i] <= 100 - candidate.rsi_sell) and (not use_z or zl[i] <= -candidate.z_sell)
            if sell != buy:
                side, armed = (-1 if sell else 1), i
                r_extreme = rh[i] if sell else rl[i]
                z_extreme = zh[i] if sell else zl[i]
            i += 1
            continue
        # All current-bar extremes precede its close. Never confirm on arm bar.
        r_extreme = min(r_extreme, rl[i]) if side == 1 else max(r_extreme, rh[i])
        z_extreme = min(z_extreme, zl[i]) if side == 1 else max(z_extreme, zh[i])
        r_pass = not use_rsi or side * (rc[i] - r_extreme) + 1e-12 >= candidate.rsi_delta
        z_pass = not use_z or side * (zc[i] - z_extreme) + 1e-12 >= candidate.z_delta
        if r_pass and z_pass:
            entry, exit_index = i + 1, i + horizon
            if exit_index >= end:
                break
            if gap_prefix[exit_index] != gap_prefix[armed]:
                # Exclude labels whose price path crosses any unavailable
                # interval, including market closures. Do not fabricate fills.
                side = 0
                i += 1
                continue
            # MqlRates spread is a bar-level proxy, not the executable spread
            # at our entry/exit. Include both sides symmetrically and label it.
            spread_cost = (spreads[entry] + spreads[exit_index]) / 2 * point_size
            result.append(Event(armed, i, entry, exit_index, side,
                                side * (bars[exit_index].close - bars[entry].open),
                                spread_cost + extra_cost))
            side = 0
            i = exit_index + 1
        else:
            i += 1
    return result


def event_stats(events: list[Event]) -> dict[str, Any]:
    values = [event.net for event in events]
    if not values:
        return {"events": 0, "mean_net_price": None, "mean_gross_price": None,
                "win_rate": None, "lower_mean_95": None, "worst_event": None}
    mean = statistics.fmean(values)
    # Descriptive normal approximation; not a multiple-testing-adjusted proof.
    se = statistics.stdev(values) / math.sqrt(len(values)) if len(values) > 1 else math.inf
    return {"events": len(events), "mean_net_price": mean,
            "mean_gross_price": statistics.fmean(e.gross for e in events),
            "win_rate": sum(x > 0 for x in values) / len(values),
            "lower_mean_95": mean - 1.96 * se if math.isfinite(se) else None,
            "worst_event": min(values)}


def select_candidate(rows: list[dict[str, Any]], minimum: int = 30) -> dict[str, Any] | None:
    """Only training statistics can influence selection, never validation/test."""
    eligible = [row for row in rows if row["train"]["events"] >= minimum
                and row["train"]["lower_mean_95"] is not None]
    return max(eligible, key=lambda row: row["train"]["lower_mean_95"]) if eligible else None


def analyze_candles(path: Path, *, point_size: float, horizon: int = 5,
                    extra_cost: float = 0.0) -> dict[str, Any]:
    if not math.isfinite(point_size) or point_size <= 0:
        raise ValueError("point_size must be positive")
    if not math.isfinite(extra_cost) or extra_cost < 0:
        raise ValueError("extra_cost must be nonnegative")
    if not isinstance(horizon, int) or not 1 <= horizon <= 100:
        raise ValueError("horizon must be 1..100")
    bars, spreads = read_candles(path)
    n = len(bars)
    split1, split2 = int(n * .6), int(n * .8)
    segments = {"train": (0, split1), "validation": (split1, split2), "test": (split2, n)}
    rsis = {p: rsi_series(bars, p) for p in (7, 14, 21)}
    zs = {p: z_series(bars, p) for p in (20, 30, 50)}
    rows = []
    for candidate in candidates():
        row: dict[str, Any] = {"parameters": asdict(candidate)}
        for name, (start, end) in segments.items():
            row[name] = event_stats(collect_events(
                bars, spreads, candidate, rsis[candidate.rsi_period], zs[candidate.z_period],
                start=start, end=end, point_size=point_size, horizon=horizon, extra_cost=extra_cost))
        rows.append(row)
    selections = []
    for family in ("RSI", "Z", "RSI_AND_Z"):
        chosen = select_candidate([r for r in rows if r["parameters"]["family"] == family])
        if chosen is None:
            selections.append({"family": family, "status": "INSUFFICIENT_TRAIN_EVENTS"})
            continue
        candidate = Candidate(**chosen["parameters"])
        result = dict(chosen)
        result["family"] = family
        result["close_only"] = {}
        for name, (start, end) in segments.items():
            result["close_only"][name] = event_stats(collect_events(
                bars, spreads, candidate, rsis[candidate.rsi_period], zs[candidate.z_period],
                start=start, end=end, point_size=point_size, horizon=horizon,
                extra_cost=extra_cost, use_extremes=False))
        result["status"] = ("RESEARCH_CANDIDATE" if all(
            chosen[part]["events"] >= 30 and chosen[part]["lower_mean_95"] > 0
            for part in ("validation", "test")) else "NOT_VALIDATED")
        selections.append(result)
    return {
        "schema_version": 1, "model": "OHLC_EXTREME_LATCH_LATER_CLOSE_EVENT_STUDY_V1",
        "source": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bars": n, "first_time": bars[0].time, "last_time": bars[-1].time,
        "point_size": point_size, "horizon_bars": horizon, "expiry_bars": 2,
        "extra_round_trip_cost_price": extra_cost, "candidate_count": len(rows),
        "segments": {name: {"start_index": a, "end_index_exclusive": b,
                             "first_time": bars[a].time, "last_time": bars[b-1].time}
                     for name, (a, b) in segments.items()},
        "selections": selections, "candidates": rows,
        "limitations": [
            "Single-timeframe reversal event study, not full Direction/Pullback/Trigger strategy P&L.",
            "OHLC high/low gives threshold evidence; actual tick order and intrabar fills are unavailable.",
            "Arm at extreme, confirm at a later close, enter next open; fixed 5-bar horizon by default.",
            "Setups and outcome labels crossing any timeframe gap are excluded, including market closures.",
            "Training alone selects each family's candidate; later validation and test never retune it.",
            "Spread uses historical bar-level proxy; commission/slippage only if supplied as extra_cost.",
            "Confidence bounds are descriptive, not corrected for multiple search trials or serial dependence.",
            "Research candidates are not automatically applied to trading profiles.",
        ],
    }
