"""Compare MT5 native indicator buffers against Python on the same closed bar."""
import math
from .strategy_engine import _rsi, _zscore, _moving_average


def compare_indicators(snapshot, history):
    rows=[]
    for probe in snapshot.get('indicator_probes',[]):
        bars=[b for b in history.get(probe.get('timeframe'),[]) if b.time<=probe.get('bar_time',0)]
        if not bars or bars[-1].time!=probe.get('bar_time'): continue
        closes=[b.close for b in bars]
        calculated={'RSI7':_rsi(closes,7),'RSI14':_rsi(closes,14),'RSI20':_rsi(closes,20),
                    'EMA20':_moving_average(closes,20,'EMA'),'Z20':_zscore(closes,20)}
        for name,python in calculated.items():
            native=probe.get(name)
            available=type(native) in (int,float) and math.isfinite(native) and python is not None
            tolerance=.01 if name.startswith('RSI') else max(.00001,float(snapshot.get('point',.01))/10)
            difference=abs(native-python) if available else None
            rows.append(dict(timeframe=probe['timeframe'],bar_time=probe['bar_time'],indicator=name,mt5=native,python=python,
                difference=difference,tolerance=tolerance,status='PASS' if available and difference<=tolerance else 'DIFFERENT' if available else 'WARMUP',seed_bars=len(bars)))
    return dict(available=bool(rows),source='MT5_NATIVE_BUFFERS_VS_PYTHON',rows=rows,
        note='RSI Wilder/EMA may retain older native seed history. Differences are reported, never replaced with a matching value. Closed bars only.')
