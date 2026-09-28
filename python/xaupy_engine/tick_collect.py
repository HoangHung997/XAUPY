"""Read-only paged MT5 quote archive; preserves equal-millisecond observations."""
from datetime import datetime, timezone, timedelta
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import time

from .history_collect import main as collect_bars, write_json


def parse_range(start, end):
    first=datetime.strptime(start,'%Y-%m-%d').replace(tzinfo=timezone.utc)
    last=datetime.strptime(end,'%Y-%m-%d').replace(tzinfo=timezone.utc)+timedelta(days=1)
    if last<=first: raise ValueError('End date must be on or after start date')
    return int(first.timestamp()),int(last.timestamp())


def collect_quotes(provider, symbol, start, end, stream, progress):
    """Disjoint hour intervals avoid both boundary duplication and count caps."""
    count=invalid=gaps=0;previous=None;discontinuous=True;digest=hashlib.sha256()
    empty=[];first=None
    for lower in range(start,end,3600):
        upper=min(lower+3600,end)
        rows=None
        for attempt in range(3):
            rows=provider.copy_ticks_range(symbol,datetime.fromtimestamp(lower,timezone.utc),
                datetime.fromtimestamp(upper,timezone.utc),provider.COPY_TICKS_ALL)
            if rows is not None: break
            time.sleep(.2*(attempt+1))
        if rows is None: raise RuntimeError(f'Tick provider failed at {lower}: {provider.last_error()}')
        in_interval=0
        for row in rows:
            stamp=int(row['time_msc']);bid=float(row['bid']);ask=float(row['ask'])
            if not lower*1000<=stamp<upper*1000: continue
            if previous is not None and stamp<previous: raise ValueError('Provider ticks are not chronological')
            if not all(math.isfinite(v) and v>0 for v in (bid,ask)) or ask<bid:
                invalid+=1;discontinuous=True;continue
            continuous=not discontinuous and previous is not None and stamp-previous<=120000
            if not continuous:gaps+=1
            item=dict(time_msc=stamp,bid=bid,ask=ask,continuous=continuous)
            encoded=(json.dumps(item,separators=(',',':'))+'\n').encode('utf-8')
            stream.write(encoded);digest.update(encoded)
            previous=stamp;first=stamp if first is None else first;discontinuous=False
            count+=1;in_interval+=1
        if not in_interval:
            empty.append(dict(start=lower,end=upper));discontinuous=True
        progress(dict(tick_count=count,invalid_quotes=invalid,discontinuous_ticks=gaps,completed_until=upper))
    return dict(tick_count=count,invalid_quotes=invalid,discontinuous_ticks=gaps,empty_intervals=empty,
        first_time_msc=first,last_time_msc=previous,sha256=digest.hexdigest(),
        continuity_rule='First tick, invalid quote, empty hour or silence above 120s resets setup; broker completeness cannot be independently guaranteed')


def main(argv=None):
    parser=argparse.ArgumentParser()
    for key in ('terminal','symbol','output','from-date','to-date'):parser.add_argument('--'+key,required=True)
    parser.add_argument('--context-file')
    args=parser.parse_args(argv);start,end=parse_range(args.from_date,args.to_date)
    root=Path(args.output);root.mkdir(parents=True,exist_ok=True)
    import MetaTrader5 as mt5
    # The complete available M1 archive provides closed-bar indicator warmup.
    collect_bars(['--terminal',args.terminal,'--symbol',args.symbol,'--output',str(root),'--timeframes','M1'])
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    report={**manifest,'status':'RUNNING','input_model':'REAL_TICKS','requested_from':args.from_date,'requested_to':args.to_date}
    if not mt5.initialize(args.terminal,timeout=15000):raise RuntimeError(str(mt5.last_error()))
    try:
        identity=mt5.account_info()
        if identity is None or identity.server!=manifest['broker_server']:raise ValueError('Broker changed during acquisition')
        with (root/'ticks.jsonl').open('wb') as stream:
            def progress(values):
                report.update(values);write_json(root/'progress.json',report)
            evidence=collect_quotes(mt5,args.symbol,start,end,stream,progress)
        after=mt5.account_info()
        if after is None or after.login!=identity.login or after.server!=identity.server:raise ValueError('Account changed during acquisition')
        if not evidence['tick_count']:raise ValueError('Broker returned no valid ticks in the requested interval')
        bars=[]
        with Path(manifest['timeframes']['M1']['path']).open(encoding='utf-8-sig',newline='') as stream:
            for row in csv.DictReader(stream):
                bars.append({key:int(row[key]) if key in ('time','tick_volume') else float(row[key]) for key in ('time','open','high','low','close','tick_volume')})
        if not bars or bars[0]['time']>=evidence['first_time_msc']//1000:
            raise ValueError('No closed M1 warmup precedes the first tick; acquire a more recent interval')
        values=manifest['symbol_metadata']
        context=json.loads(Path(args.context_file).read_text(encoding='utf-8')) if args.context_file else {}
        document=dict(schema_version=1,input_model='REAL_TICKS',timeframe='M1',symbol=args.symbol,
            point_size=values['point'],tick_size=values['trade_tick_size'],tick_value=values['trade_tick_value'],
            volume_min=values['volume_min'],volume_max=values['volume_max'],volume_step=values['volume_step'],
            stops_level_points=values.get('trade_stops_level',0),freeze_level_points=values.get('trade_freeze_level',0),
            timezone_offset_minutes=0,bars=bars,ticks_file='ticks.jsonl',ticks_sha256=evidence['sha256'],tick_context=context,
            acquisition={**evidence,'broker_server':identity.server,'timestamp_semantics':manifest['timestamp_semantics'],
                'metadata_assumption':'Current broker contract specification; historical changes are not supplied by MT5'})
        write_json(root/'ticks-dataset.json',document)
        report.update(status='COMPLETE_WITH_COVERAGE_LIMITS',ticks={**evidence,'path':str((root/'ticks-dataset.json').resolve())},
            finished_utc=datetime.now(timezone.utc).isoformat())
        write_json(root/'manifest.json',report);write_json(root/'progress.json',report)
    except Exception as error:
        report.update(status='FAILED',error=str(error));write_json(root/'progress.json',report);raise
    finally:mt5.shutdown()


if __name__=='__main__':main()
