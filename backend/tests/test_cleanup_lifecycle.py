from concurrent.futures import ThreadPoolExecutor
from threading import Event
from backend.app.db import Session, Run


def seed_wiki(client, wid):
    snap = client.post(f'/api/workspaces/{wid}/repository-link', json={'url':'https://github.com/example/demo'}).json()
    with Session.begin() as s:
        s.add(Run(workspace_id=wid, status='completed', request={'snapshot_id':snap['id']},
                  result={'wiki':{'generated_pages':{'p':{'content':'项目架构材料'}}}}, idempotency_key='source'))
    return snap


def test_cancelled_inline_generation_cannot_retry_in_analysis_queue_or_save(client, wid, monkeypatch):
    seed_wiki(client, wid)
    entered, release = Event(), Event()
    def writer(*args):
        entered.set()
        assert release.wait(10)
        # Deliberately ignores cooperative cancellation: persistence must still reject.
        return 'draft', {'kind':'writing_review','status':'passed'}
    monkeypatch.setattr('backend.app.resume_writer.write', writer)
    body = {'type':'resume','writing_mode':'model','idempotency_key':'first'}
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.post, f'/api/workspaces/{wid}/artifacts', json=body)
        try:
            assert entered.wait(10)
            run = next(r for r in client.get(f'/api/workspaces/{wid}').json()['runs'] if r['request'].get('resume_generation'))
            url = f'/api/runs/{run["id"]}'
            assert client.post(url+'/cancel', params={'workspace_id':wid}).json()['status']=='cancelled'
            assert client.post(url+'/retry', params={'workspace_id':wid}).status_code==409
            assert client.post(f'/api/workspaces/{wid}/artifacts', json=body).status_code==409
            assert client.post(f'/api/workspaces/{wid}/artifacts', json={**body,'idempotency_key':'different'}).status_code==409
        finally:
            release.set()
        assert pending.result().status_code==409
    w = client.get(f'/api/workspaces/{wid}').json()
    assert not w['artifacts']
    assert next(r for r in w['runs'] if r['id']==run['id'])['status']=='cancelled'
    # The original artifact command is the supported retry; source/context remain fixed.
    monkeypatch.setattr('backend.app.resume_writer.write', lambda *a:('draft',{'kind':'writing_review','status':'passed'}))
    assert client.post(f'/api/workspaces/{wid}/artifacts', json=body).status_code==200


def test_busy_workspace_rejects_model_generation_before_provider(client, wid, monkeypatch):
    seed_wiki(client, wid)
    with Session.begin() as s:
        s.add(Run(workspace_id=wid,status='running',request={'architecture':True},idempotency_key='busy'))
    monkeypatch.setattr('backend.app.resume_writer.write', lambda *a:(_ for _ in ()).throw(AssertionError('must not call provider')))
    assert client.post(f'/api/workspaces/{wid}/artifacts',json={'type':'resume','writing_mode':'model','idempotency_key':'blocked'}).status_code==409


def test_target_and_jd_routes_share_terms_history_and_invalidation(client, wid):
    jd = client.post(f'/api/workspaces/{wid}/jd-versions',json={'content':'Multi-Agent 长期记忆'}).json()
    client.post(f'/api/workspaces/{wid}/target',json={'role':'AI开发','jd':'Multi-Agent 长期记忆'})
    assert len(client.get(f'/api/workspaces/{wid}').json()['jd_versions'])==1
    client.post(f'/api/workspaces/{wid}/target',json={'role':'AI开发','jd':'MCP 工具编排'})
    w = client.get(f'/api/workspaces/{wid}').json()
    latest = w['jd_versions'][-1]
    assert latest['requirements']==['MCP','工具编排']
    assert latest['supersedes_id']==jd['id'] and latest['version']==2
    client.post(f'/api/workspaces/{wid}/target',json={'role':'AI开发','jd':''})
    assert client.get(f'/api/workspaces/{wid}').json()['jd_versions'][-1]['requirements']==[]


def test_harness_checks_cancellation_before_any_provider_call():
    from fastapi import HTTPException
    from backend.app.resume_harness import Harness
    import pytest
    def stopped():raise HTTPException(409,'cancelled')
    h = Harness(lambda p:(_ for _ in ()).throw(AssertionError('paid call')),check_active=stopped)
    with pytest.raises(HTTPException):h.call('WRITE\ntext')
    assert h.records==[]


def test_model_generation_does_not_render_rule_reference(client,wid,monkeypatch):
    seed_wiki(client,wid)
    monkeypatch.setattr('backend.app.artifact_service.compose',lambda *a:(_ for _ in ()).throw(AssertionError('rule rendering on model path')))
    monkeypatch.setattr('backend.app.resume_writer.write',lambda *a:('draft',{'kind':'writing_review','status':'passed'}))
    artifact=client.post(f'/api/workspaces/{wid}/artifacts',json={'type':'resume','writing_mode':'model','idempotency_key':'ledger'}).json()
    ledger=[c for c in artifact['claims'] if c.get('usage')=='source_ledger_not_generated_text']
    assert ledger and all('text' not in c for c in ledger)


def test_post_generation_failure_does_not_leave_running_job(client,wid,monkeypatch):
    from fastapi import HTTPException
    from backend.app.resume_writer import collect
    seed_wiki(client,wid)
    calls=[]
    def collector(*args):
        calls.append(1)
        if len(calls)>1:raise HTTPException(422,'最新材料已不可用')
        return collect(*args)
    monkeypatch.setattr('backend.app.resume_writer.collect',collector)
    monkeypatch.setattr('backend.app.resume_writer.write',lambda *a:('draft',{'kind':'writing_review','status':'passed'}))
    assert client.post(f'/api/workspaces/{wid}/artifacts',json={'type':'resume','writing_mode':'model','idempotency_key':'post-failure'}).status_code==422
    w=client.get(f'/api/workspaces/{wid}').json()
    assert not w['artifacts']
    assert next(r for r in w['runs'] if r['request'].get('resume_generation'))['status']=='failed'


def test_generation_admission_is_scoped_to_workspace(client,wid,monkeypatch):
    other=client.post('/api/workspaces',json={'interest':'other','role':'AI'}).json()['id']
    seed_wiki(client,wid);seed_wiki(client,other)
    entered,release=Event(),Event()
    def writer(snapshot,material):
        if material['workspace_id']==wid:
            entered.set();assert release.wait(10)
        return 'draft',{'kind':'writing_review','status':'passed'}
    monkeypatch.setattr('backend.app.resume_writer.write',writer)
    body={'type':'resume','writing_mode':'model','idempotency_key':'scoped'}
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(client.post,f'/api/workspaces/{wid}/artifacts',json=body)
        try:
            assert entered.wait(10)
            result=client.post(f'/api/workspaces/{other}/artifacts',json=body)
            assert result.status_code==200 and result.json()['workspace_id']==other
        finally:release.set()
        assert pending.result().status_code==200
