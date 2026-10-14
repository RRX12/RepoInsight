"""Actual writer/optimization entry regressions with only external I/O faked."""
import json
from types import SimpleNamespace
import pytest
from backend.app.resume_writer import write
from backend.app.optimization_review import generate as optimize
from backend.app.providers import ProviderError
from backend.tests.test_resume_quality import MATERIAL,Stub,SHA,claim,candidate
from backend.tests.source_fixture import Reader,Retriever


def report():
    return {'overview':{'summary':'角色记忆','current_architecture':'版本化更新','modules':[{'name':'记忆','responsibility':'维护版本','paths':['memory.ts']}],'core_flows':[{'name':'更新','description':'拒绝过期','paths':['memory.ts']}],'coverage_notes':['静态证据']},'directions':[],'no_change_reason':'现有版本校验满足需求','jd_assessment':[]}

def test_shared_pack_reused_across_branches_without_wiki():
    model=Stub();material={k:v for k,v in MATERIAL.items() if 'wiki' not in k}
    _,a=write(None,material,model)
    calls=[]
    def planner(p):
        stage=p.split('\n',1)[0];calls.append(stage)
        if stage=='OPTIMIZATION_PLAN':return json.dumps(report())
        if stage=='OPTIMIZATION_CHECK':return json.dumps({'approved':True,'issues':[]})
        raise AssertionError('shared stages should not be rerun: '+stage)
    result,coverage=optimize(SimpleNamespace(id='s',commit_sha=SHA),material,lambda *a:None,lambda:None,planner,Reader(),Retriever())
    assert calls==['OPTIMIZATION_PLAN','OPTIMIZATION_CHECK']
    assert a['analysis_pack_id']==coverage['analysis_pack_id'] and not result['directions']
    assert not any(s in ('MAPPING','ANALYZE','PRODUCT','DISCOVER') for s,_ in model.calls)
    assert '多轮记忆' in next(p for s,p in model.calls if s=='WRITE')

@pytest.mark.parametrize('change',['jd','workspace_id','commit','project_corrections'])
def test_shared_pack_invalidates_relevant_identity(change):
    _,a=write(None,MATERIAL,Stub())
    changed={**MATERIAL,change:{'jd':'异常恢复','workspace_id':'other','commit':'b'*40,'project_corrections':[{'excerpt':'已有恢复'}]}[change]}
    model=Stub();_,b=write(None,changed,model)
    assert a['analysis_pack_id']!=b['analysis_pack_id']
    assert any(s=='JD_PLAN' for s,_ in model.calls)

def test_personal_edits_do_not_invalidate_project_investigation():
    _,a=write(None,MATERIAL,Stub())
    model=Stub();_,b=write(None,{**MATERIAL,'previous_resume':'编辑文本','reported_metrics':[],'improvement_states':[{'id':'x','details':{'implementation':'not_started','proposal':'计划'}}]},model)
    assert a['analysis_pack_id']==b['analysis_pack_id']
    assert not any(s in ('PROJECT_CONTEXT','JD_PLAN','INVESTIGATE','CLAIM_VERIFY') for s,_ in model.calls)

def test_failed_downstream_preserves_verified_pack():
    stub=Stub()
    def broken(p):
        if p.startswith('WRITE'):raise ProviderError('offline failure','resume_model_error')
        return stub(p)
    with pytest.raises(ProviderError):write(None,MATERIAL,broken)
    model=Stub();write(None,MATERIAL,model)
    assert not any(s=='INVESTIGATE' for s,_ in model.calls)

def test_cache_hit_observes_cancellation():
    write(None,MATERIAL,Stub());model=Stub()
    def cancel():raise ProviderError('已取消','cancelled')
    with pytest.raises(ProviderError) as e:write(None,{**MATERIAL,'_check_active':cancel},model)
    assert e.value.code=='cancelled' and not model.calls

def test_fixed_source_read_budget_and_supplement_once(monkeypatch):
    monkeypatch.setenv('RESUME_SOURCE_FILES','2');reader=Reader();stub=Stub()
    def model(p):
        d=json.loads(stub(p))
        if p.startswith('INVESTIGATE\n'):d['next_reads']=[{'path':'caller.ts','terms':['guard'],'reason':'调用方未读'}]
        if p.startswith('SYNTHESIZE\n'):d['next_reads']=[{'path':'caller.ts','terms':['other'],'reason':'不能再次请求'}];d['unresolved_questions']=['调用链未证实']
        return json.dumps(d)
    _,a=write(None,MATERIAL,model,reader)
    assert len({p for p,_ in reader.reads})==2
    assert sum(s=='SYNTHESIZE' for s,_ in stub.calls)==1
    assert a['analysis_gaps'] and a['status']=='needs_review'

def test_source_failure_records_gap_without_promoting_wiki():
    class Broken(Reader):
        def read_source(self,repo,sha,path,line_range=None):
            if path=='memory.ts':raise ProviderError('rate limit','rate_limited')
            return super().read_source(repo,sha,path,line_range)
    stub=Stub()
    def model(p):
        d=json.loads(stub(p))
        if p.startswith(('INVESTIGATE','CLAIM_VERIFY')):
            for c in d['claims']:c['evidence_ids']=['source:readme']
        return json.dumps(d)
    _,a=write(None,MATERIAL,model,Broken())
    assert any('rate_limited' in g for g in a['analysis_gaps']) and a['status']=='needs_review'
    assert all(e['kind']!='wiki' for e in a['source_evidence'])

def test_no_wiki_api_has_optional_run_dependency(client,wid,monkeypatch):
    client.post(f'/api/workspaces/{wid}/repository-link',json={'url':'https://github.com/example/demo'})
    monkeypatch.setattr('backend.app.resume_support.WritingModel',Stub)
    response=client.post(f'/api/workspaces/{wid}/artifacts',json={'type':'resume','writing_mode':'model','target_role':'AI','target_jd':'多轮记忆','idempotency_key':'no-wiki'})
    assert response.status_code==200,response.text
    assert None not in response.json()['dependency_ids']

def test_optimizer_path_repair_is_bounded_and_never_accepts_unknown():
    stub=Stub();calls=[]
    def planner(p):
        stage=p.split('\n',1)[0];calls.append(stage)
        if stage.startswith('OPTIMIZATION_'):
            d=report();d['overview']['modules'][0]['paths']=['invented.py'];return json.dumps(d)
        return stub(p)
    with pytest.raises(ProviderError) as e:optimize(SimpleNamespace(id='s',commit_sha=SHA),MATERIAL,lambda *a:None,lambda:None,planner,Reader(),Retriever())
    assert e.value.code=='optimization_contract'
    assert calls.count('OPTIMIZATION_PATH_REPAIR')==1 and 'OPTIMIZATION_CHECK' not in calls

def test_score_binds_exact_draft_and_skill_is_loaded():
    stub=Stub();_,a=write(None,MATERIAL,stub)
    from backend.app.resume_harness import digest
    from backend.app.resume_support import ROOT
    assert a['final_draft_hash']==digest(a['structured_draft'])==a['content_score']['draft_hash']
    assert (ROOT/'SKILL.md').read_text(encoding='utf-8') in next(p for s,p in stub.calls if s=='WRITE')


def test_optimization_first_then_resume_reuses_same_pack():
    stub=Stub()
    def model(p):
        if p.startswith('OPTIMIZATION_PLAN'):return json.dumps(report())
        if p.startswith('OPTIMIZATION_CHECK'):return json.dumps({'approved':True,'issues':[]})
        return stub(p)
    _,coverage=optimize(SimpleNamespace(id='s',commit_sha=SHA),MATERIAL,lambda *a:None,lambda:None,model,Reader(),Retriever())
    writer=Stub();_,audit=write(None,MATERIAL,writer)
    assert coverage['analysis_pack_id']==audit['analysis_pack_id']
    assert [stage for stage,_ in writer.calls]==['SELECT','WRITE','REVIEW_HR','REVIEW_TECHNICAL']

@pytest.mark.parametrize('kind',['test_source','documentation','code'])
def test_unconnected_declarations_or_tests_cannot_be_promoted_integrated(kind):
    from backend.app.resume_contract import Claim,check_claims
    from backend.tests.test_resume_quality import context
    from backend.app.source_reader import SourceEvidence
    source=SourceEvidence(id='e',kind=kind,repo='example/demo',commit_sha=SHA,content_hash='h',excerpt='register_tool / save_state',revision_status='resolved')
    c=Claim(id='c',statement='具备完整工具编排和恢复链路',evidence_ids=['e'],validation_level='integrated')
    with pytest.raises(ValueError,match='集成'):check_claims([c],{'e':source},context(),{})
    if kind!='code':
        c.integration_evidence_ids=['e'];c.integration_basis='测试调用了这个函数'
        with pytest.raises(ValueError,match='生产集成'):check_claims([c],{'e':source},context(),{})

def test_analysis_cache_corruption_does_not_silently_run_with_bad_facts(tmp_path):
    write(None,MATERIAL,Stub());cache=next((tmp_path/'analysis/shared/offline').glob('*.json'))
    data=json.loads(cache.read_text(encoding='utf-8'));data['discovery']['claims'][0]['statement']='tampered'
    cache.write_text(json.dumps(data),encoding='utf-8');stub=Stub()
    with pytest.raises(ProviderError) as e:write(None,MATERIAL,stub)
    assert e.value.code=='analysis_cache' and not stub.calls

def test_unresolved_snapshot_never_promotes_old_wiki():
    stub=Stub()
    with pytest.raises(ProviderError) as e:write(None,{**MATERIAL,'commit':'unresolved:github'},stub)
    assert e.value.code=='source_revision' and not stub.calls


def test_actual_architecture_entry_preserves_wiki_on_failure_then_reuses_shared(client,wid,monkeypatch):
    from backend.app.db import Session,Run,Evidence
    from backend.app import analysis
    client.post(f'/api/workspaces/{wid}/target',json={'role':'AI','jd':'多轮记忆'})
    snapshot=client.post(f'/api/workspaces/{wid}/repository-link',json={'url':'https://github.com/example/demo'}).json()
    wiki_calls=[];stub=Stub();fail=[True]
    class Wiki:
        def wiki(self,*args):wiki_calls.append(1);return {'generated_pages':{'p':{'content':'旧Wiki不能作为源码','filePaths':['wrong.py']}}}
        def close(self):pass
    class Model(Stub):
        def __call__(self,p):
            if p.startswith('OPTIMIZATION_PLAN'):
                if fail[0]:raise ProviderError('模拟下游异常','offline_failure')
                return json.dumps(report())
            if p.startswith('OPTIMIZATION_CHECK'):return json.dumps({'approved':True,'issues':[]})
            return stub(p)
    monkeypatch.setattr('backend.app.deepwiki.DeepWikiOpen',Wiki)
    monkeypatch.setattr('backend.app.optimization_review.WritingModel',Model)
    monkeypatch.setattr('backend.app.optimization_review.SourceReader',Reader)
    monkeypatch.setattr('backend.app.main.submit',lambda rid:None)
    response=client.post(f'/api/workspaces/{wid}/architecture-runs',json={'snapshot_id':snapshot['id'],'demo':False,'idempotency_key':'new-analysis'})
    assert response.status_code==200,response.text
    rid=response.json()['id'];analysis.execute(rid)
    with Session() as session:
        run=session.get(Run,rid);assert run.status=='failed' and run.result['wiki'] and run.result['failure_calls']
    first_upstream=len(stub.calls);fail[0]=False
    with Session.begin() as session:session.get(Run,rid).status='queued'
    analysis.execute(rid)
    with Session() as session:
        run=session.get(Run,rid);assert run.status=='completed',run.error
        assert run.result['analysis_pack_ref'] and run.result['report']['directions']==[]
        ids=run.result['source_evidence_ids'];assert ids
        assert all(session.get(Evidence,i).workspace_id==wid for i in ids)
        assert run.result['usage']['shared_analysis']==[]
    assert len(wiki_calls)==1 and len(stub.calls)==first_upstream


def test_writer_deduplicates_shared_source_and_verifier_owns_fact_labels():
    stub=Stub()
    def model(p):
        d=json.loads(stub(p))
        if p.startswith('INVESTIGATE\n'):
            for c in d['claims']:c['validation_level']='test_passed'
        return json.dumps(d)
    _,audit=write(None,MATERIAL,model)
    assert not any('REPAIR' in stage for stage,_ in stub.calls)
    assert all(c['validation_level']=='unknown' for c in audit['generated_claims'])
    prompt=next(p for stage,p in stub.calls if stage=='WRITE')
    payload=json.loads(prompt.split('\nJSON schema:')[0].split('\n')[-1])
    assert len(payload['sources'])==1 and payload['sources'][0]['id']=='source:memory'


def test_unlinked_optional_mechanisms_are_gaps_not_facts():
    from backend.app.resume_contract import Candidate,Analysis,Claim
    from pydantic import ValidationError
    import pytest
    raw={'candidate_id':'c1','title':'边界','claim_ids':['f1'],'exception_boundaries':[{'text':'失败后重试','claim_ids':[]}], 'mechanism_steps':[{'text':'校验版本','claim_ids':['f1']}]}
    card=Candidate.model_validate(raw)
    assert card.exception_boundaries==[]
    assert card.mechanism_steps[0].claim_ids==['f1']
    assert any('失败后重试' in gap for gap in card.gaps)
    assert raw['exception_boundaries'][0]['claim_ids']==[]
    assert Candidate.model_validate(card.model_dump())==card
    with pytest.raises(ValidationError):Candidate.model_validate({**raw,'claim_ids':[]})
    with pytest.raises(ValidationError):Claim.model_validate({'id':'f1','statement':'x','evidence_ids':[]})
    with pytest.raises(ValidationError):Candidate.model_validate({**raw,'gaps':['a','b','c','d','e']})
    result=Analysis.model_validate({'claims':[],'candidates':[raw]})
    assert result.candidates[0].exception_boundaries==[]


def test_jd_plan_validates_excerpt_before_stage_acceptance():
    from backend.app.shared_analysis import jd_plan_schema
    from pydantic import ValidationError
    import pytest
    row={'requirement_id':'r1','description':'记忆','origin':'jd','question':'如何记忆','search_terms':['memory'],'queries':['memory','记忆']}
    schema=jd_plan_schema('设计多轮对话与用户记忆机制','jd')
    with pytest.raises(ValidationError):schema.model_validate({'requirements':[row]})
    with pytest.raises(ValidationError):schema.model_validate({'requirements':[{**row,'original_excerpt':'不存在的原文'}]})
    assert schema.model_validate({'requirements':[{**row,'original_excerpt':'用户记忆机制'}]}).requirements[0].original_excerpt=='设计多轮对话与用户记忆机制'
    assert jd_plan_schema('','role_inferred').model_validate({'requirements':[{**row,'origin':'role_inferred'}]})


def test_verification_schema_checks_documentation_before_accepting_stage():
    from types import SimpleNamespace
    from backend.app.resume_contract import Claim
    from backend.app.shared_analysis import verification_schema
    from pydantic import ValidationError
    import pytest
    original=Claim(id='f1',statement='项目提供记忆',evidence_ids=['d1'])
    context=SimpleNamespace(commit_sha='a'*40)
    evidence={'d1':SimpleNamespace(kind='documentation',commit_sha='a'*40)}
    schema=verification_schema([original],evidence,context)
    with pytest.raises(ValidationError,match='f1'):
        schema.model_validate({'claims':[{**original.model_dump(),'validation_level':'code_present'}]})
    checked=schema.model_validate({'claims':[original.model_dump()]})
    assert checked.claims[0].statement==original.statement
    assert checked.claims[0].validation_level=='unknown'
    evidence['d1']=SimpleNamespace(kind='code',commit_sha='a'*40)
    assert schema.model_validate({'claims':[{**original.model_dump(),'validation_level':'code_present'}]}).claims[0].validation_level=='code_present'


def test_jd_refs_bind_exact_text_without_model_copying():
    from backend.app.shared_analysis import jd_plan_schema
    from pydantic import ValidationError
    import pytest
    schema=jd_plan_schema('1. Agent 编排。\n2. 用户记忆。','jd')
    row={'requirement_id':'r','description':'任务连续性','question':'如何保持状态','search_terms':['state'],'queries':['状态','state'], 'jd_source_ids':['JD-01','JD-02'],'original_excerpt':'模型自行改写的文字'}
    result=schema.model_validate({'requirements':[row]}).requirements[0]
    assert result.original_excerpt=='1. Agent 编排。\n2. 用户记忆。'
    assert result.origin=='jd'
    with pytest.raises(ValidationError):schema.model_validate({'requirements':[{**row,'jd_source_ids':['JD-99']}]})


def test_optimization_schema_enumerates_read_paths_in_all_citations():
    from backend.app.optimization_review import report_schema
    schema=report_schema({'lib/read.ts'}).model_json_schema()
    found=[]
    def walk(node):
        if isinstance(node,dict):
            for key,value in node.get('properties',{}).items():
                if key in ('paths','source_paths'):found.append(value['items']['enum'])
            for value in node.values():walk(value)
        elif isinstance(node,list):
            for value in node:walk(value)
    walk(schema)
    assert len(found)>=3 and all(value==['lib/read.ts'] for value in found)
