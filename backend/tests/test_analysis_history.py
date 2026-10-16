from datetime import datetime
from backend.app.db import Session,Run,Workspace
from backend.app import analysis
from backend.app.providers import ProviderError

def test_clear_all_project_history_preserves_active_and_retired_runs(client,wid,monkeypatch):
    other=client.post('/api/workspaces',json={'interest':'other project'}).json()['id']
    protected=None
    with Session.begin() as s:
        for workspace,status,request,key in [(wid,'failed',{'architecture':True},'failed'),(other,'completed',{'architecture':True},'done'),(wid,'running',{'architecture':True},'active'),(wid,'completed',{'resume_generation':True},'retired'),(wid,'cancelled',{'architecture':True},'stopping')]:
            r=Run(workspace_id=workspace,status=status,request=request,result={},idempotency_key=key);s.add(r);s.flush()
            if key=='stopping':protected=r.id
    monkeypatch.setattr('backend.app.main.still_executing',lambda rid:rid==protected)
    result=client.delete('/api/analysis-history');assert result.status_code==200
    assert result.json()=={'deleted_count':2,'protected_count':2}
    with Session() as s:
        assert s.get(Workspace,wid) and s.get(Workspace,other)
        assert sorted(r.idempotency_key for r in s.query(Run).all())==['active','retired','stopping']
    assert client.delete('/api/analysis-history').json()['deleted_count']==0

def test_failure_records_frozen_elapsed_time_and_retry_resets_clock(client,wid,monkeypatch):
    monkeypatch.setattr('backend.app.main.submit',lambda rid:None)
    snap=client.post(f'/api/workspaces/{wid}/repository-link',json={'url':'https://github.com/offline/project'}).json()
    run=client.post(f'/api/workspaces/{wid}/architecture-runs',json={'snapshot_id':snap['id'],'idempotency_key':'timing','demo':False}).json();rid=run['id']
    monkeypatch.setattr(analysis,'execute_architecture',lambda *a:(_ for _ in ()).throw(ProviderError('offline failure','offline')))
    analysis.execute(rid)
    result=client.get(f'/api/runs/{rid}?workspace_id={wid}').json()
    assert result['status']=='failed' and result['result']['elapsed_seconds']>=0
    assert datetime.fromisoformat(result['result']['analysis_started_at'])<=datetime.fromisoformat(result['result']['analysis_finished_at'])
    retried=client.post(f'/api/runs/{rid}/retry?workspace_id={wid}').json()
    assert retried['status']=='queued' and 'elapsed_seconds' not in retried['result'] and 'queued_at' in retried['result']
    cancelled=client.post(f'/api/runs/{rid}/cancel?workspace_id={wid}').json()
    elapsed=cancelled['result']['elapsed_seconds']
    assert client.post(f'/api/runs/{rid}/cancel?workspace_id={wid}').json()['result']['elapsed_seconds']==elapsed
