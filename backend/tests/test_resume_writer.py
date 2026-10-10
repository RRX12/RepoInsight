import json
import pytest
from backend.app.resume_writer import write,checks

GOOD='**项目简介：** 基于FastAPI构建文档筛选系统。\n\n## 技术亮点\n- **分层筛选**：按条件筛选，减少重复阅读。\n- **证据关联**：保留来源以核对结论。\n\n**项目成果：** 完成筛选与证据关联。'
MATERIAL={'role':'后端','jd':'Celery RabbitMQ','overview':{'summary':'FastAPI文档筛选系统'},'user_optimizations':[]}
SELECTED={'selected':[{'title':t,'jd_relation':'后端筛选能力','hr_value':'与岗位相关','interview_focus':'筛选条件与证据追问','reason':'有材料支持','source_refs':['overview'],'state':'project_existing'} for t in ('分层筛选','证据关联')],'omitted':['Celery和RabbitMQ仅在JD中，无项目材料']}

def test_skill_is_passed_and_loop_repairs_unsupported_metrics():
    calls=[]
    replies=iter([json.dumps(SELECTED),GOOD+'提升90%。',json.dumps({'approved':True,'issues':[]}),json.dumps({'approved':True,'issues':[]}),GOOD,json.dumps({'approved':True,'issues':[]}),json.dumps({'approved':True,'issues':[]})])
    def chat(prompt):calls.append(prompt);return next(replies)
    draft,audit=write(None,MATERIAL,chat)
    assert draft==GOOD and audit['iterations']==2 and audit['status']=='passed'
    assert '没有该指标' in str(audit['reviews'][0])
    assert 'STAR是内在逻辑' in calls[1] and '模型执行流程' in calls[1]
    assert 'STAR是内在逻辑' not in calls[2]
    assert '90%' in calls[4] and '必须修复' in calls[4]
    assert calls[0].startswith('SELECT') and [h['title'] for h in audit['selection']['selected']]==[h['title'] for h in SELECTED['selected']]

def test_review_is_bounded_and_invalid_review_is_not_pass():
    calls=[]
    def chat(prompt):calls.append(prompt);return json.dumps(SELECTED) if prompt.startswith('SELECT') else GOOD if prompt.startswith('WRITE') else 'not JSON'
    _,audit=write(None,MATERIAL,chat)
    assert len(calls)==7 and audit['status']=='needs_review'

def test_selection_rejects_fake_refs_and_promoted_plans():
    from backend.app.resume_writer import Selection,validate_selection
    bad=json.loads(json.dumps(SELECTED));bad['selected'][0]['source_refs']=['invented']
    with pytest.raises(ValueError):validate_selection(Selection.model_validate(bad),{'overview':'project_existing'})
    bad['selected'][0]['source_refs']=['optimization:plan'];bad['selected'][0]['state']='implemented'
    with pytest.raises(ValueError):validate_selection(Selection.model_validate(bad),{'overview':'project_existing','optimization:plan':'proposed'})
    bad['selected'][0]['state']='project_existing';bad['selected'][0]['source_refs']=['overview','optimization:plan']
    with pytest.raises(ValueError):validate_selection(Selection.model_validate(bad),{'overview':'project_existing','optimization:plan':'proposed'})

def test_jd_keywords_are_not_project_evidence():
    issues=checks(GOOD+'基于Celery提升2.8倍。',MATERIAL)
    assert any('Celery' in x for x in issues) and any('2.8倍' in x for x in issues)
    assert any('不能断言' in x for x in checks(GOOD+'系统化评测尚未建立。',MATERIAL))

def test_native_model_has_separate_roles_and_json_review(monkeypatch):
    import httpx
    from backend.app.resume_writer import WritingModel
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


def test_targeted_retrieval_reaches_late_wiki_and_is_bounded():
    from backend.app.resume_writer import enrich_material,Selection
    selection=json.loads(json.dumps(SELECTED));selection['selected'][0]['source_refs']=['wiki:0']
    material={**MATERIAL,'wiki_pages':[{'title':'筛选','content':'开头'}], '_full_wiki_pages':[{'title':'筛选','content':'无关开头'*1000+'\n\n分层筛选技术：按条件短路，保留原文证据。'}]}
    enriched=enrich_material(material,Selection.model_validate(selection),budget=200)
    assert '_full_wiki_pages' not in enriched
    assert sum(len(c['content']) for c in enriched['targeted_evidence'])<=200
    assert any('按条件短路' in c['content'] for c in enriched['targeted_evidence'])


def test_topics_can_reorder_or_remove_but_not_invent():
    from backend.app.resume_writer import validate_draft_topics,Selection
    selection=Selection.model_validate(SELECTED)
    assert not validate_draft_topics('- **证据关联**：保留证据',selection)
    assert validate_draft_topics('- **虚构亮点**：内容',selection)


def test_review_separates_questions_from_rewrites():
    feedback={'title':'分层筛选','category':'needs_evidence','perspective':'technical','issue':'未提供测试结果','suggestion':'补充测试范围','question':'使用什么样本验证？'}
    replies=iter([json.dumps(SELECTED),GOOD,json.dumps({'approved':True,'issues':[]}),json.dumps({'approved':True,'issues':[],'feedback':[feedback]})])
    draft,audit=write(None,MATERIAL,lambda _:next(replies))
    assert audit['status']=='passed' and audit['reviews'][0]['feedback'][0]['question']
    assert '使用什么样本' not in draft


def test_content_rewrite_feedback_triggers_bounded_revision():
    feedback={'title':'分层筛选','category':'rewrite','perspective':'technical','issue':'只列框架','suggestion':'说明筛选机制'}
    replies=iter([json.dumps(SELECTED),GOOD,json.dumps({'approved':True,'issues':[],'feedback':[]}),json.dumps({'approved':True,'issues':[],'feedback':[feedback]}),GOOD,json.dumps({'approved':True,'issues':[],'feedback':[]}),json.dumps({'approved':True,'issues':[],'feedback':[]})])
    prompts=[]
    def chat(p):prompts.append(p);return next(replies)
    _,audit=write(None,MATERIAL,chat)
    assert audit['iterations']==2 and '说明筛选机制' in prompts[4]
    assert audit['reviews'][1]['feedback']==[]


def test_independent_review_does_not_receive_other_opinion():
    prompts=[]
    def chat(p):
        prompts.append(p)
        if p.startswith('JD_PLAN'):return json.dumps({'questions':[{'requirement':'多轮对话','question':'历史状态如何进入下一轮？','search_terms':['FastAPI']}]})
        if p.startswith('SELECT'):return json.dumps(SELECTED)
        if p.startswith('WRITE'):return GOOD
        if p.startswith('REVIEW_HR'):return json.dumps({'approved':True,'issues':[],'feedback':[{'title':'分层筛选','category':'future_work','perspective':'hr','issue':'HR_ONLY_MARKER','suggestion':'后续补充业务案例'}]})
        return json.dumps({'approved':True,'issues':[],'feedback':[]})
    _,audit=write(None,MATERIAL,chat)
    technical=next(p for p in prompts if p.startswith('REVIEW_TECHNICAL'))
    assert 'HR_ONLY_MARKER' not in technical
    assert len(audit['reviews'][0]['perspectives'])==2


def test_value_claim_rejects_unconfirmed_as_existing():
    from backend.app.resume_writer import Selection,validate_selection
    data=json.loads(json.dumps(SELECTED))
    data['project_value']={'claims':[{'statement':'用户已完成重构','mechanism_chain':['改造'], 'source_refs':['optimization:p'],'evidence_level':'wiki_analysis'}]}
    with pytest.raises(ValueError):validate_selection(Selection.model_validate(data),{'overview':'project_existing','optimization:p':'proposed'})


def test_product_analysis_is_independent_of_jd_before_selection():
    prompts=[]
    mat={**MATERIAL,'jd':'TARGET_JD_MARKER','wiki_pages':[{'title':'系统','content':'FastAPI筛选系统'}],'_full_wiki_pages':[{'title':'系统','content':'FastAPI筛选系统'}]}
    def chat(p):
        prompts.append(p)
        if p.startswith('JD_PLAN'):return json.dumps({'questions':[{'requirement':'筛选','question':'如何筛选？','search_terms':['FastAPI']}]})
        if p.startswith('ANALYZE'):
            return json.dumps({'facts':[{'capability':'筛选','mechanism':'FastAPI','limitation':'未验证','source_ref':'wiki:0:chunk:0:span:0'}],'uncertainties':[]})
        if p.startswith('PRODUCT'):
            return json.dumps({'audience':'文档处理者','scenario':'筛选','background':'处理文档','value_summary':'建立筛选链路','claims':[{'statement':'提供筛选能力','mechanism_chain':['输入','筛选'],'source_refs':['wiki:0:chunk:0:span:0'],'evidence_level':'wiki_documented'}]})
        if p.startswith('SELECT'):return json.dumps(SELECTED)
        if p.startswith('WRITE'):return GOOD
        return json.dumps({'approved':True,'issues':[]})
    _,audit=write(None,mat,chat)
    assert 'TARGET_JD_MARKER' not in next(p for p in prompts if p.startswith('PRODUCT'))
    assert 'TARGET_JD_MARKER' in next(p for p in prompts if p.startswith('SELECT'))
    assert audit['selection']['project_value']['audience']=='文档处理者'
    assert audit['project_map']['facts'][0]['quote']=='FastAPI筛选系统'
    assert len(audit['harness']['calls'])==7
    assert prompts.index(next(p for p in prompts if p.startswith('JD_PLAN')))<prompts.index(next(p for p in prompts if p.startswith('SELECT')))
    assert 'FastAPI筛选系统' in next(p for p in prompts if p.startswith('SELECT'))
    assert audit['job_evidence'][0]['candidate_evidence'][0]['source_ref']=='wiki:0:chunk:0:span:0'


def test_stable_ids_allow_renaming_but_reject_unknown_or_duplicate():
    from backend.app.resume_writer import Selection,validate_draft_topics
    selection=Selection.model_validate(SELECTED)
    for i,h in enumerate(selection.selected):h.id=f'h{i+1}'
    assert not validate_draft_topics('- **条件级联筛选** <!-- highlight:h1 -->：说明机制',selection)
    assert validate_draft_topics('- **无来源** <!-- highlight:h4 -->：未知',selection)
    assert validate_draft_topics('- **主题A** <!-- highlight:h1 -->：a\n- **主题B** <!-- highlight:h1 -->：b',selection)


def test_evidence_packing_keeps_all_cited_text_and_ids():
    from backend.app.resume_writer import pack_evidence
    packed=pack_evidence([{'content':'完整原文：角色保存经历并读取。','source_ref':'wiki:0'}],[{'id':'wiki:0:chunk:0:span:0','content':'角色保存经历'}])
    assert len(packed)==1
    assert 'wiki:0:chunk:0:span:0' in packed[0]['source_refs']
    assert '角色保存经历' in packed[0]['content']

def test_job_retrieval_is_fair_bounded_and_preserves_tail():
    from backend.app.resume_writer import JobPlan,job_evidence
    plan=JobPlan.model_validate({'questions':[{'requirement':'记忆','question':'如何召回？','search_terms':['memory']},{'requirement':'不存在','question':'如何处理？','search_terms':['unknown-term']}]})
    result=job_evidence({'_full_wiki_pages':[{'content':'无关'*6000+' memory retrieval history','title':'记忆'}]},plan,{},budget=3200)
    assert any('memory retrieval' in e['content'] for e in result[0]['candidate_evidence'])
    assert sum(len(e['content']) for q in result for e in q['candidate_evidence'])<=3200
    assert result[1]['status']=='unconfirmed'

@pytest.mark.parametrize('ref',['invented','optimization:plan'])
def test_panorama_chain_rejects_invalid_or_personal_plan_sources(ref):
    from backend.app.resume_writer import ProjectValue,validate_product
    product=ProjectValue.model_validate({'architecture':[{'name':'多Agent','steps':['调度','提交'],'source_refs':[ref]}]})
    with pytest.raises(ValueError):validate_product(product,{'overview':'project_existing','optimization:plan':'proposed'})

def test_merged_topic_preserves_proposed_state():
    from backend.app.resume_writer import Selection,validate_selection
    data=json.loads(json.dumps(SELECTED));h=data['selected'][0]
    h.update(source_refs=['overview','optimization:plan'],state='proposed')
    h['card']={'mechanism':'原项目已有记忆；计划优化召回，尚未实现'}
    selection=validate_selection(Selection.model_validate(data),{'overview':'project_existing','optimization:plan':'proposed'})
    assert selection.selected[0].state=='proposed'

def test_normalize_heading_does_not_change_claims_or_invent_sections():
    from backend.app.resume_writer import normalize_draft
    missing=GOOD.replace('## 技术亮点\n','')
    repaired=normalize_draft(missing)
    assert '## 技术亮点' in repaired
    assert repaired.replace('## 技术亮点\n\n','')==missing
    assert normalize_draft('无正文材料')=='无正文材料'
