"""State/API regressions. Model fixtures verify transport only, not model quality."""
import uuid
from sqlalchemy import select
from backend.app.db import Session,MemoryEvent,InteractionState,Artifact
from backend.app import interaction_service as svc
from backend.app.interaction_contract import DiscussionResult,ReviewResult


def base(wid):return '/api/workspaces/'+wid+'/interaction'
def view(c,w):return c.get(base(w)).json()
def post(c,w,path,**kwargs):
    return c.post(base(w)+path,json={'expected_version':view(c,w)['version'],'mutation_id':uuid.uuid4().hex,**kwargs})
def mutate(c,w,*ops):return post(c,w,'/mutations',operations=list(ops))
def op(kind,data=None,target=None):return {'op':kind,'data':data or {},'target_id':target}
def saved(c,w,text='原文'):
    r=post(c,w,'/editor',content=text);assert r.status_code==200,r.text;return r.json()['artifact']


def test_atomic_idempotency_and_stale_version(client,wid):
    body={'expected_version':view(client,wid)['version'],'mutation_id':'repeat','operations':[op('create_metric',{'name':'幻觉率','value':70,'unit':'%','change_type':'relative_decrease'})]}
    r=client.post(base(wid)+'/mutations',json=body);assert r.status_code==200,r.text
    assert client.post(base(wid)+'/mutations',json=body).json()==r.json()
    assert len(view(client,wid)['metrics'])==1
    body['mutation_id']='new';assert client.post(base(wid)+'/mutations',json=body).status_code==409
    before=view(client,wid)
    r=mutate(client,wid,op('create_improvement',{'title':'不会被部分保存'}),op('update_metric',{'value':80},'missing'))
    assert r.status_code==404
    assert view(client,wid)==before


def test_improvements_decision_completion_and_replacement(client,wid):
    for title in ['角色隔离','缓存']:assert mutate(client,wid,op('create_improvement',{'title':title})).status_code==200
    a,b=view(client,wid)['improvements']
    assert mutate(client,wid,op('report_improvement_completed',target=a['id'])).status_code==422
    assert mutate(client,wid,op('update_improvement_decision',{'decision':'selected'},a['id'])).status_code==200
    a=view(client,wid)['improvements'][0];assert a['details']['implementation']=='not_started'
    assert mutate(client,wid,op('update_improvement_decision',{'decision':'deferred'},a['id']),op('update_improvement_decision',{'decision':'selected'},b['id'])).status_code==200
    assert mutate(client,wid,op('report_improvement_completed',target=b['id'])).status_code==200
    state=view(client,wid);assert len(state['improvements'])==2
    assert state['improvements'][0]['details']['decision']=='deferred'
    assert state['improvements'][1]['details']['implementation']=='user_reported_done'
    assert not state['contributions']  # reporting scheme completion never invents personal attribution


def test_metric_correction_history_jd_and_workspace(client,wid):
    artifact=saved(client,wid)
    mutate(client,wid,op('create_metric',{'name':'幻觉率下降','value':70,'unit':'%','change_type':'relative_decrease'}))
    metric=view(client,wid)['metrics'][0]
    mutate(client,wid,op('update_metric',{'value':80},metric['id']))
    state=view(client,wid);assert len(state['metrics'])==1
    assert state['metrics'][0]['version']==2 and state['metrics'][0]['value']==80
    assert state['current_resume']['content']=='原文' and state['current_resume']['review_status']=='needs_review'
    with Session() as s:
        event=s.scalar(select(MemoryEvent).where(MemoryEvent.operation=='update_metric'))
        assert event.before['value']==70 and event.after['value']==80
    before=state
    mutate(client,wid,op('update_jd',{'jd':'新岗位要求','role':'后端工程师'}))
    state=view(client,wid);assert state['metrics']==before['metrics'] and state['findings']==before['findings'] and state['current_resume']['id']==artifact['id']
    other=client.post('/api/workspaces',json={'interest':'隔离项目'}).json()['id']
    assert mutate(client,other,op('update_metric',{'value':1},metric['id'])).status_code==404
    assert post(client,other,'/editor',content='',restore_id=artifact['id']).status_code==404


def test_chat_hypothesis_ambiguity_and_atomic_update(client,wid,monkeypatch):
    mutate(client,wid,op('create_metric',{'name':'指标甲','value':70,'unit':'%'}),op('create_metric',{'name':'指标乙','value':70,'unit':'%'}))
    metrics=view(client,wid)['metrics']
    for intent in ['hypothetical','ambiguous','discussion']:
        monkeypatch.setattr(svc,'ask_json',lambda *a,intent=intent:DiscussionResult(intent=intent,clarification='指的是哪一个指标？' if intent=='ambiguous' else '',operations=[op('update_metric',{'value':80},metrics[0]['id'])]))
        r=post(client,wid,'/chat',content='希望达到80%');assert r.status_code==200,r.text
        assert view(client,wid)['metrics']==metrics
    monkeypatch.setattr(svc,'ask_json',lambda *a:DiscussionResult(intent='explicit_update',operations=[op('update_metric',{'value':80},metrics[0]['id']),op('create_improvement',{'title':'另外加缓存'})]))
    r=post(client,wid,'/chat',content='把甲改为80，另外加缓存');assert r.status_code==200,r.text
    state=view(client,wid);assert len(state['metrics'])==2 and state['metrics'][-1]['value']==80 and len(state['improvements'])==1
    assert state['metrics'][-1]['source_message_id']
    before=state
    monkeypatch.setattr(svc,'ask_json',lambda *a:DiscussionResult(intent='explicit_update',operations=[op('update_jd',{'jd':'不应保存'}),op('update_metric',{'value':9},'foreign')]))
    assert post(client,wid,'/chat',content='非法模型操作').status_code==404
    assert view(client,wid)==before


def test_review_preserves_text_accept_restore_and_sync_is_separate(client,wid,monkeypatch):
    first=saved(client,wid,'快照恢复')
    def review(stage,schema,payload,instruction):
        assert payload['editor_text']=='任务级断点续跑'
        return ReviewResult(suggested_text='任务级断点续跑（证据待补）',issues=[{'category':'fact_metric_attribution','issue':'含义扩大，缺少恢复单个任务状态的证据'}],sync_candidates=[op('create_metric',{'name':'人工待确认','value':80,'unit':'%'})])
    monkeypatch.setattr(svc,'ask_json',review)
    r=post(client,wid,'/review',content='任务级断点续跑');assert r.status_code==200,r.text
    proposal=r.json()['proposal'];assert view(client,wid)['current_resume']['content']=='快照恢复'
    assert not view(client,wid)['metrics']
    r=post(client,wid,'/decision',proposal_id=proposal['id'],accept=True);assert r.status_code==200,r.text
    assert view(client,wid)['current_resume']['content']=='任务级断点续跑（证据待补）'
    assert not view(client,wid)['metrics']
    assert post(client,wid,'/editor',content='',restore_id=first['id']).status_code==200
    assert view(client,wid)['current_resume']['content']=='快照恢复'
    assert len(view(client,wid)['resume_versions'])==3


def test_old_proposal_and_generation_cannot_replace_new_editor(client,wid,monkeypatch):
    saved(client,wid)
    monkeypatch.setattr(svc,'ask_json',lambda *a:ReviewResult(suggested_text='旧建议'))
    proposal=post(client,wid,'/review',content='原文').json()['proposal']
    saved(client,wid,'新人工版本')
    assert post(client,wid,'/decision',proposal_id=proposal['id'],accept=True).status_code==409
    assert view(client,wid)['current_resume']['content']=='新人工版本'
    def generating(s,w,body):
        # Independent transaction emulates another browser editing during model work.
        saved(client,wid,'并发人工编辑')
        return {'id':'not-used','content':'过期生成'}
    monkeypatch.setattr('backend.app.artifact_service.create_artifact',generating)
    r=post(client,wid,'/generate',writing_mode='reference');assert r.status_code==409,r.text
    assert view(client,wid)['current_resume']['content']=='并发人工编辑'


def test_generation_is_proposal_and_personal_requires_contribution(client,wid,monkeypatch):
    calls=[]
    def generate(s,w,b):calls.append(b);return {'id':'fixture','content':'离线模拟项目参考'}
    monkeypatch.setattr('backend.app.artifact_service.create_artifact',generate)
    assert post(client,wid,'/generate',output_mode='personal_resume').status_code==422
    assert not calls
    r=post(client,wid,'/generate',output_mode='project_reference');assert r.status_code==200,r.text
    assert view(client,wid)['current_resume'] is None
    r=post(client,wid,'/decision',proposal_id=r.json()['proposal']['id'],accept=True)
    assert r.status_code==200,r.text
    assert view(client,wid)['current_resume']['content']=='离线模拟项目参考'


def test_contribution_patch_and_source_support_independent(client,wid):
    r=mutate(client,wid,op('update_contribution',{'personal_role':'我负责缓存','action':'增加缓存','state':'implemented'}));assert r.status_code==200,r.text
    c=view(client,wid)['contributions'][0]
    assert mutate(client,wid,op('update_contribution',{'personal_role':'我负责设计'},c['id'])).status_code==200
    newer=view(client,wid)['contributions'][0];assert newer['action']==c['action'] and newer['version']==2
    assert mutate(client,wid,op('update_contribution',{'state':'validated'},c['id'])).status_code==422



def test_migration_preserves_v001_records(tmp_path):
    import os,subprocess,sys
    script='''
from pathlib import Path
from alembic.config import Config
from alembic import command
from backend.app.db import Session,Workspace,Artifact,migrate,InteractionState
cfg=Config('backend/alembic.ini');cfg.set_main_option('script_location','backend/migrations')
command.upgrade(cfg,'001')
with Session.begin() as s:
    w=Workspace(interest='existing project',role='engineer');s.add(w);s.flush();wid=w.id
    s.add(Artifact(workspace_id=wid,type='resume',version=1,content='existing handwritten text',idempotency_key='old'))
migrate()
with Session() as s:
    assert s.get(Workspace,wid).interest=='existing project'
    assert s.query(Artifact).one().content=='existing handwritten text'
    assert s.get(InteractionState,wid) is None
from backend.app.interaction_service import state
with Session() as s:
    assert state(s,wid)['current_resume']['content']=='existing handwritten text'
'''
    env={**os.environ,'REPOCAREER_DATA':str(tmp_path/'migration')}
    result=subprocess.run([sys.executable,'-c',script],env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_review_large_evidence_context_does_not_change_accept_fingerprint(client,wid,monkeypatch):
    client.post('/api/workspaces/'+wid+'/evidence',json={'type':'user_statement','excerpt':'长材料'*1000,'source_ref':'用户说明'})
    saved(client,wid,'原文')
    monkeypatch.setattr(svc,'ask_json',lambda *a:ReviewResult(suggested_text='改写'))
    r=post(client,wid,'/review',content='原文');assert r.status_code==200,r.text
    assert post(client,wid,'/decision',proposal_id=r.json()['proposal']['id'],accept=True).status_code==200


def test_metric_change_kinds_and_optional_fields(client,wid):
    for kind in ['relative_decrease','absolute_decrease','final_value','unspecified']:
        r=mutate(client,wid,op('create_metric',{'name':'测试口径','value':80,'unit':'百分点' if kind=='absolute_decrease' else '%','change_type':kind}))
        assert r.status_code==200,r.text
    assert [m['change_type'] for m in view(client,wid)['metrics']]==['relative_decrease','absolute_decrease','final_value','unspecified']
    assert all(m['baseline'] is None and m['source']=='user_reported' for m in view(client,wid)['metrics'])


def test_editor_review_and_restore_preserve_output_mode(client,wid,monkeypatch):
    original=post(client,wid,'/editor',content='用户待复核个人稿',output_mode='personal_resume').json()['artifact']
    def review(stage,schema,payload,instruction):
        assert payload['output_mode']=='personal_resume'
        return ReviewResult(suggested_text='修改后的个人稿')
    monkeypatch.setattr(svc,'ask_json',review)
    r=post(client,wid,'/review',content='用户待复核个人稿',output_mode='personal_resume')
    assert r.json()['proposal']['output_mode']=='personal_resume'
    assert post(client,wid,'/decision',proposal_id=r.json()['proposal']['id'],accept=True).status_code==200
    # Caller default cannot turn a restored personal draft into a reference draft.
    r=post(client,wid,'/editor',content='',restore_id=original['id'])
    assert r.json()['artifact']['claims'][0]['output_mode']=='personal_resume'


def test_user_metric_reaches_existing_writer_without_measured_promotion():
    from backend.app.resume_quality import metric_records,material_evidence
    material={'reported_metrics':[{'id':'m','name':'错误率','value':80,'unit':'%','change_type':'relative_decrease','contribution_id':'c'}]}
    metric=metric_records(material)['m']
    assert metric.state=='user_reported' and metric.baseline is None and metric.change_type=='relative_decrease'
    assert metric.user_statement_id=='reported-metric:m' and metric.experiment_id is None
    assert material_evidence(material)['reported-metric:m'].kind=='user_statement'


def test_interrupted_generation_key_cannot_replay_old_artifact_after_edit(client,wid,monkeypatch):
    saved(client,wid,'生成前')
    calls=[]
    def generating(s,w,body):
        calls.append(body.idempotency_key)
        saved(client,wid,'生成中改稿')
        return {'id':'old-result','content':'旧输入生成'}
    monkeypatch.setattr('backend.app.artifact_service.create_artifact',generating)
    key='same-generation'
    def request():return client.post(base(wid)+'/generate',json={'expected_version':view(client,wid)['version'],'mutation_id':key,'writing_mode':'reference'})
    assert request().status_code==409
    assert request().status_code==409
    assert len(calls)==1
    assert view(client,wid)['current_resume']['content']=='生成中改稿'
