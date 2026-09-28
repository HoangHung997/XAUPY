"""Portable, verified data archives. Imports never grant trading permissions."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import threading
from uuid import uuid4
import zipfile
from .settings import _atomic_json
from .user_library import UserLibrary

MAX_BYTES=20*1024**3
MAX_FILES=100000
SUFFIXES={'.json','.jsonl','.csv','.html','.log','.txt','.sqlite','.sqlite3'}


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


class DataTransfer:
    def __init__(self,state,logs,backtests,optimizers):
        self.state=Path(state)
        self.roots={'profiles':self.state/'profiles','market-history':self.state/'market-history',
                    'logs':Path(logs),'backtests':Path(backtests),'optimizers':Path(optimizers),
                    'broker-history':self.state/'broker-history'}
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='xaupy-data')
        self.lock=threading.Lock();self.future=None;self.stop=threading.Event()
        self.current={'status':'IDLE'}

    def status(self):
        with self.lock:return dict(self.current)

    def _update(self,**values):
        with self.lock:self.current.update(values)

    def start(self,mode,path):
        if mode not in ('EXPORT','IMPORT'):raise ValueError('Unknown transfer mode')
        if not isinstance(path,str) or not Path(path).is_absolute() or Path(path).suffix.lower()!='.zip':
            raise ValueError('Choose an absolute .zip path')
        with self.lock:
            if self.future is not None and not self.future.done():raise ValueError('A data transfer is already running')
            self.stop.clear();self.current=dict(status='QUEUED',mode=mode,path=path,files=0,bytes=0)
            self.future=self.pool.submit(self._run,mode,Path(path))
        return self.status()

    def _check(self):
        if self.stop.is_set():raise ValueError('Transfer cancelled')

    def close(self):
        self.stop.set();self.pool.shutdown(wait=True,cancel_futures=True)

    def cancel(self):
        self.stop.set();return self.status()

    def _run(self,mode,path):
        try:
            self._update(status='RUNNING')
            result=self.export(path) if mode=='EXPORT' else self.import_archive(path)
            self._update(status='COMPLETE',**result)
        except Exception as exc:
            self._update(status='CANCELLED' if self.stop.is_set() else 'FAILED',error=str(exc))

    def export(self,path):
        # Existing archives are never truncated: the picker must supply a new
        # name. A failed export removes only its own uniquely named temp file.
        if path.exists():raise ValueError('Archive already exists; choose a new file name')
        path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_name('.xaupy-'+uuid4().hex+'.zip.tmp')
        database_snapshot=temp.with_suffix('.sqlite.tmp')
        entries=[];total=0
        try:
            with zipfile.ZipFile(temp,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as archive:
                sources=[(group,p,p.relative_to(root).as_posix()) for group,root in self.roots.items()
                         if root.is_dir() for p in root.rglob('*') if p.is_file() and p.suffix.lower() in SUFFIXES
                         and p.resolve().is_relative_to(root.resolve())]
                # Carry previously imported archives through subsequent exports.
                # Analysis results/profiles already have active library copies.
                for marker in (self.state/'imports').glob('*/import-complete.json'):
                    for group in ('market-history','broker-history','logs','calendar'):
                        base=marker.parent/group
                        for source in base.rglob('*'):
                            if not source.is_file() or source.suffix.lower() not in SUFFIXES or not source.resolve().is_relative_to(base.resolve()):continue
                            relative=source.relative_to(base)
                            collection=relative.parts[0] if group in ('market-history','broker-history') else ''
                            namespace='import-'+hashlib.sha256((marker.parent.name+'/'+collection).encode()).hexdigest()[:16]
                            tail=Path(*relative.parts[1:]) if collection else relative
                            sources.append((group,source,(Path(namespace)/tail).as_posix()))
                calendar=self.state/'calendar-import-v1.json'
                if calendar.is_file():sources.append(('calendar',calendar,calendar.name))
                for group,source,relative in sorted(sources):
                    self._check();name=group+'/'+relative;h=hashlib.sha256();size=0
                    if source.suffix in ('.sqlite','.sqlite3'):
                        database_snapshot.unlink(missing_ok=True)
                        original=sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)
                        copy=sqlite3.connect(database_snapshot)
                        try:original.backup(copy,pages=256,progress=lambda *_:self._check())
                        finally:original.close();copy.close()
                        source=database_snapshot
                    # Freeze the initial length so a growing journal cannot
                    # make this a never-ending export. Hash exactly copied bytes.
                    remaining=source.stat().st_size
                    if total+remaining>MAX_BYTES or len(entries)>=MAX_FILES:raise ValueError('Data bundle exceeds size/file limit')
                    with source.open('rb') as incoming,archive.open(name,'w',force_zip64=True) as outgoing:
                        while remaining:
                            self._check();chunk=incoming.read(min(1024*1024,remaining))
                            if not chunk:raise ValueError('Source changed during export; retry after writer completes')
                            outgoing.write(chunk);h.update(chunk);size+=len(chunk);remaining-=len(chunk)
                    total+=size;entries.append(dict(path=name,size=size,sha256=h.hexdigest()))
                    self._update(files=len(entries),bytes=total)
                manifest=dict(schema_version=1,kind='XAUPY_DATA_BUNDLE',created_utc=datetime.now(timezone.utc).isoformat(),
                    files=entries,scope='Profiles, history, research, reports and log archives. No runtime settings, execution ledger or trading permissions.')
                archive.writestr('bundle-manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
            self._check()
            # Hard-link provides atomic create-if-absent on the same volume.
            path.hardlink_to(temp)
            return dict(files=len(entries),bytes=total,sha256=digest(path))
        finally:
            temp.unlink(missing_ok=True);database_snapshot.unlink(missing_ok=True)

    @staticmethod
    def _safe_name(name):
        p=PurePosixPath(name)
        if (not name or '\\' in name or ':' in name or p.is_absolute() or '..' in p.parts or
            str(p)!=name or any(part.endswith((' ','.')) for part in p.parts)):
            raise ValueError('Unsafe archive path')
        return p

    def import_archive(self,path):
        session=uuid4().hex;stage=self.state/'imports'/('.pending-'+session)
        final=self.state/'imports'/session
        stage.mkdir(parents=True,exist_ok=False)
        total=0
        try:
            with zipfile.ZipFile(path) as archive:
                if len(archive.infolist())>MAX_FILES+1:raise ValueError('Too many bundle files')
                info=archive.getinfo('bundle-manifest.json')
                if info.file_size>16*1024**2:raise ValueError('Bundle manifest too large')
                manifest=json.loads(archive.read(info))
                if manifest.get('schema_version')!=1 or manifest.get('kind')!='XAUPY_DATA_BUNDLE':raise ValueError('Not a supported XAUPY data bundle')
                entries=manifest.get('files')
                if not isinstance(entries,list):raise ValueError('Missing bundle file table')
                names=[entry.get('path') for entry in entries]
                if len(names)!=len(set(names)) or len(archive.namelist())!=len(set(archive.namelist())) or set(archive.namelist())!=set(names)|{'bundle-manifest.json'}:
                    raise ValueError('Duplicate or unlisted bundle entries')
                for index,entry in enumerate(entries):
                    self._check();name=self._safe_name(entry['path']);size=entry['size']
                    if name.parts[0] not in {*self.roots,'calendar'} or len(name.parts)<2 or name.suffix not in SUFFIXES:raise ValueError('Unsupported data category')
                    if type(size) is not int or size<0 or total+size>MAX_BYTES:raise ValueError('Bundle size exceeds limit')
                    member=archive.getinfo(str(name))
                    if member.file_size!=size or (member.external_attr>>16)&0o170000==0o120000:raise ValueError('Invalid archive member')
                    target=stage/str(name);target.parent.mkdir(parents=True,exist_ok=True)
                    h=hashlib.sha256();copied=0
                    with archive.open(member) as incoming,target.open('xb') as outgoing:
                        while chunk:=incoming.read(1024*1024):
                            self._check();copied+=len(chunk)
                            if copied>size:raise ValueError('Expanded size mismatch')
                            outgoing.write(chunk);h.update(chunk)
                    if copied!=size or h.hexdigest()!=entry['sha256']:raise ValueError('Bundle integrity mismatch')
                    total+=size;self._update(files=index+1,bytes=total)
            # Validate before publishing any imported data. Imported profiles
            # remain drafts. Logs/calendar remain in the inspectable archive.
            library=UserLibrary(stage)
            imported_profiles=[]
            for file in (stage/'profiles').glob('*/*.json'):
                imported_profiles.append((file.parent.name,library.profile_get(file.parent.name,file.stem)))
            imported_results=[]
            for group in ('backtests','optimizers'):
                for file in (stage/group).glob('*.json'):
                    data=json.loads(file.read_text(encoding='utf-8'))
                    if not isinstance(data,dict) or 'run_id' not in data or not isinstance(data.get('metrics' if group=='backtests' else 'base_profile'),dict):raise ValueError('Invalid imported result')
                    if group=='optimizers':
                        from .optimizer import _optimizer_hash
                        hashed={k:v for k,v in data.items() if k not in ('optimizer_hash','workers_used','run_id','created_at_utc')}
                        if _optimizer_hash(hashed)!=data.get('optimizer_hash'):raise ValueError('Optimizer result integrity mismatch')
                    else:
                        from .tick_backtest import TICK_BACKTEST_MODEL
                        tick=data.get('model')==TICK_BACKTEST_MODEL
                        excluded={'result_hash','run_id','created_at_utc'} | (set() if tick else {'dataset_file_name'})
                        hashed={k:v for k,v in data.items() if k not in excluded}
                        actual=hashlib.sha256(json.dumps(hashed,ensure_ascii=tick,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                        if actual!=data.get('result_hash'):raise ValueError('Backtest result integrity mismatch')
                    imported_results.append((group,data))
            self._check()
            imports=(self.state/'imports').resolve()
            if not stage.resolve().is_relative_to(imports) or not final.resolve().is_relative_to(imports):raise ValueError('Invalid import destination')
            stage.rename(final)
            # History paths were local on the source computer. Rebase only
            # paths pointing to files carried in this same verified bundle.
            for manifest_path in (final/'market-history').glob('*/manifest.json'):
                doc=json.loads(manifest_path.read_text(encoding='utf-8'))
                for row in [*doc.get('timeframes',{}).values(),doc.get('ticks',{})]:
                    if not row.get('path'):continue
                    leaf=PurePosixPath(str(row['path']).replace('\\','/')).name
                    rebound=manifest_path.parent/leaf
                    if not rebound.is_file():raise ValueError('History references a missing bundled file')
                    row['path']=str(rebound.resolve())
                _atomic_json(manifest_path,doc)
            # Publish manifest last. Consumers ignore incomplete imports.
            _atomic_json(final/'import-complete.json',dict(files=len(entries),bytes=total,source_sha256=digest(path)))
            library=UserLibrary(self.state)
            for key,profile in imported_profiles:library.save_profile(key,profile)
            for group,data in imported_results:
                data['run_id']=str(uuid4())
                _atomic_json(self.roots[group]/(data['run_id']+'.json'),data)
            return dict(files=len(entries),bytes=total,import_directory=str(final),
                note='Imported analysis data is available in the library; profiles and calendar require explicit application. Trading settings unchanged.')
        finally:
            if stage.exists() and stage.resolve().is_relative_to((self.state/'imports').resolve()):shutil.rmtree(stage)
