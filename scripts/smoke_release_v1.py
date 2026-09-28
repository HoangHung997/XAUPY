"""Frozen release APIs, multiprocessing and data portability; no MT5 connection."""
import json
from pathlib import Path
import sys
import tempfile
import time

from smoke_task014_015_maintenance import engine_session, exchange
from smoke_task012_optimizer import create_dataset, task012_profile, sweep_request


def poll(stream,kind,terminal,*,payload=None,timeout=90):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        result=exchange(stream,kind,payload)
        assert result['ok'],result
        item=result['transfer' if kind=='data_transfer_status' else 'status']
        if item['status'] in terminal:return item
        time.sleep(.05)
    raise TimeoutError(f'{kind}: {item}')


def main():
    executable=str(Path(sys.argv[1]).resolve())
    with tempfile.TemporaryDirectory(prefix='xaupy-v1-smoke-') as directory:
        root=Path(directory);dataset=root/'history.json';create_dataset(dataset,days=15)
        with engine_session(executable,root/'first') as stream:
            profile=task012_profile(exchange(stream,'config_active_get')['profile'])
            assert exchange(stream,'config_active_set',dict(profile=profile))['applied']
            assert exchange(stream,'library_profile_save',dict(id='acceptance',profile=profile))['ok']
            assert exchange(stream,'startup_profile_set',dict(profile=profile))['ok']
            assert exchange(stream,'startup_profile_clear')['ok']
            request=sweep_request(dataset);request.update(to_date='2024-01-15',max_workers=2)
            started=exchange(stream,'research_start',request);assert started['ok'],started
            terminal=poll(stream,'optimizer_status',{'COMPLETED','FAILED','CANCELLED'},payload=dict(job_id=started['status']['job_id']))
            assert terminal['status']=='COMPLETED',terminal
            report=exchange(stream,'optimizer_result_get',dict(run_id=terminal['result_run_id']))['result']
            assert report['mode']=='RESEARCH' and report['workers_used']==2
            candidate=exchange(stream,'optimizer_candidate_prepare',dict(run_id=report['run_id'],index=report['research']['selected_index']))
            assert candidate['ok'],candidate
            assert exchange(stream,'config_active_get')['profile']==profile
            assert candidate['candidate']['profile']['execution']==profile['execution']
            archive=root/'portable.zip'
            assert exchange(stream,'data_transfer_start',dict(mode='EXPORT',path=str(archive)))['ok']
            exported=poll(stream,'data_transfer_status',{'COMPLETE','FAILED','CANCELLED'})
            assert exported['status']=='COMPLETE',exported
        with engine_session(executable,root/'second') as stream:
            before=exchange(stream,'config_active_get')['profile']
            assert exchange(stream,'data_transfer_start',dict(mode='IMPORT',path=str(archive)))['ok']
            imported=poll(stream,'data_transfer_status',{'COMPLETE','FAILED','CANCELLED'})
            assert imported['status']=='COMPLETE',imported
            assert any(p['id']=='acceptance' for p in exchange(stream,'library_profile_list')['profiles'])
            assert exchange(stream,'config_active_get')['profile']==before
            diagnostics=exchange(stream,'diagnostics_get')['diagnostics']
            assert diagnostics['execution']['mode']=='OFF'
            assert not diagnostics['bridge']['connected']
    print('PASS frozen research with two process workers, review without application, profile/startup library and verified data export/import; no broker connection or permission changes.')


if __name__=='__main__':main()
