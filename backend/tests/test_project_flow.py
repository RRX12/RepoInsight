import json
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from backend.app.db import Session,Improvement,Artifact,Run
from backend.app.providers import ProviderError
from backend.app.discussion_contract import Question,Plan
from backend.app import discussion_memory as memory
from backend.app.optimization_review import generate
from backend.tests.analysis_fixture import Stub,MATERIAL,SHA
from backend.tests.source_fixture import Reader,Retriever
from backend.tests.test_shared_analysis import report

def optimize(material=MATERIAL,model=None,reader=None,check=lambda:None):
    stub=model or Stub()
    def call(prompt):
        if prompt.startswith('OPTIMIZATION_PLAN'):return json.dumps(report())
        if prompt.startswith('OPTIMIZATION_CHECK'):return json.dumps({'approved':True,'issues':[]})
        return stub(prompt)
    return generate(SimpleNamespace(id='s',commit_sha=material['commit']),material,lambda *a:None,check,call,reader or Reader(),Retriever())

def test_repeated_optimization_reuses_verified_project_analysis():
    _,a=optimize();stub=Stub();_,b=optimize(model=stub)
    assert a['analysis_pack_id']==b['analysis_pack_id'] and stub.calls==[]

@pytest.mark.parametrize('field,value',[('jd','恢复机制'),('workspace_id','other'),('commit','b'*40),('project_corrections',[{'excerpt':'已有恢复'}])])
def test_project_material_change_invalidates_analysis(field,value):
    _,a=optimize();stub=Stub();_,b=optimize({**MATERIAL,field:value},stub)
    assert a['analysis_pack_id']!=b['analysis_pack_id']
    assert any(stage=='JD_PLAN' for stage,_ in stub.calls)

def test_analysis_cache_corruption_and_cancellation_are_not_ignored(tmp_path):
    optimize();stub=Stub()
    def stop():raise ProviderError('已取消','cancelled')
    with pytest.raises(ProviderError,match='已取消'):optimize(model=stub,check=stop)
    assert not stub.calls
    cache=next((tmp_path/'analysis/shared/offline').glob('*.json'))
    data=json.loads(cache.read_text(encoding='utf-8'));data['discovery']['claims'][0]['statement']='tampered'
    cache.write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises(ProviderError) as error:optimize(model=stub)
    assert error.value.code=='analysis_cache' and not stub.calls

def test_failed_downstream_keeps_verified_pack():
    stub=Stub()
    def failed(prompt):
        if prompt.startswith('OPTIMIZATION_PLAN'):raise ProviderError('offline failure','offline_failure')
        return stub(prompt)
    with pytest.raises(ProviderError):generate(SimpleNamespace(id='s',commit_sha=SHA),MATERIAL,lambda *a:None,lambda:None,failed,Reader(),Retriever())
    second=Stub();optimize(model=second);assert not second.calls

def test_fixed_source_budget_keeps_single_supplement(monkeypatch):
    monkeypatch.setenv('RESUME_SOURCE_FILES','2');reader=Reader();stub=Stub()
    def call(prompt):
        d=json.loads(stub(prompt))
        if prompt.startswith('INVESTIGATE\n'):d['next_reads']=[{'path':'caller.ts','terms':['guard'],'reason':'调用方未读'}]
        if prompt.startswith('SYNTHESIZE\n'):d['next_reads']=[{'path':'caller.ts','terms':['other'],'reason':'不能再次请求'}];d['unresolved_questions']=['调用链未证实']
        return json.dumps(d)
    _,audit=optimize(model=call,reader=reader)
    assert len({p for p,_ in reader.reads})==2
    assert sum(stage=='SYNTHESIZE' for stage,_ in stub.calls)==1 and audit['analysis_gaps']

def test_resume_routes_removed_and_history_preserved(client,wid):
    routes=client.get('/openapi.json').json()['paths']
    assert '/api/workspaces/{wid}/artifacts' not in routes
    for path in ['editor','generate','review','decision']:assert '/api/workspaces/{wid}/interaction/'+path not in routes
    with Session.begin() as s:
        a=Artifact(workspace_id=wid,type='resume',version=1,content='历史文本',idempotency_key='old');s.add(a);s.flush();aid=a.id
    assert client.get('/api/artifacts/'+aid,params={'workspace_id':wid}).json()['content']=='历史文本'
    state=client.get(f'/api/workspaces/{wid}/interaction').json()
    response=client.post(f'/api/workspaces/{wid}/interaction/mutations',json={'expected_version':state['version'],'mutation_id':'retired','operations':[{'op':'request_resume_generation','data':{}}]})
    assert response.status_code==422

def test_repository_analysis_does_not_require_role_or_jd(client,wid,monkeypatch):
    from backend.app.db import Workspace
    with Session.begin() as s:s.get(Workspace,wid).role='待填写'
    snapshot=client.post(f'/api/workspaces/{wid}/repository-link',json={'url':'https://github.com/example/demo'}).json()
    monkeypatch.setattr('backend.app.main.submit',lambda rid:None)
    response=client.post(f'/api/workspaces/{wid}/architecture-runs',json={'snapshot_id':snapshot['id'],'idempotency_key':'no-role'})
    assert response.status_code==200 and response.json()['request']['role']=='项目工程优化'

def direction(wid):
    with Session.begin() as s:
        item=Improvement(workspace_id=wid,status='proposed',details={'title':'版本检查','proposal':'先比较失效策略，尚未实施','version':1});s.add(item);s.flush();return item.id

def test_direction_discussion_context_is_scoped_and_changes_cancel_late_result(client,wid):
    iid=direction(wid);cid=memory.open_conversation(wid,'discussion')['id']
    q=Question(request_id='direction',expected_revision=memory.view(wid,cid)['revision'],content='这个方案的代价是什么？',improvement_id=iid)
    ticket=memory.begin(wid,cid,q)
    assert ticket['direction_context']['details']['proposal']=='先比较失效策略，尚未实施'
    assert '不能视为已经实现' in ticket['direction_context']['fact_boundary']
    with Session.begin() as s:
        item=s.get(Improvement,iid);item.details={**item.details,'proposal':'方案已更正','version':2}
    assert not memory.finish(wid,cid,ticket,'completed','旧方案答案',Plan())
    assert all(m['content']!='旧方案答案' for m in memory.view(wid,cid)['messages'])
    other=client.post('/api/workspaces',json={'interest':'other'}).json()['id'];cid2=memory.open_conversation(other,'discussion')['id']
    with pytest.raises(HTTPException) as error:memory.begin(other,cid2,q.model_copy(update={'expected_revision':0}))
    assert error.value.status_code==404

def test_deleted_direction_cannot_be_discussed_or_accept_late_answer(client,wid):
    iid=direction(wid);cid=memory.open_conversation(wid,'discussion')['id']
    q=Question(request_id='before-delete',expected_revision=0,content='比较方案',improvement_id=iid);ticket=memory.begin(wid,cid,q)
    with Session.begin() as s:s.get(Improvement,iid).details={'deleted':True}
    assert not memory.finish(wid,cid,ticket,'completed','晚到答案',Plan())
    with pytest.raises(HTTPException) as error:memory.begin(wid,cid,q.model_copy(update={'request_id':'after-delete','expected_revision':memory.view(wid,cid)['revision']}))
    assert error.value.status_code==409

def test_direction_context_reaches_answer_envelope_without_business_changes(client,wid,monkeypatch):
    from backend.tests.test_discussion_memory import material
    from backend.app import wiki_chat
    run=material(wid);iid=direction(wid);cid=memory.open_conversation(wid,'discussion')['id'];seen=[]
    monkeypatch.setenv('DEEPWIKI_BASE_URL','http://test')
    async def stream(base,payload):
        seen.append(json.loads(payload['messages'][0]['content']))
        yield wiki_chat.event(delta='需要核对失效边界，建议不是已实施成果')
        yield wiki_chat.event(done=True)
    monkeypatch.setattr(wiki_chat,'stream',stream)
    before=client.get(f'/api/workspaces/{wid}').json()
    result=client.post(f'/api/workspaces/{wid}/conversations/{cid}/turns',json={'request_id':'proposal-stream','expected_revision':0,'content':'方案有什么取舍？','run_id':run,'improvement_id':iid})
    assert '"done": true' in result.text,result.text
    proposal=next(e for e in seen[0]['evidence'] if e['kind']=='optimization_proposal')
    assert proposal['details']['proposal']=='先比较失效策略，尚未实施'
    after=client.get(f'/api/workspaces/{wid}').json()
    for key in ['improvements','contributions','artifacts','jd_versions']:assert before[key]==after[key]
