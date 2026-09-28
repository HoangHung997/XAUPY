"""Read-only broker history import and disk-backed, identity-scoped paging.

Exit rows allocate entry costs proportionally. Raw broker deals remain available
in the same database so allocation can always be audited, including reversals.
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import closing
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sqlite3
import time

# ENUM_DEAL_REASON, preserved alongside the numeric broker value for auditing.
DEAL_REASONS = {0:'CLIENT', 1:'MOBILE', 2:'WEB', 3:'EXPERT', 4:'SL', 5:'TP',
                6:'SO', 7:'ROLLOVER', 8:'VMARGIN', 9:'SPLIT', 10:'CORPORATE_ACTION'}


def reconstruct(deals: list[dict], magic: int) -> list[dict]:
    states = defaultdict(lambda: dict(volume=0., signed=0., price=0., costs=0.))
    result = []
    for deal in sorted(deals, key=lambda d: (d.get('time_msc', d['time']*1000), d['ticket'])):
        if deal['type'] not in (0, 1) or deal['volume'] <= 0:
            continue
        state = states[(deal['symbol'], deal['position_id'])]
        volume = deal['volume']
        direction = 1 if deal['type'] == 0 else -1
        cost = deal.get('commission', 0.) + deal.get('fee', 0.)
        closing = deal['entry'] in (1, 2, 3)
        closed = min(state['volume'], volume) if closing else 0.
        # Missing entry history is explicit; exit profit/costs are still real.
        unknown_entry = closing and state['volume'] <= 0
        close_volume = volume if unknown_entry or deal['entry'] in (1, 3) else closed
        allocated = state['costs'] * closed / state['volume'] if state['volume'] else 0.
        exit_cost = cost * close_volume / volume
        if closing and close_volume > 0 and deal['magic'] == magic:
            profit, swap = deal.get('profit', 0.), deal.get('swap', 0.)
            result.append(dict(ticket=deal['ticket'], order_ticket=deal['order'], magic=magic,
                position_id=deal['position_id'], symbol=deal['symbol'], side='BUY' if direction < 0 else 'SELL',
                entry={1:'OUT', 2:'INOUT', 3:'OUT_BY'}[deal['entry']], volume=close_volume,
                price_in=state['price'] if not unknown_entry else None, price_out=deal['price'],
                entry_costs=allocated, exit_costs=exit_cost, commission=allocated+exit_cost,
                profit=profit, swap=swap, realized_total=profit+swap+allocated+exit_cost,
                reason=DEAL_REASONS.get(deal.get('reason'),f"UNKNOWN ({deal.get('reason', 'unavailable')})"),
                reason_code=deal.get('reason'), time=deal['time'], comment=deal.get('comment',''),
                entry_complete=not unknown_entry, sl=deal.get('sl',0.), tp=deal.get('tp',0.)))
        if closing:
            state['volume'] = max(0., state['volume']-closed)
            state['costs'] -= allocated
        opening = volume if deal['entry'] == 0 else max(0., volume-closed) if deal['entry'] == 2 and not unknown_entry else 0.
        if opening:
            old_volume = state['volume']
            state['price'] = (state['price']*old_volume+deal['price']*opening)/(old_volume+opening)
            state['volume'] += opening
            state['costs'] += cost-exit_cost if closing else cost
            state['signed'] = direction
        if state['volume'] < 1e-10:
            states[(deal['symbol'],deal['position_id'])] = dict(volume=0.,signed=0.,price=0.,costs=0.)
    return result


def write_report(path: Path, identity: dict, deals: list[dict]) -> dict:
    rows = reconstruct(deals, identity['magic'])
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('CREATE TABLE metadata (name TEXT PRIMARY KEY,value TEXT)')
        db.execute('CREATE TABLE deals (ticket INTEGER PRIMARY KEY,time INTEGER,symbol TEXT,payload TEXT)')
        db.execute('CREATE TABLE raw_deals (ticket INTEGER PRIMARY KEY,payload TEXT)')
        db.executemany('INSERT INTO deals VALUES (?,?,?,?)',[(d['ticket'],d['time'],d['symbol'],json.dumps(d)) for d in rows])
        db.executemany('INSERT INTO raw_deals VALUES (?,?)',[(d['ticket'],json.dumps(d)) for d in deals if d['magic']==identity['magic']])
        metadata={**identity,'imported_utc':datetime.now(timezone.utc).isoformat(),
            'exit_rows':len(rows),'raw_deals':sum(d['magic']==identity['magic'] for d in deals),
            'earliest_time':min((d['time'] for d in deals if d['magic']==identity['magic']),default=None),
            'trade_time_basis':'MT5_SERVER_WALL_CLOCK',
            'coverage':'ALL_HISTORY_RETURNED_BY_CONNECTED_BROKER','broker_execution_requested':False}
        db.execute('INSERT INTO metadata VALUES (?,?)',('report',json.dumps(metadata)))
    return metadata


def query_report(path: Path, identity: dict, *, page=0, limit=100, symbol=None) -> dict:
    if type(page) is not int or page<0 or type(limit) is not int or not 1<=limit<=1000:
        raise ValueError('Invalid broker history page')
    if symbol is not None and not isinstance(symbol,str): raise ValueError('Invalid symbol')
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        meta=json.loads(db.execute("SELECT value FROM metadata WHERE name='report'").fetchone()[0])
        if any(meta.get(k)!=identity.get(k) for k in ('account_login','account_server','magic')):
            raise ValueError('BROKER_HISTORY_IDENTITY_MISMATCH')
        where,args=(' WHERE symbol=?',[symbol]) if symbol else ('',[])
        total=db.execute('SELECT COUNT(*) FROM deals'+where,args).fetchone()[0]
        rows=[json.loads(r[0]) for r in db.execute('SELECT payload FROM deals'+where+' ORDER BY time DESC,ticket DESC LIMIT ? OFFSET ?',[*args,limit,page*limit])]
    return dict(metadata=meta,page=page,limit=limit,total=total,rows=rows,has_more=(page+1)*limit<total)


def collect(terminal: str, directory: Path, expected: dict) -> None:
    # This isolated worker imports only. It never logs in or invokes order APIs.
    import MetaTrader5 as mt5
    from .history_collect import write_json
    try:
        if not mt5.initialize(terminal, timeout=15000): raise ValueError(str(mt5.last_error()))
        account=mt5.account_info()
        if account is None or account.login!=expected['account_login'] or account.server!=expected['account_server']:
            raise ValueError('TERMINAL_ACCOUNT_IDENTITY_MISMATCH')
        # Some terminals encode their server wall clock in deal epochs. Include
        # the whole current broker day; returned records are already executed.
        start, end = datetime(1970,1,1,tzinfo=timezone.utc), datetime.now(timezone.utc)+timedelta(days=2)
        previous=None
        stable=0
        for attempt in range(20):
            values=mt5.history_deals_get(start,end)
            total=mt5.history_deals_total(start,end)
            terminal_info=mt5.terminal_info()
            if values is None or terminal_info is None or not terminal_info.connected:
                stable=0
            else:
                signature=(len(values),tuple((d.ticket,d.magic) for d in values[-10:]))
                stable=stable+1 if signature==previous and total==len(values) else 0
                previous=signature
                if stable>=2: break
            time.sleep(.5)
        else: raise ValueError('Broker history did not synchronize; retry after terminal is ready')
        # Read related positions regardless of their closing magic, so averages
        # never confuse a partial close with the original entry volume.
        selected_positions={v.position_id for v in values if v.magic==expected['magic']}
        deals=[v._asdict() for v in values if v.position_id in selected_positions]
        account=mt5.account_info()
        if account is None or account.login!=expected['account_login'] or account.server!=expected['account_server']:
            raise ValueError('TERMINAL_ACCOUNT_CHANGED_DURING_IMPORT')
        report=write_report(directory/'broker-history.sqlite',{**expected,'provider_deals_count':len(values)},deals)
        write_json(directory/'progress.json',dict(status='COMPLETE',**report))
    except Exception as exc:
        write_json(directory/'progress.json',dict(status='FAILED',error=str(exc),broker_execution_requested=False))
        raise
    finally:
        mt5.shutdown()
