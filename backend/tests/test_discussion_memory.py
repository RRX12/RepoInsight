"""Spec M01-M20: real persistence/context/API, mocked external answering only."""
import asyncio,copy,json,uuid
import pytest
from fastapi import HTTPException
from sqlalchemy import select,text
from backend.app import discussion_memory as mem,discussion_service as svc,wiki_chat
from backend.app.discussion_contract import Question,Plan,MemoryChange,MemoryCandidate
from backend.app.discussion_context import assemble,complete_pairs,history_search,tokens
from backend.app.db import Session,Snapshot,Conversation,Message,MemoryEvent
from backend.tests.test_wiki_chat import material

def opened(wid,surface='wiki'):return mem.open_conversation(wid,surface)['id']
def begin(wid,cid,content='缓存怎么设计？',rid=None):
    return mem.begin(wid,cid,Question(request_id=rid or uuid.uuid4().hex,expected_revision=mem.view(wid,cid)['revision'],content=content))
def done(wid,cid,content='缓存怎么设计？',answer='仅讨论缓存方案，未确认实现',plan=None):
    ticket=begin(wid,cid,content);assert mem.finish(wid,cid,ticket,'completed',answer,plan or Plan(topic_title='缓存',focused_refs=['缓存']));return ticket

def edit(wid,cid,**kw):
    return mem.change_memory(wid,cid,MemoryChange(expected_revision=mem.view(wid,cid)['revision'],request_id=uuid.uuid4().hex,subject_key='deployment',content='只考虑本地',**kw))

def test_M01_refresh_and_surface_separation(client,wid):
    cid=opened(wid);done(wid,cid)
    assert opened(wid)==cid
    data=client.get(f'/api/workspaces/{wid}/conversations/{cid}').json()
    assert data['message_count']==2 and data['data']['focused_refs']==['缓存']
    other=opened(wid,'discussion');assert mem.view(wid,other)['messages']==[]
    assert client.get(f'/api/workspaces/{wid}/conversations/{cid}?offset=1&limit=1').json()['messages'][0]['role']=='assistant'

def test_M02_M03_recent_limit_constraint_and_budget(client,wid,monkeypatch):
    cid=opened(wid);done(wid,cid,'约束：仅本地部署')
    for i in range(12):done(wid,cid,f'轮次{i}','说明')
    done(wid,cid,'长代码','x'*10000)
    ticket=begin(wid,cid,'继续');payload,log=assemble(wid,cid,ticket,Plan())
    assert len(payload['recent'])<=10 and all(len(p)==2 for p in payload['recent'])
    assert any(m['content']=='仅本地部署' for m in payload['memory'])
    assert tokens(payload)<=log['input_limit']
    mem.finish(wid,cid,ticket,'failed')
    ticket=begin(wid,cid,'x'*18000)
    with pytest.raises(HTTPException,match='超预算'):assemble(wid,cid,ticket,Plan())

def test_M04_M05_pronoun_topic_switch(client,wid):
    cid=opened(wid);done(wid,cid)
    ticket=begin(wid,cid,'那失败以后呢');p=asyncio.run(svc.plan_turn(wid,cid,ticket))
    assert '缓存' in p.standalone_query and '不预设已实现' in p.standalone_query
    mem.finish(wid,cid,ticket,'completed','尚需核查',p)
    ticket=begin(wid,cid,'讨论恢复');p=asyncio.run(svc.plan_turn(wid,cid,ticket));assert p.topic_relation=='switch'
    mem.finish(wid,cid,ticket,'completed','讨论恢复',p)
    ticket=begin(wid,cid,'这个如何处理');p=asyncio.run(svc.plan_turn(wid,cid,ticket));assert p.focused_refs==['恢复']

def test_M06_M18_M20_chinese_history_old_topic_and_missing(client,wid):
    cid=opened(wid);old=done(wid,cid,'缓存方案为什么不用Redis','部署约束下优先本地，淘汰策略仍未解决')
    for i in range(12):done(wid,cid,f'恢复方案第{i}步','讨论恢复',Plan(topic_title='恢复',focused_refs=['恢复']))
    ticket=begin(wid,cid,'回到缓存方案');p=asyncio.run(svc.plan_turn(wid,cid,ticket));payload,log=assemble(wid,cid,ticket,p)
    assert old['user']['id'] in log['history_message_ids'] and '部署约束' in str(payload['history'])
    assert log['retrieval_mode'] in ('fts5_trigram+keyword','keyword_fallback')
    payload,_=assemble(wid,cid,ticket,Plan(history_needed=True,history_query='绝不存在的主题'))
    assert '没有找到' in payload['history_notice']
    with Session() as s:
        c=mem.get(s,wid,cid);rows=mem.messages(s,cid,wid)
        hits,mode=history_search(s,c,rows,'缓存方案');assert old['user']['id'] in [m.id for p in hits for m in p]

def test_M07_repeat_three_times_and_M09_scopes(client,wid):
    cid=opened(wid)
    for _ in range(3):done(wid,cid,'约束：仅本地部署')
    items=mem.view(wid,cid)['memories'];assert len(items)==1 and len(items[0]['source_message_ids'])==3
    done(wid,cid,'项目约束：仅本地部署');assert len(mem.view(wid,cid)['memories'])==2
    other=opened(wid,'discussion');assert len(mem.view(wid,other)['memories'])==1

def test_M08_correction_excludes_old_turn_and_retract(client,wid):
    cid=opened(wid);old=done(wid,cid,'约束：只用云端')
    m=mem.view(wid,cid)['memories'][0]
    body=MemoryChange(expected_revision=mem.view(wid,cid)['revision'],request_id='correct',subject_key=m['subject_key'],content='只用本地',target_id=m['id'],action='SUPERSEDE')
    mem.change_memory(wid,cid,body);ticket=begin(wid,cid,'回到部署约束')
    payload,log=assemble(wid,cid,ticket,Plan(history_needed=True,history_query='云端'))
    assert '只用云端' not in str(payload) and old['user']['id'] not in log['recent_message_ids']
    current=next(m for m in mem.view(wid,cid)['memories'] if m['status']=='active')
    mem.change_memory(wid,cid,body.model_copy(update={'request_id':'retract','expected_revision':mem.view(wid,cid)['revision'],'target_id':current['id'],'content':current['content'],'action':'RETRACT'}))
    assert not [m for m in mem.view(wid,cid)['memories'] if m['status']=='active']

def test_M10_proposal_is_not_implementation(client,wid):
    cid=opened(wid);done(wid,cid,'讨论笔记：计划新增缓存')
    ticket=begin(wid,cid,'缓存现在实现了吗');p=asyncio.run(svc.plan_turn(wid,cid,ticket));payload,_=assemble(wid,cid,ticket,p)
    assert p.source_lookup_needed and payload['memory'][0]['kind']=='proposal_note'
    assert '不是源码事实' in payload['rules'] and '不预设已实现' in p.standalone_query

def test_M11_source_revision_invalidation(client,wid):
    material(wid);cid=opened(wid);ticket=begin(wid,cid)
    ev={'e':dict(id='e',kind='code',commit_sha='a'*40,path='cache.py',start_line=1,end_line=2,excerpt='def read(): pass')}
    assert mem.finish(wid,cid,ticket,'completed','已读局部代码',Plan(topic_title='缓存',focused_refs=['缓存']),{},ev)
    assert mem.view(wid,cid)['memories'][0]['status']=='active'
    with Session.begin() as s:s.add(Snapshot(workspace_id=wid,owner='example',repo='repo',commit_sha='b'*40,metadata_json={}))
    assert mem.view(wid,cid)['memories'][0]['status']=='needs_recheck'
    ticket=begin(wid,cid);payload,_=assemble(wid,cid,ticket,Plan());assert not payload['memory']

def test_M12_cross_workspace(client,wid):
    cid=opened(wid);done(wid,cid,'项目约束：秘密')
    other=client.post('/api/workspaces',json={'interest':'other'}).json()['id']
    assert client.get(f'/api/workspaces/{other}/conversations/{cid}').status_code==404
    assert client.delete(f'/api/workspaces/{other}/conversations/{cid}').status_code==404
    assert mem.view(other,opened(other))['memories']==[]

def test_M13_idempotency_and_M14_concurrent_correction(client,wid):
    cid=opened(wid);ticket=begin(wid,cid,rid='same')
    assert begin(wid,cid,rid='same')['replay']
    with pytest.raises(HTTPException):begin(wid,cid,'different',rid='same')
    with pytest.raises(HTTPException):begin(wid,cid,rid='another')
    edit(wid,cid)
    assert not mem.finish(wid,cid,ticket,'completed','旧回答')
    assert all(m['role']!='assistant' for m in mem.view(wid,cid)['messages'])
    assert mem.view(wid,cid)['messages'][0]['proposal']['discussion']['status']=='cancelled'

def test_M15_delete_late_result_fts_audit_cache(client,wid):
    cid=opened(wid);done(wid,cid,'约束：删除敏感记录');ticket=begin(wid,cid)
    mem.delete_conversation(wid,cid);assert not mem.finish(wid,cid,ticket,'completed','晚到结果')
    with Session() as s:
        assert not mem.messages(s,cid,wid)
        assert not s.scalars(select(MemoryEvent).where(MemoryEvent.entity_id==cid)).all()
        assert s.get(Conversation,cid).data=={}
        if mem.fts_available(s):assert s.execute(text('SELECT count(*) FROM discussion_fts WHERE conversation_id=:c'),{'c':cid}).scalar()==0
    assert mem.view(wid,opened(wid))['memories']==[]

def test_M16_invalid_memory_source_transaction(client,wid):
    cid=opened(wid);ticket=begin(wid,cid)
    p=Plan(memory_candidates=[MemoryCandidate(kind='proposal_note',subject_key='cache',content='不要虚构',origin='assistant_proposal',source_message_ids=['foreign'])])
    with pytest.raises(HTTPException):mem.finish(wid,cid,ticket,'completed','不要虚构',p)
    assert mem.view(wid,cid)['memories']==[] and mem.view(wid,cid)['message_count']==1

def test_M17_production_route_no_business_mutation(client,wid,monkeypatch):
    monkeypatch.setattr(svc,'plan_turn',lambda *a: (_ for _ in ()).throw(AssertionError('no model')))
    cid=opened(wid);before=client.get('/api/workspaces/'+wid).json()
    r=client.post(f'/api/workspaces/{wid}/conversations/{cid}/turns',json={'request_id':'one','expected_revision':0,'content':'请生成简历并修改JD'})
    assert r.status_code==200 and '独立按钮' in r.text and '"done": true' in r.text
    after=client.get('/api/workspaces/'+wid).json()
    for k in before:
        if k not in ('messages','events'):assert before[k]==after[k]

def test_M19_failure_cancel_and_restart(client,wid):
    cid=opened(wid);ticket=begin(wid,cid,'约束：保留失败时的约束')
    mem.finish(wid,cid,ticket,'failed');assert mem.view(wid,cid)['memories']
    ticket=begin(wid,cid);mem.cancel(wid,cid,ticket['user']['proposal']['discussion']['request_id'])
    assert not mem.finish(wid,cid,ticket,'completed','未完成流')
    ticket=begin(wid,cid);mem.recover()
    with Session() as s:assert complete_pairs(mem.messages(s,cid,wid))==[]
    assert mem.view(wid,cid)['messages'][-1]['proposal']['discussion']['status']=='failed'

def test_production_stream_context_and_failure(client,wid,monkeypatch):
    run=material(wid);cid=opened(wid);monkeypatch.setenv('DEEPWIKI_BASE_URL','http://test');seen=[]
    async def stream(base,payload):
        seen.append(payload);yield wiki_chat.event(delta='有依据的回答');yield wiki_chat.event(done=True)
    monkeypatch.setattr(wiki_chat,'stream',stream)
    body=dict(request_id='stream',expected_revision=0,content='缓存方案？',run_id=run,page_id='p')
    r=client.post(f'/api/workspaces/{wid}/conversations/{cid}/turns',json=body)
    assert '"done": true' in r.text,r.text
    assert '版本检查' in seen[0]['messages'][0]['content']
    view=mem.view(wid,cid);assert view['message_count']==2
    log=view['messages'][-1]['proposal']['discussion']['load_log'];assert log['token_estimate']<=log['input_limit'] and log['usage'] is None
    r=client.post(f'/api/workspaces/{wid}/conversations/{cid}/turns',json=body);assert '"reused": true' in r.text and len(seen)==1
    async def fail(*a):yield wiki_chat.event(delta='部分');yield wiki_chat.event(error='失败')
    monkeypatch.setattr(wiki_chat,'stream',fail)
    r=client.post(f'/api/workspaces/{wid}/conversations/{cid}/turns',json={**body,'request_id':'failure','expected_revision':view['revision']})
    assert '失败' in r.text and mem.view(wid,cid)['message_count']==3
    assert mem.view(wid,cid)['messages'][-1]['proposal']['discussion']['status']=='failed'

def test_explicit_plan_committed_before_failure_and_conflict(client,wid):
    cid=opened(wid);ticket=begin(wid,cid,'记住：只用本地')
    plan=Plan(memory_candidates=[MemoryCandidate(kind='constraint',subject_key='deployment',content='只用本地',origin='user_explicit',source_message_ids=[ticket['user']['id']])])
    mem.commit_explicit(wid,cid,ticket,plan);assert not plan.memory_candidates
    mem.finish(wid,cid,ticket,'failed');assert mem.view(wid,cid)['memories'][0]['content']=='只用本地'
    edit(wid,cid);assert any(m['status']=='needs_recheck' for m in mem.view(wid,cid)['memories'])

def test_FTS_fallback_same_chinese_match(client,wid,monkeypatch):
    cid=opened(wid);done(wid,cid,'缓存方案','中文上下文')
    monkeypatch.setattr(mem,'fts_available',lambda s:False)
    with Session() as s:
        hits,mode=history_search(s,mem.get(s,wid,cid),mem.messages(s,cid,wid),'缓存')
        assert mode=='keyword_fallback' and len(hits)==1

def test_migration_preserves_legacy_messages(tmp_path):
    import subprocess,sys,os
    script=r'''
from pathlib import Path
from alembic import command
from alembic.config import Config
from backend.app.db import engine
from sqlalchemy import text
cfg=Config('backend/alembic.ini');cfg.set_main_option('script_location','backend/migrations')
command.upgrade(cfg,'002')
with engine.begin() as db:
 db.execute(text("INSERT INTO workspaces(id,created_at,interest,role,skills,time_budget,environment,stage) VALUES('w','2026','legacy','role','','','','understanding')"))
 db.execute(text("INSERT INTO messages(id,created_at,workspace_id,role,content,proposal) VALUES('m','2026','w','user','old text','{}')"))
command.upgrade(cfg,'head')
with engine.connect() as db:
 row=db.execute(text('SELECT content,proposal FROM messages')).first()
 assert row[0]=='old text' and 'legacy' in row[1]
 assert db.execute(text('SELECT surface FROM conversations')).scalar()=='legacy'
command.upgrade(cfg,'head')
with engine.connect() as db:assert db.execute(text('SELECT count(*) FROM conversations')).scalar()==1
'''
    result=subprocess.run([sys.executable,'-c',script],env={**os.environ,'REPOCAREER_DATA':str(tmp_path),'REPOCAREER_DEMO':'true'},capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_stop_from_other_client_closes_waiting_stream(client,wid,monkeypatch):
    cid=opened(wid);ticket=begin(wid,cid);closed=[]
    async def slow(*args):
        try:
            await asyncio.sleep(5);yield wiki_chat.event(done=True)
        finally:closed.append(True)
    monkeypatch.setattr(wiki_chat,'stream',slow)
    async def run():
        async def consume():return [x async for x in svc.guarded_stream(wid,cid,ticket,'unused',{})]
        task=asyncio.create_task(consume());await asyncio.sleep(.03)
        mem.cancel(wid,cid,ticket['user']['proposal']['discussion']['request_id'])
        with pytest.raises(HTTPException):await asyncio.wait_for(task,2)
    asyncio.run(run());assert closed==[True]


def test_old_checkpoints_removed_and_other_workspace_retained(client,wid):
    import sqlite3
    from backend.app.db import DATA
    cid=opened(wid);ticket=done(wid,cid)
    path=DATA/'agent-checkpoints.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS checkpoints(thread_id TEXT, content TEXT)')
        db.executemany('INSERT INTO checkpoints VALUES (?,?)',[(wid+':'+ticket['user']['id'],'private'),('other:message','keep')])
    mem.delete_conversation(wid,cid)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT content FROM checkpoints WHERE thread_id=?',(wid+':'+ticket['user']['id'],)).fetchall()==[]
        assert db.execute("SELECT content FROM checkpoints WHERE thread_id='other:message'").fetchone()[0]=='keep'

def test_workspace_constraint_change_cancels_other_session_answer(client,wid):
    owner=opened(wid);done(wid,owner,'项目约束：只考虑本地')
    cid=opened(wid,'discussion');ticket=begin(wid,cid)
    m=mem.view(wid,owner)['memories'][0]
    mem.change_memory(wid,owner,MemoryChange(expected_revision=mem.view(wid,owner)['revision'],request_id='new',subject_key=m['subject_key'],scope='workspace',target_id=m['id'],action='SUPERSEDE',content='允许云端'))
    assert not mem.active(wid,cid,ticket)
    assert not mem.finish(wid,cid,ticket,'completed','只用旧约束回答')


def test_source_observation_requires_code_provenance(client,wid):
    cid=opened(wid);ticket=begin(wid,cid,'用户声称测试通过')
    p=Plan(memory_candidates=[MemoryCandidate(kind='code_observation',subject_key='test',content='测试通过',origin='user_explicit',source_message_ids=[ticket['user']['id']])])
    with pytest.raises(HTTPException):mem.commit_explicit(wid,cid,ticket,p)
    assert not mem.view(wid,cid)['memories']


def test_actual_model_envelope_budget_and_output_reserve(monkeypatch):
    import httpx
    from backend.app.resume_support import WritingModel
    from backend.app.providers import ProviderError
    monkeypatch.setenv('RESUME_MODEL_API_KEY','offline-only')
    seen=[]
    def reply(req):
        seen.append(json.loads(req.content));return httpx.Response(200,json={'choices':[{'message':{'content':'{}'}}]})
    model=WritingModel(httpx.MockTransport(reply))
    try:
        with pytest.raises(ProviderError,match='预算'):model.request('x'*300,stage='DISCUSSION_PLAN',input_budget=200,output_budget=2000,system_instruction='只讨论')
        assert seen==[]
        model.request('x',stage='DISCUSSION_PLAN',input_budget=1000,output_budget=2000,system_instruction='只讨论')
        assert seen[0]['max_tokens']==2000 and seen[0]['messages'][0]['content']=='只讨论'
    finally:model.close()

def test_delete_shared_memory_redacts_dependent_answer_but_keeps_independent_input(client,wid):
    owner=opened(wid);done(wid,owner,'项目约束：不能公开的部署限制')
    shared=mem.view(wid,owner)['memories'][0]
    other=opened(wid,'discussion');ticket=begin(wid,other,'如何选择部署方式')
    mem.finish(wid,other,ticket,'completed','根据不能公开的部署限制，选择本地',Plan(),{'memory_ids':[shared['id']]})
    mem.delete_conversation(wid,owner)
    restored=mem.view(wid,other)
    assert '不能公开' not in str(restored) and restored['messages'][0]['content']=='如何选择部署方式'
    with Session() as s:assert not complete_pairs(mem.messages(s,other,wid))
