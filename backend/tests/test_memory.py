from backend.app.db import Session, MemoryEvent, Contribution
from sqlalchemy import select

def contribution(**kwargs):
    return {'personal_role':'独立实现','problem':'非法输入返回不明确','action':'增加输入校验与错误类型','state':'implemented',**kwargs}
def artifact(client,wid):
    return client.post(f'/api/workspaces/{wid}/artifacts',json={'type':'resume','idempotency_key':'a'}).json()
def test_correction_versions_and_stale(client,wid):
    c=client.post(f'/api/workspaces/{wid}/contributions',json=contribution(outcome='实测提升 90%')).json()
    a=artifact(client,wid)
    assert '90%' in a['content'] and '用户补充结果，未独立核验' in a['content']
    patch={**contribution(outcome='只是预估，尚未对照'), 'workspace_id':wid,'expected_version':1}
    assert client.patch('/api/contributions/'+c['id'],json=patch).status_code==200
    assert client.patch('/api/contributions/'+c['id'],json=patch).status_code==409
    assert client.get('/api/artifacts/'+a['id'],params={'workspace_id':wid}).json()['review_status']=='needs_review'
    a2=client.post(f'/api/workspaces/{wid}/artifacts',json={'type':'resume','idempotency_key':'b'}).json()
    assert '实测提升' not in a2['content']
    with Session() as s:
        events=list(s.scalars(select(MemoryEvent).where(MemoryEvent.entity_id==c['id'])))
        assert len(events)==2 and events[1].before['outcome']=='实测提升 90%'
        assert events[1].supersedes_event_id==events[0].id
def test_state_separation(client,wid):
    for state,action in [('proposed','讨论 Redis'),('abandoned','Redis 方案放弃'),('in_progress','尝试缓存'),('implemented','没实现 Redis，只是讨论'),('implemented','补充文件内容校验')]:
        assert client.post(f'/api/workspaces/{wid}/contributions',json=contribution(state=state,action=action)).status_code==200
    a=artifact(client,wid)
    assert any('补充文件内容校验' in c['text'] for c in a['claims'])
    assert all('已实现优化' not in c['text'] for c in a['claims'] if 'Redis' in c['text'])
    assert all('Redis 方案放弃' not in c['text'] for c in a['claims'])
def test_workspace_isolation(client,wid):
    other=client.post('/api/workspaces',json={'interest':'another'}).json()['id']
    ev=client.post(f'/api/workspaces/{wid}/evidence',json={'type':'diff','excerpt':'diff'}).json()
    assert client.post(f'/api/workspaces/{other}/contributions',json=contribution(evidence_ids=[ev['id']])).status_code==404
    c=client.post(f'/api/workspaces/{wid}/contributions',json=contribution()).json()
    assert client.patch('/api/contributions/'+c['id'],json={**contribution(),'workspace_id':other,'expected_version':1}).status_code==404
    assert client.get(f'/api/workspaces/{other}').json()['contributions']==[]
    a=artifact(client,wid)
    assert client.get('/api/artifacts/'+a['id'],params={'workspace_id':other}).status_code==404
def test_jd_changes_selection_not_facts(client,wid):
    c=client.post(f'/api/workspaces/{wid}/contributions',json=contribution()).json()
    a=artifact(client,wid)
    j1=client.post(f'/api/workspaces/{wid}/jd-versions',json={'content':'Python Redis'}).json()
    j2=client.post(f'/api/workspaces/{wid}/jd-versions',json={'content':'Python SQL'}).json()
    assert j2['supersedes_id']==j1['id'] and 'SQL' in j2['diff']['added']
    assert client.get(f'/api/workspaces/{wid}/contributions').json()[0]==c
    assert client.get('/api/artifacts/'+a['id'],params={'workspace_id':wid}).json()['review_status']=='needs_review'
def test_experiment_requires_scope_and_only_claims_limited_result(client,wid):
    report=client.post(f'/api/workspaces/{wid}/evidence',json={'type':'test_report','excerpt':'环境相同，10 个样本，耗时 20 -> 15 ms'}).json()
    assert client.post(f'/api/workspaces/{wid}/contributions',json=contribution(state='validated',evidence_ids=[report['id']])).status_code==422
    c=client.post(f'/api/workspaces/{wid}/contributions',json=contribution(state='validated',evidence_ids=[report['id']],verification={'scope':'10 个样本','source':'用户本地运行','limitations':'单场景'})).json()
    exp={'contribution_id':c['id'],'baseline_snapshot':'before','modified_ref':'after','dataset_description':'10 个样本','conditions':'相同 CPU','metric':'耗时','unit':'ms','baseline_value':20,'modified_value':15,'limitations':'单场景，不代表整体提升','source_evidence_ids':[report['id']]}
    assert client.post(f'/api/workspaces/{wid}/experiments',json=exp).status_code==200
    a=artifact(client,wid); assert '10 个样本' in a['claims'][0]['text'] and '20.0 ms' in a['content'] and '单场景' in a['content']
    # Estimate correction must override an old experiment even with validated enum kept.
    assert client.patch('/api/contributions/'+c['id'],json={**contribution(state='validated',outcome='更正：这是预估，不是实测',evidence_ids=[report['id']],verification={'scope':'10 个样本','source':'用户材料','limitations':'单场景'}),'workspace_id':wid,'expected_version':1}).status_code==200
    estimate=client.post(f'/api/workspaces/{wid}/artifacts',json={'type':'resume','idempotency_key':'estimate'}).json()
    assert '20.0 ms' not in estimate['content']
    # Correction removes result from a new draft even if experiment history remains.
    assert client.patch('/api/contributions/'+c['id'],json={**contribution(state='implemented',outcome='预估'),'workspace_id':wid,'expected_version':2}).status_code==200
    b=client.post(f'/api/workspaces/{wid}/artifacts',json={'type':'resume','idempotency_key':'b'}).json()
    assert '20.0 ms' not in b['content']
def test_idempotent_artifact(client,wid):
    assert artifact(client,wid)['id']==artifact(client,wid)['id']
    assert client.post(f'/api/workspaces/{wid}/artifacts',json={'type':'interview_notes','idempotency_key':'a'}).status_code==409
def test_material_limits_and_no_upstream_claims(client,wid):
    assert client.post(f'/api/workspaces/{wid}/evidence',json={'type':'source_code','excerpt':'spoof'}).status_code==422
    assert client.post(f'/api/workspaces/{wid}/evidence',json={'type':'user_statement','excerpt':'x'*200001}).status_code==422
    c=client.post(f'/api/workspaces/{wid}/contributions',json=contribution()).json()
    a=artifact(client,wid)
    assert a['claims'][0]['contribution_id']==c['id'] and '原项目技术与功能已融入项目描述' in a['content']
def test_action_field_cannot_bypass_result_review(client,wid):
    client.post(f'/api/workspaces/{wid}/contributions',json=contribution(action='增加空内容校验，实测提升 90%，达到生产级高并发'))
    a=artifact(client,wid)
    assert len(a['claims'])==1
    assert '增加空内容校验' in a['claims'][0]['text']
    assert '90%' not in a['claims'][0]['text'] and '生产级' not in a['claims'][0]['text']

def test_project_resume_without_discussion_uses_saved_wiki(client,wid):
    from backend.app.db import Run
    snap=client.post(f'/api/workspaces/{wid}/repository-link',json={'url':'https://github.com/example/ppt-agent'}).json()
    with Session.begin() as s:
        run=Run(workspace_id=wid,status='failed',request={'snapshot_id':snap['id']},result={'wiki':{'generated_pages':{'overview':{'content':'# 项目概览\n\n基于A2A、MCP和ADK的智能PPT项目，串联主题输入、内容规划、资料检索与幻灯片生成，支持流式输出。\n\n通过多Agent分工完成资料检索和内容汇总；工具层通过MCP协议接入，前端以流式事件展示生成进度。'}}}},idempotency_key='wiki')
        s.add(run);s.flush();rid=run.id
    a=artifact(client,wid)
    assert 'A2A' in a['content'] and 'MCP' in a['content'] and '技术架构与设计' in a['content']
    assert a['content'].index('项目简介')<a['content'].index('技术亮点')<a['content'].index('项目成果')
    assert '- **技术架构与设计**' in a['content']
    assert rid in a['dependency_ids'] and snap['id'] in a['dependency_ids']
    assert all(c['kind']=='project_context' for c in a['claims'])
    assert '暂无可写入' not in a['content'] and '架构评审尚未完成' in a['content']

def test_planned_design_and_user_metrics_remain_explicit_after_correction(client,wid):
    c=client.post(f'/api/workspaces/{wid}/contributions',json=contribution(personal_role='',state='proposed',action='设计检查点恢复方案',tradeoffs='复用单Agent，避免新增调度层',outcome='预计耗时减少30%')).json()
    a=artifact(client,wid)
    assert '优化设计（未实现）' in a['content'] and '预期效果，待验证' in a['content'] and '30%' in a['content']
    assert '已实现优化' not in a['content']
    patch={**contribution(state='implemented',action='增加检查点恢复',outcome='耗时减少20%'),'workspace_id':wid,'expected_version':1}
    assert client.patch('/api/contributions/'+c['id'],json=patch).status_code==200
    b=client.post(f'/api/workspaces/{wid}/artifacts',json={'type':'resume','idempotency_key':'new'}).json()
    assert '用户补充结果，未独立核验' in b['content'] and '20%' in b['content'] and '30%' not in b['content']
    assert client.get('/api/artifacts/'+a['id'],params={'workspace_id':wid}).json()['review_status']=='needs_review'
