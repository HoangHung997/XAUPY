"""Background broker-history acquisition; no blocking native call on IPC."""
from __future__ import annotations
from datetime import datetime, timezone
import json
import hashlib
import sqlite3
import os
from pathlib import Path
import subprocess
import sys
import uuid
from .history_jobs import HistoryJobs
from .broker_history import query_report


class BrokerHistoryJobs(HistoryJobs):
    def __init__(self, root: Path):
        super().__init__(root)
        self.root=root/'broker-history'

    def start(self, terminal: str, identity: dict) -> dict:
        if self.process is not None and self.process.poll() is None: raise ValueError('History import already running')
        path=Path(terminal)
        if not path.is_absolute() or not path.is_file() or path.name.lower()!='terminal64.exe': raise ValueError('Select MT5 terminal64.exe in Settings')
        if type(identity.get('account_login')) is not int or not identity.get('account_server') or type(identity.get('magic')) is not int: raise ValueError('Fresh Bridge identity required')
        self.job_dir=self.root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8])
        self.job_dir.mkdir(parents=True)
        request=self.job_dir/'request.json'
        request.write_text(json.dumps(dict(terminal=str(path),identity=identity)),encoding='utf-8')
        command=[sys.executable]+([] if getattr(sys,'frozen',False) else ['-m','xaupy_engine.main'])+['--collect-broker-history',str(request)]
        env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]),PYINSTALLER_RESET_ENVIRONMENT='1')
        if self.output is not None: self.output.close()
        self.output=(self.job_dir/'collector.log').open('wb')
        try:
            self.process=subprocess.Popen(command,stdout=self.output,stderr=subprocess.STDOUT,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except OSError:
            self.output.close(); self.output=None
            raise
        return self.status()

    def query(self, identity: dict, report_id=None, **kwargs) -> dict:
        candidates={p.parent.name:p for p in self.root.glob('*/broker-history.sqlite')}
        for marker in (self.root.parent/'imports').glob('*/import-complete.json'):
            for path in (marker.parent/'broker-history').glob('*/broker-history.sqlite'):
                key='import-'+hashlib.sha256(str(path.relative_to(self.root.parent)).encode()).hexdigest()[:24]
                candidates[key]=path
        if report_id:
            if not isinstance(report_id,str) or report_id not in candidates: raise ValueError('Invalid report id')
            candidates={report_id:candidates[report_id]}
        matched=[]
        for key,path in candidates.items():
            try:
                result=query_report(path,identity,**kwargs)
                matched.append(dict(report_id=key,**result))
            except (ValueError,TypeError,KeyError,sqlite3.Error,OSError) as exc:
                if report_id:raise ValueError(str(exc)) from exc
        if matched:return max(matched,key=lambda r:r['metadata'].get('imported_utc',''))
        raise ValueError('No history for this account/magic; import from MT5 first')
