"""Incremental read-only MT5 Experts/Journal intake on a background worker."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
from .settings import _atomic_json


class Mt5LogReader:
    def __init__(self,root,journal):
        self.path=root/'mt5-log-cursors-v1.json';self.journal=journal
        try:self.cursors=json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError,ValueError):self.cursors={}
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='mt5-log-reader')
        self.future=None;self.status={'available':False,'reason':'WAITING_FOR_TERMINAL_PATH','imported':0}

    def poll(self,snapshot):
        value=snapshot.get('terminal_data_path')
        if self.future is not None and not self.future.done():return dict(self.status)
        if self.future is not None:
            try:self.future.result()
            except Exception as error:self.status={'available':False,'reason':str(error),'imported':self.status.get('imported',0)}
            self.future=None
        if isinstance(value,str) and value:
            root=Path(value)
            if root.is_absolute() and root.is_dir():self.future=self.pool.submit(self.read_once,root)
        return dict(self.status)

    def read_once(self,root):
        count=0;files=[]
        for folder,tag in ((root/'Logs','MT5_JOURNAL'),(root/'MQL5'/'Logs','MT5_EXPERTS')):
            candidates=sorted((p for p in folder.glob('*.log') if re.fullmatch(r'\d{8}\.log',p.name) and not p.is_symlink()),reverse=True)
            if not candidates:continue
            path=candidates[0];files.append(str(path));key=str(path.resolve())
            cursor=self.cursors.get(key,{})
            # A rewritten/truncated file starts a new generation, retaining its
            # original raw messages and byte offsets for duplicate reconciliation.
            with path.open('rb') as stream:
                prefix_length=int(cursor.get('prefix_length',min(128,path.stat().st_size)))
                prefix=stream.read(prefix_length);signature=hashlib.sha256(prefix).hexdigest()
                offset=int(cursor.get('offset',0))
                if offset>path.stat().st_size or (cursor.get('signature') and cursor['signature']!=signature):
                    offset=0;prefix_length=min(128,path.stat().st_size);stream.seek(0)
                    prefix=stream.read(prefix_length);signature=hashlib.sha256(prefix).hexdigest()
                encoding='utf-16-le' if prefix.startswith(b'\xff\xfe') or b'\x00' in prefix else 'utf-8-sig'
                stream.seek(offset);raw=stream.read(256*1024)
            separator=b'\n\x00' if encoding=='utf-16-le' else b'\n'
            last=raw.rfind(separator)
            if last<0:continue # An incomplete final line is retried without loss.
            complete=raw[:last+len(separator)]
            consumed=0
            for line in complete.split(separator)[:-1]:
                text=line.decode(encoding,errors='replace').lstrip('\ufeff').strip()
                identity=hashlib.sha256(f'{key}:{signature}:{offset+consumed}'.encode()).hexdigest()
                consumed+=len(line)+len(separator)
                if not text:continue
                columns=text.split('\t');level='INFO'
                # MT5 native severity column is 0=info, 1=error, 2=warning.
                if len(columns)>1:level={'1':'ERROR','2':'WARN'}.get(columns[1].strip(),'INFO')
                self.journal.append(level,'MT5',tag,text[:16000],correlation_id=identity,
                    details={'source_file':key,'byte_offset':offset+consumed-len(line)-len(separator),
                        'native_raw_line':text[:16000],'native_line_characters':len(text),'truncated':len(text)>16000,
                        'timestamp_basis':'IMPORT_UTC; original terminal time retained in raw line'})
                count+=1
            self.cursors[key]={'offset':offset+len(complete),'signature':signature,'prefix_length':prefix_length}
        if count:_atomic_json(self.path,self.cursors)
        self.status={'available':bool(files),'source_files':files,'imported':self.status.get('imported',0)+count,
                     'scope':'Latest native Journal and Experts log files; complete lines only'}
        return dict(self.status)

    def close(self):self.pool.shutdown(wait=True,cancel_futures=True)
