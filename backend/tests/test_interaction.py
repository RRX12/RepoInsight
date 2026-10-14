"""State/API regressions. Model fixtures verify transport only, not model quality."""
import uuid
import pytest
from sqlalchemy import select
from backend.app.db import Session,MemoryEvent,InteractionState,Artifact
from backend.app import interaction_service as svc


def base(wid):return '/api/workspaces/'+wid+'/interaction'


def view(c,w):return c.get(base(w)).json()


def post(c,w,path,**kwargs):
    return c.post(base(w)+path,json={'expected_version':view(c,w)['version'],'mutation_id':uuid.uuid4().hex,**kwargs})


def mutate(c,w,*ops):return post(c,w,'/mutations',operations=list(ops))


def op(kind,data=None,target=None):return {'op':kind,'data':data or {},'target_id':target}


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
    mutate(client,wid,op('create_metric',{'name':'幻觉率下降','value':70,'unit':'%','change_type':'relative_decrease'}))
    metric=view(client,wid)['metrics'][0]
    mutate(client,wid,op('update_metric',{'value':80},metric['id']))
    state=view(client,wid);assert len(state['metrics'])==1
    assert state['metrics'][0]['version']==2 and state['metrics'][0]['value']==80
    with Session() as s:
        event=s.scalar(select(MemoryEvent).where(MemoryEvent.operation=='update_metric'))
        assert event.before['value']==70 and event.after['value']==80
    before=state
    mutate(client,wid,op('update_jd',{'jd':'新岗位要求','role':'后端工程师'}))
    state=view(client,wid);assert state['metrics']==before['metrics'] and state['findings']==before['findings']
    other=client.post('/api/workspaces',json={'interest':'隔离项目'}).json()['id']
    assert mutate(client,other,op('update_metric',{'value':1},metric['id'])).status_code==404


def test_retired_chat_cannot_mutate_business_state(client,wid,monkeypatch):
    mutate(client,wid,op('create_metric',{'name':'指标甲','value':70,'unit':'%'}))
    before=view(client,wid)
    for content in ('希望达到80%','把甲改为80，另外加缓存','修改JD'):
        assert post(client,wid,'/chat',content=content).status_code==410
        assert view(client,wid)==before


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
    assert 'current_resume' not in state(s,wid)
    assert s.query(Artifact).one().content=='existing handwritten text'
'''
    env={**os.environ,'REPOINSIGHT_DATA':str(tmp_path/'migration')}
    result=subprocess.run([sys.executable,'-c',script],env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_metric_change_kinds_and_optional_fields(client,wid):
    for kind in ['relative_decrease','absolute_decrease','final_value','unspecified']:
        r=mutate(client,wid,op('create_metric',{'name':'测试口径','value':80,'unit':'百分点' if kind=='absolute_decrease' else '%','change_type':kind}))
        assert r.status_code==200,r.text
    assert [m['change_type'] for m in view(client,wid)['metrics']]==['relative_decrease','absolute_decrease','final_value','unspecified']
    assert all(m['baseline'] is None and m['source']=='user_reported' for m in view(client,wid)['metrics'])


def test_direction_edit_delete_history_and_workspace_isolation(client,wid):
    r=mutate(client,wid,op('create_improvement',{'title':'方向','proposal':'明确处理流程'}));assert r.status_code==200
    ident=r.json()['changes'][0]['id']
    assert mutate(client,wid,op('update_improvement_decision',{'decision':'selected'},ident)).status_code==200
    assert mutate(client,wid,op('report_improvement_completed',{},ident)).status_code==200
    r=mutate(client,wid,op('edit_improvement',{'title':'更正方向','proposal':'修订后的设计'},ident));assert r.status_code==200
    item=next(i for i in r.json()['state']['improvements'] if i['id']==ident)
    assert item['details']['implementation']=='not_started'
    other=client.post('/api/workspaces',json={'interest':'other'}).json()['id']
    assert mutate(client,other,op('delete_improvement',{},ident)).status_code==404
    r=mutate(client,wid,op('delete_improvement',{},ident));assert r.status_code==200
    item=next(i for i in r.json()['state']['improvements'] if i['id']==ident)
    assert item['details']['deleted'] and item['status']=='abandoned'
    assert mutate(client,wid,op('update_improvement_decision',{'decision':'selected'},ident)).status_code==409
    with Session() as s:
        events=list(s.scalars(select(MemoryEvent).where(MemoryEvent.entity_id==ident)))
        assert any(e.operation=='edit_improvement' and e.before['details']['title']=='方向' for e in events)
