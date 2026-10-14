import json
import pytest

GOOD='**项目简介：** 基于FastAPI构建文档筛选系统。\n\n## 技术亮点\n- **分层筛选**：按条件筛选，减少重复阅读。\n- **证据关联**：保留来源以核对结论。\n\n**项目成果：** 完成筛选与证据关联。'
MATERIAL={'role':'后端','jd':'Celery RabbitMQ','overview':{'summary':'FastAPI文档筛选系统'},'user_optimizations':[]}
SELECTED={'selected':[{'title':t,'jd_relation':'后端筛选能力','hr_value':'与岗位相关','interview_focus':'筛选条件与证据追问','reason':'有材料支持','source_refs':['overview'],'state':'project_existing'} for t in ('分层筛选','证据关联')],'omitted':['Celery和RabbitMQ仅在JD中，无项目材料']}





def test_native_model_has_separate_roles_and_json_review(monkeypatch):
    import httpx
    from backend.app.resume_support import WritingModel
    monkeypatch.setenv('RESUME_MODEL_API_KEY','test-key')
    monkeypatch.setenv('RESUME_MODEL_BASE_URL','https://model.test')
    calls=[]
    def handle(request):
        payload=json.loads(request.content);calls.append(payload)
        return httpx.Response(200,json={'choices':[{'message':{'content':GOOD}}]})
    model=WritingModel(transport=httpx.MockTransport(handle))
    try:
        model('WRITE\nmaterial');model('REVIEW\nmaterial')
        assert calls[0]['messages'][0]['role']=='system'
        assert 'response_format' not in calls[0]
        assert calls[1]['response_format']=={'type':'json_object'}
        assert calls[0]['thinking']=={'type':'disabled'}
    finally:model.close()

@pytest.mark.parametrize('change',['jd','contribution'])
def test_material_changed_during_writing_rejected(client,wid,monkeypatch,change):
    from backend.app.db import Session,Run,JD,Contribution
    from sqlalchemy import update
    from backend.app.resume_writer import collect
    snap=client.post(f'/api/workspaces/{wid}/repository-link',json={'url':'https://github.com/example/agent'}).json()
    with Session.begin() as s:
        s.add(Run(workspace_id=wid,status='completed',request={'snapshot_id':snap['id']},result={'wiki':{'generated_pages':{'p':{'content':'实际项目资料'}}}},idempotency_key='source'))
        c=Contribution(workspace_id=wid,personal_role='设计',action='恢复方案',state='proposed');s.add(c);s.flush();cid=c.id
    def writer(*args):
        with Session.begin() as s:
            if change=='jd':s.add(JD(workspace_id=wid,raw_text='最新JD',requirements=['最新']))
            else:s.execute(update(Contribution).where(Contribution.id==cid).values(state='implemented',version=2))
        return GOOD,{'status':'passed'}
    monkeypatch.setattr('backend.app.resume_writer.write',writer)
    result=client.post(f'/api/workspaces/{wid}/artifacts',json={'type':'resume','writing_mode':'model','idempotency_key':'model'})
    assert result.status_code==409
    assert client.get(f'/api/workspaces/{wid}').json()['artifacts']==[]

def test_model_audit_saved_and_idempotent(client,wid,monkeypatch):
    from backend.app.db import Session,Run
    snap=client.post(f'/api/workspaces/{wid}/repository-link',json={'url':'https://github.com/example/agent'}).json()
    with Session.begin() as s:s.add(Run(workspace_id=wid,status='completed',request={'snapshot_id':snap['id']},result={'wiki':{'generated_pages':{'p':{'content':'实际项目资料'}}}},idempotency_key='source'))
    calls=[]
    def writer(*args):calls.append(1);return GOOD,{'kind':'writing_review','status':'needs_review','iterations':2}
    monkeypatch.setattr('backend.app.resume_writer.write',writer)
    body={'type':'resume','writing_mode':'model','idempotency_key':'model'}
    first=client.post(f'/api/workspaces/{wid}/artifacts',json=body).json()
    second=client.post(f'/api/workspaces/{wid}/artifacts',json=body).json()
    assert first['id']==second['id'] and first['review_status']=='needs_review' and len(calls)==1
    assert client.post(f'/api/workspaces/{wid}/artifacts',json={**body,'writing_mode':'reference'}).status_code==409

def test_model_errors_do_not_create_reference_artifact(client,wid,monkeypatch):
    from backend.app.db import Session,Run
    from backend.app.providers import ProviderError
    snap=client.post(f'/api/workspaces/{wid}/repository-link',json={'url':'https://github.com/example/agent'}).json()
    with Session.begin() as s:s.add(Run(workspace_id=wid,status='completed',request={'snapshot_id':snap['id']},result={'wiki':{'generated_pages':{'p':{'content':'实际项目资料'}}}},idempotency_key='source'))
    def fail(*args):raise ProviderError('模型连接失败','resume_model_error')
    monkeypatch.setattr('backend.app.resume_writer.write',fail)
    result=client.post(f'/api/workspaces/{wid}/artifacts',json={'type':'resume','writing_mode':'model','idempotency_key':'failure'})
    assert result.status_code>=400
    assert client.get(f'/api/workspaces/{wid}').json()['artifacts']==[]




















@pytest.mark.parametrize('ref',['invented','optimization:plan'])
def test_panorama_chain_rejects_invalid_or_personal_plan_sources(ref):
    from backend.app.resume_support import ProjectValue,validate_product
    product=ProjectValue.model_validate({'architecture':[{'name':'多Agent','steps':['调度','提交'],'source_refs':[ref]}]})
    with pytest.raises(ValueError):validate_product(product,{'overview':'project_existing','optimization:plan':'proposed'})
