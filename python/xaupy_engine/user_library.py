"""User-owned versioned profiles, history catalogue and explicit calendar import."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from .config_schema import normalized_profile, validate_profile
from .settings import _atomic_json


class UserLibrary:
    def __init__(self, root: Path):
        self.root=root
        self.profiles=root/'profiles'
        self.calendar_path=root/'calendar-import-v1.json'
        self.calendar=None
        if self.calendar_path.exists():
            try: self.calendar=self.validate_calendar(json.loads(self.calendar_path.read_text(encoding='utf-8')))
            except (ValueError,KeyError,TypeError,OSError): pass

    @staticmethod
    def key(value):
        if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',value): raise ValueError('Use 1..64 letters, digits, _ or - for profile id')
        return value

    def save_profile(self, key, profile):
        key=self.key(key)
        errors=validate_profile(profile)
        if errors: raise ValueError('; '.join(errors))
        profile=normalized_profile(profile)
        digest=hashlib.sha256(json.dumps(profile,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        path=self.profiles/key/(digest+'.json')
        if not path.exists(): _atomic_json(path,dict(profile=profile,sha256=digest,saved_utc=datetime.now(timezone.utc).isoformat()))
        return dict(id=key,revision=digest,profile=profile)

    def profile_list(self):
        rows=[]
        for path in self.profiles.glob('*/*.json'):
            try:
                doc=json.loads(path.read_text(encoding='utf-8'))
                rows.append(dict(id=path.parent.name,revision=path.stem,name=doc['profile']['profile']['name'],saved_utc=doc['saved_utc']))
            except (ValueError,KeyError,OSError): continue
        return sorted(rows,key=lambda r:r['saved_utc'],reverse=True)

    def profile_get(self,key,revision):
        key=self.key(key)
        if not isinstance(revision,str) or not re.fullmatch('[0-9a-f]{64}',revision): raise ValueError('Invalid profile revision')
        profile=json.loads((self.profiles/key/(revision+'.json')).read_text(encoding='utf-8'))['profile']
        if hashlib.sha256(json.dumps(profile,sort_keys=True,ensure_ascii=False).encode()).hexdigest()!=revision:
            raise ValueError('Stored profile revision failed integrity check')
        errors=validate_profile(profile)
        if errors: raise ValueError('; '.join(errors))
        return profile

    def history_catalog(self):
        rows=[]
        paths=list((self.root/'market-history').glob('*/manifest.json'))
        for marker in (self.root/'imports').glob('*/import-complete.json'):
            paths.extend((marker.parent/'market-history').glob('*/manifest.json'))
        for path in paths:
            try:
                doc=json.loads(path.read_text(encoding='utf-8'))
                ticks=doc.get('ticks',{})
                tick_file=Path(ticks.get('path','')).resolve()
                if ticks.get('tick_count') and tick_file.is_relative_to(path.parent.resolve()) and tick_file.is_file():
                    rows.append(dict(id=path.parent.name,timeframe='TICKS',symbol=doc['symbol'],path=str(tick_file),
                        rows=ticks['tick_count'],earliest_time=ticks['first_time_msc']//1000,latest_time=ticks['last_time_msc']//1000,
                        sha256=ticks['sha256'],status=doc['status'],broker_server=doc.get('broker_server')))
                for timeframe,item in doc['timeframes'].items():
                    file=Path(item.get('path','')).resolve()
                    if not file.is_relative_to(path.parent.resolve()) or not file.is_file() or not item.get('rows'): continue
                    rows.append(dict(id=path.parent.name,timeframe=timeframe,symbol=doc['symbol'],path=str(file),
                        rows=item['rows'],earliest_time=item.get('earliest_time'),latest_time=item.get('latest_time'),
                        sha256=item.get('sha256'),status=item.get('status'),broker_server=doc.get('broker_server')))
            except (ValueError,KeyError,TypeError,OSError): continue
        return sorted(rows,key=lambda r:(r['id'],r['timeframe']),reverse=True)

    def save_startup_profile(self,profile):
        saved=self.save_profile('startup-default',profile)
        _atomic_json(self.root/'startup-profile-v1.json',dict(id=saved['id'],revision=saved['revision']))
        return saved

    def startup_profile(self):
        path=self.root/'startup-profile-v1.json'
        if not path.exists(): return None
        saved=json.loads(path.read_text(encoding='utf-8'))
        return self.profile_get(saved['id'],saved['revision'])

    def clear_startup_profile(self):
        (self.root/'startup-profile-v1.json').unlink(missing_ok=True)
        return {'cleared':True}

    @staticmethod
    def validate_calendar(doc):
        if not isinstance(doc,dict): raise ValueError('Calendar needs coverage_start_utc, coverage_end_utc and events')
        def timestamp(value):
            if not isinstance(value,str): raise ValueError('Calendar timestamp must be ISO 8601 with timezone')
            dt=datetime.fromisoformat(value.replace('Z','+00:00'))
            if dt.tzinfo is None: raise ValueError('Calendar timestamp requires a timezone')
            return int(dt.timestamp())
        start,end=timestamp(doc.get('coverage_start_utc')),timestamp(doc.get('coverage_end_utc'))
        if end<=start or end-start>366*86400: raise ValueError('Calendar coverage must be positive and at most 366 days')
        events=doc.get('events')
        if not isinstance(events,list) or len(events)>10000: raise ValueError('Calendar events must be an array of at most 10000')
        for event in events:
            if not isinstance(event,dict): raise ValueError('Calendar event must be an object')
            t=timestamp(event.get('timestamp_utc'))
            if not start<=t<=end: raise ValueError('Event outside declared coverage')
            if not re.fullmatch('[A-Z]{3}',str(event.get('currency',''))) or event.get('impact') not in ('HIGH','MEDIUM','LOW') or not isinstance(event.get('title'),str) or not 1<=len(event['title'])<=300:
                raise ValueError('Calendar event needs currency, impact HIGH/MEDIUM/LOW and title')
        return json.loads(json.dumps(doc))

    def save_calendar(self,doc):
        accepted=self.validate_calendar(doc)
        _atomic_json(self.calendar_path,accepted)
        self.calendar=accepted
        return dict(events=len(accepted['events']),coverage_start_utc=accepted['coverage_start_utc'],coverage_end_utc=accepted['coverage_end_utc'])

    def merge_calendar(self,snapshot):
        if not self.calendar: return snapshot
        now=snapshot.get('server_time'); offset=snapshot.get('server_utc_offset_seconds')
        if type(now) is not int or type(offset) not in (int,float): return snapshot
        def epoch(value): return int(datetime.fromisoformat(value.replace('Z','+00:00')).timestamp())
        start=epoch(self.calendar['coverage_start_utc'])+offset
        end=epoch(self.calendar['coverage_end_utc'])+offset
        if not start<=now<=end: return snapshot
        native=snapshot.get('calendar') or {}
        events=list(native.get('events',[])) if native.get('available') else []
        currencies={snapshot.get('currency_base'),snapshot.get('currency_profit')}
        if not any(currencies): currencies={snapshot.get('symbol','')[-3:]}
        for e in self.calendar['events']:
            if e['currency'] in currencies:
                events.append(dict(time=epoch(e['timestamp_utc'])+offset,currency=e['currency'],importance=e['impact'],name=e['title'],source='USER_IMPORT'))
        return {**snapshot,'calendar':dict(available=True,as_of=now,source='MT5 + USER_IMPORT' if native.get('available') else 'USER_IMPORT',
            coverage_start=start,coverage_end=end,events=sorted(events,key=lambda e:e['time']))}
