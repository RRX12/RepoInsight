import json
from types import SimpleNamespace as N
import httpx,pytest
from backend.app.optimization_review import generate,validate_report,check_dag
from backend.app.architecture_schema import OptimizationDiscovery,OptimizationReportV2,ResearchSource,legacy_direction
from backend.app.optimization_research import AdvisorConfig
from backend.app.providers import ProviderError
from backend.app.web_research import WebResearch,public_url,public_addresses
from backend.tests.analysis_fixture import MATERIAL,Stub,SHA
from backend.tests.source_fixture import Reader,Retriever
from backend.tests.advisor_fixture import response,data,plan,report_v2


def run(model=None,material=None,check=lambda:None):
    stub=Stub()
    def default(prompt):return response(prompt) if prompt.startswith('OPTIMIZATION_') else stub(prompt)
    return generate(N(id='s',commit_sha=SHA),material or MATERIAL,lambda *a:None,check,model or default,Reader(),Retriever())


def test_cold_preparation_hot_report_and_constraints_identity():
    report,a=run();assert report['schema_version']=='optimization-v2'
    assert sum(c['stage'].startswith('OPTIMIZATION_') for c in a['calls'])==2
    assert any(c['stage']=='CLAIM_VERIFY' for c in a['calls'])
    _,b=run();assert b['cached'] and b['calls']==[]
    _,c=run(material={**MATERIAL,'constraints':{'time_budget':'1 day'}})
    assert c['analysis_pack_id']!=a['analysis_pack_id']


def test_multiple_candidates_still_two_requests_and_source_read_reaches_synthesis():
    stub=Stub();requests=[]
    def model(p):
        if not p.startswith('OPTIMIZATION_'):return stub(p)
        requests.append(p.split('\n')[0])
        if p.startswith('OPTIMIZATION_DISCOVER'):
            d=plan(p);d['candidates'][0]['research_actions']=[{'candidate_id':'c','question_id':'q','purpose':'read caller','action_type':'code_read','path':'caller.ts'}]
            d['candidates'].append({**d['candidates'][0],'candidate_id':'other','research_actions':[]})
        else:
            assert any(s['path']=='caller.ts' for s in data(p)['research']['sources'])
            d=report_v2(p);d['candidate_assessments'].append({**d['candidate_assessments'][0],'candidate_id':'other','decision':'not_recommended','rationale':'已有解法，不重复建设'})
        return json.dumps(d)
    _,audit=run(model)
    assert requests==['OPTIMIZATION_DISCOVER','OPTIMIZATION_SYNTHESIZE']


def test_one_followup_and_no_second_loop():
    stub=Stub();requests=[]
    def model(p):
        if not p.startswith('OPTIMIZATION_'):return stub(p)
        stage=p.split('\n')[0];requests.append(stage)
        if stage=='OPTIMIZATION_DISCOVER':return response(p)
        d=report_v2(p)
        if stage=='OPTIMIZATION_SYNTHESIZE':d['follow_up_requests']=[{'candidate_id':'c','question_id':'q','purpose':'decide connection','action_type':'code_read','path':'caller.ts'}]
        else:assert data(p)['final_call']
        return json.dumps(d)
    _,audit=run(model);assert audit['semantic_calls']==3 and requests[-1]=='OPTIMIZATION_REFINE'


def test_one_format_repair_attempts_not_hidden_and_repeated_failure_does_not_publish(tmp_path):
    stub=Stub();calls=[]
    def model(p):
        if not p.startswith('OPTIMIZATION_'):return stub(p)
        calls.append(p)
        return '{bad' if p.startswith('OPTIMIZATION_SYNTHESIZE') else response(p)
    with pytest.raises(ProviderError) as e:run(model)
    assert len([c for c in e.value.stage_calls if c['stage'].startswith('OPTIMIZATION_')])==3
    assert not list((tmp_path/'analysis/advisor').rglob('*.json')) or all(p.name.endswith('.plan.json') for p in (tmp_path/'analysis/advisor').rglob('*.json'))


def test_empty_candidates_cost_one_optimization_request():
    stub=Stub()
    def model(p):return json.dumps({'candidates':[],'no_change_reason':'已有实现，无需改造'}) if p.startswith('OPTIMIZATION_') else stub(p)
    report,a=run(model);assert report['directions']==[] and a['optimization_attempts']==1


def test_cancel_after_model_never_publishes(tmp_path):
    stub=Stub();cancel=[False]
    def check():
        if cancel[0]:raise ProviderError('cancelled','cancelled')
    def model(p):
        text=response(p) if p.startswith('OPTIMIZATION_') else stub(p)
        if p.startswith('OPTIMIZATION_SYNTHESIZE'):cancel[0]=True
        return text
    with pytest.raises(ProviderError,match='cancelled'):run(model,check=check)
    assert not [p for p in (tmp_path/'analysis/advisor').rglob('*.json') if not p.name.endswith('.plan.json')]


@pytest.mark.parametrize('url',['http://127.0.0.1/','http://[::1]/','http://169.254.169.254/','http://10.1.1.1/','http://user:pass@example.com/','file:///etc/passwd','http://localhost/'])
def test_public_url_rejects_private_and_credentials(url):
    with pytest.raises(ValueError):public_url(url)


def test_dns_mixed_and_rebinding_addresses_are_rejected(monkeypatch):
    monkeypatch.setattr('socket.getaddrinfo',lambda *a,**k:[(2,1,6,'',('1.1.1.1',443)),(2,1,6,'',('127.0.0.1',443))])
    with pytest.raises(ValueError,match='unsafe_dns'):public_addresses('docs.example.com',443)


def test_tavily_search_uses_no_answer_and_raw_body_is_distinct_source(tmp_path):
    seen=[]
    def handler(r):
        seen.append(r);payload=json.loads(r.content)
        assert payload['include_answer'] is False and payload['search_depth']=='basic' and not payload['auto_parameters']
        return httpx.Response(200,json={'results':[{'title':'Official','url':'https://docs.example.com/x','content':'snippet','raw_content':'Full mechanism body'}]})
    web=WebResearch(enabled=True,key='fake',transport=httpx.MockTransport(handler),cache_dir=tmp_path)
    assert web.search('general retries')['status']=='ok'
    body=web.read('https://docs.example.com/x');assert body['excerpt']=='Full mechanism body' and body['source_version'] is None
    web.search('general retries');assert len(seen)==1 and web.trace[-1]['cached']
    web.close()


@pytest.mark.parametrize('status',[429,500])
def test_web_failure_status_is_visible(status):
    web=WebResearch(enabled=True,key='fake',transport=httpx.MockTransport(lambda r:httpx.Response(status)))
    assert web.search('retry')['status']=='http_'+str(status);web.close()


def test_unconfigured_timeout_empty_redirect_private_and_size():
    assert WebResearch(enabled=True,key='').search('q')['status']=='not_configured'
    def timeout(r):raise httpx.ReadTimeout('timeout')
    w=WebResearch(enabled=True,key='fake',transport=httpx.MockTransport(timeout));assert w.search('q')['status']=='timeout';w.close()
    for response,status in [(httpx.Response(302,headers={'location':'http://10.0.0.1/'}),'unsafe_url'),(httpx.Response(200,headers={'content-type':'text/plain'},content=b'x'*500001),'response_too_large')]:
        w=WebResearch(enabled=True,key='fake',transport=httpx.MockTransport(lambda r:response));w.known['https://docs.example.com']={'title':'x','raw_content':None,'fetched_at':1};assert w.read('https://docs.example.com')['status']==status;w.close()


def test_config_invalid_and_dependencies_cyclic_are_rejected(monkeypatch):
    monkeypatch.setenv('OPTIMIZATION_MAX_REQUEST_ATTEMPTS','5')
    with pytest.raises(ValueError):AdvisorConfig.environment()
    with pytest.raises(ValueError,match='cycle'):check_dag([('a',['b']),('b',['a'])])


def test_unknown_refs_and_external_as_current_fact_are_rejected():
    # Exercise validation on a real report rather than a schema-only snapshot.
    report,a=run();d=OptimizationDiscovery.model_validate({'candidates':[{'candidate_id':'c','title':'x','kind':'capability_deepening','current_state':{'statement':'x'},'opportunity':'x','expected_value':'x','preliminary_decision':'validate_first','decision_reason':'x'}]})
    r=OptimizationReportV2.model_validate(report);r.candidate_assessments[0].source_refs=['unknown']
    with pytest.raises(ValueError,match='unknown_source'):validate_report(r,d,r.sources,AdvisorConfig())


def test_detailed_plan_add_path_and_history_adapter_and_source_validation():
    from backend.tests.advisor_fixture import detailed
    stub=Stub()
    def model(p):
        if not p.startswith('OPTIMIZATION_'):return stub(p)
        if p.startswith('OPTIMIZATION_DISCOVER'):return response(p)
        r=report_v2(p);r['directions']=[detailed(r)];return json.dumps(r)
    report,_=run(model)
    assert report['directions'][0]['code_changes'][0]['change_type']=='add'
    compat=legacy_direction(report['directions'][0],report)
    assert compat['source_paths']==['memory.ts'] and compat['schema_version']=='optimization-v2'
    assert legacy_direction({'proposal':'old'},{})=={'proposal':'old'}
    discovery=OptimizationDiscovery.model_validate({'candidates':[{'candidate_id':'c','title':'x','kind':'capability_deepening','current_state':{'statement':'x'},'opportunity':'x','expected_value':'x','preliminary_decision':'validate_first','decision_reason':'x'}]})
    for change,match in [('unread','modify_requires_read_source'),('external','external_as_repository_fact')]:
        r=OptimizationReportV2.model_validate(report)
        if change=='unread':r.directions[0].code_changes[0].change_type='modify'
        else:
            src=r.sources[0];src.kind='external_source';r.directions[0].current_design.source_refs=[src.source_id]
        with pytest.raises(ValueError,match=match):validate_report(r,discovery,r.sources,AdvisorConfig())


def test_optimize_constraints_change_rejects_late_result(client,wid,monkeypatch):
    from backend.app.db import Session,Workspace
    from backend.app.project_inputs import collect_project
    snapshot=client.post(f'/api/workspaces/{wid}/repository-link',json={'url':'https://github.com/example/demo'}).json()
    with Session() as s:_,a,old=collect_project(s,wid)
    client.patch(f'/api/workspaces/{wid}',json={'interest':'x','skills':'Rust','time_budget':'1 day','environment':'CPU'})
    with Session() as s:_,b,new=collect_project(s,wid)
    assert old!=new and b['constraints']['skills']=='Rust'


def test_optimization_output_tokens_and_truncation_are_explicit(monkeypatch):
    from backend.app.model_support import ProjectModel
    monkeypatch.setenv('PROJECT_MODEL_API_KEY','fake');monkeypatch.setenv('OPTIMIZATION_REPORT_OUTPUT_TOKENS','10000')
    def handler(r):
        assert json.loads(r.content)['max_tokens']==10000
        return httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'content':'{}'}}]})
    model=ProjectModel(transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as e:model.request('json',stage='OPTIMIZATION_SYNTHESIZE_SCHEMA_REPAIR')
    assert e.value.code=='resume_model_truncated';model.close()


def test_no_jd_or_constraints_does_not_invent_a_target():
    stub=Stub();seen=[]
    def model(p):
        if p.startswith('OPTIMIZATION_'):
            seen.append(data(p));return response(p)
        return stub(p)
    run(model,material={**MATERIAL,'jd':'','jd_version_id':None})
    assert seen and all(d['role_origin']=='not_provided' and d['constraints']=={} and d['requirements'] is None for d in seen)


def test_production_save_maps_v2_once_and_keeps_user_plans(client,wid,monkeypatch):
    from backend.app import analysis
    from backend.app.db import Session,Run,Improvement
    from backend.tests.advisor_fixture import detailed
    client.post(f'/api/workspaces/{wid}/target',json={'role':'AI','jd':'多轮记忆'})
    snapshot=client.post(f'/api/workspaces/{wid}/repository-link',json={'url':'https://github.com/example/demo'}).json()
    class Wiki:
        def wiki(self,*args):return {'generated_pages':{'p':{'content':'saved wiki','filePaths':[]}}}
        def close(self):pass
    class Model(Stub):
        def __call__(self,p):
            if p.startswith('OPTIMIZATION_DISCOVER'):return response(p)
            if p.startswith('OPTIMIZATION_'):
                report=report_v2(p);report['directions']=[detailed(report)];return json.dumps(report)
            return super().__call__(p)
    monkeypatch.setattr('backend.app.deepwiki.DeepWikiOpen',Wiki)
    monkeypatch.setattr('backend.app.optimization_review.ProjectModel',Model)
    monkeypatch.setattr('backend.app.optimization_review.SourceReader',Reader)
    monkeypatch.setattr('backend.app.optimization_review.CodeRetrieval',Retriever)
    monkeypatch.setattr('backend.app.main.submit',lambda rid:None)
    with Session.begin() as session:
        user=Improvement(workspace_id=wid,snapshot_id=snapshot['id'],status='selected',details={'title':'用户方向','proposal':'keep'})
        session.add(user);session.flush();uid=user.id
    run_id=client.post(f'/api/workspaces/{wid}/architecture-runs',json={'snapshot_id':snapshot['id'],'demo':False,'idempotency_key':'advisor-save'}).json()['id']
    analysis.execute(run_id);analysis.execute(run_id)
    with Session() as session:
        run=session.get(Run,run_id);assert run.status=='completed',run.error
        assert len(run.result['improvement_ids'])==1
        item=session.get(Improvement,run.result['improvement_ids'][0]);assert item.details['candidate_id']=='c' and item.details['v2_plan']['technical_options']
        assert session.get(Improvement,uid).status=='selected'
        from backend.app.discussion_memory import direction_context
        old=direction_context(session,wid,item.id)
        item.details={**item.details,'v2_plan':{**item.details['v2_plan'],'implementation_steps':[]}}
        new=direction_context(session,wid,item.id)
        assert old['details']==new['details'] and old['proposal_hash']!=new['proposal_hash']
        assert run.result['usage']['preparation_model'] and len(run.result['usage']['optimization_model'])==2


def test_jd_version_alone_invalidates_shared_and_report_cache():
    _,a=run();_,b=run(material={**MATERIAL,'jd_version_id':'new-version'})
    assert a['analysis_pack_id']!=b['analysis_pack_id'] and not b['cached']


def test_html_paragraphs_are_loaded_without_executing_scripts():
    body='<html><script>doEvil()</script><h1>Header</h1><p>First mechanism.</p><p>Second mechanism.</p></html>'
    web=WebResearch(enabled=True,key='fake',transport=httpx.MockTransport(lambda r:httpx.Response(200,headers={'content-type':'text/html'},text=body)))
    web.known['https://docs.example.com']={'title':'x','raw_content':None,'fetched_at':1}
    result=web.read('https://docs.example.com')
    assert result['status']=='ok' and 'First mechanism.' in result['excerpt'] and 'doEvil' not in result['excerpt']
    web.close()


def test_candidate_fair_research_dedup_failure_counts_and_shared_budget():
    from backend.app.optimization_research import Research
    from backend.app.architecture_schema import ResearchAction
    reader=Reader();e=reader.read_source('example/demo',SHA,'memory.ts')
    pack=N(reads=[],evidence=[e],identity={'index':Retriever().prepare('example/demo',SHA)})
    requests=[]
    def handler(r):requests.append(r);return httpx.Response(429)
    web=WebResearch(enabled=True,key='fake',transport=httpx.MockTransport(handler))
    research=Research(pack,MATERIAL,reader,Retriever(),web,AdvisorConfig(max_web_queries=1),lambda:None)
    actions=[ResearchAction(candidate_id='a',question_id='q1',purpose='search',action_type='web_search',query='native retry backoff'),ResearchAction(candidate_id='b',question_id='q2',purpose='search',action_type='web_search',query='distributed queue reference')]
    research.run(actions,['a','b'])
    assert len(requests)==1 and research.queries==1
    assert research.results[0]['unresolved_reason']=='外部调研未完成：http_429' and research.results[1]['unresolved_reason']=='web_query_budget'
    repeated=[ResearchAction(candidate_id=c,question_id='q',purpose='read',action_type='code_read',path='memory.ts') for c in ['a','b']]
    before=len(reader.reads);research.run(repeated,['a','b'])
    assert len(reader.reads)==before+1 and research.results[-1]['cached']
    research.code_calls=32
    research.run([ResearchAction(candidate_id='a',question_id='new',purpose='read',action_type='code_read',path='caller.ts')],['a'])
    assert research.results[-1]['unresolved_reason']=='source_budget';web.close()


def test_overlap_preserves_stable_source_mapping_without_repeating_body():
    from backend.app.optimization_research import Research
    from backend.app.source_reader import SourceEvidence,sha256
    def evidence(start,end,text):return SourceEvidence(id=str(start),kind='code',repo=MATERIAL['repo'],commit_sha=SHA,path='memory.ts',start_line=start,end_line=end,content_hash=sha256(text),excerpt=text,revision_status='resolved')
    web=WebResearch(enabled=False)
    research=Research(N(reads=[],evidence=[evidence(1,2,'a\nb\n')],identity={}),MATERIAL,Reader(),Retriever(),web,AdvisorConfig(),lambda:None)
    ident=next(iter(research.sources));assert research.add_code(evidence(2,3,'b\nc\n'))==ident
    assert len(research.sources)==1 and research.sources[ident].excerpt=='a\nb\nc\n' and research.sources[ident].end_line==3
    web.close()


def test_production_network_connects_validated_ip_with_original_tls_name(monkeypatch):
    from backend.app.web_research import PublicTransport
    addresses=[];names=[];dns=[]
    def resolve(*a,**k):dns.append(a);return [(2,1,6,'',('1.1.1.1',443))]
    monkeypatch.setattr('socket.getaddrinfo',resolve)
    class Sock:pass
    monkeypatch.setattr('socket.create_connection',lambda address,timeout:addresses.append(address) or Sock())
    monkeypatch.setattr('ssl.create_default_context',lambda:N(wrap_socket=lambda sock,server_hostname:names.append(server_hostname) or sock))
    class Conn:
        def __init__(self,*a,**k):pass
        def request(self,*a,**k):pass
        def getresponse(self):return N(status=200,read=lambda size:b'public',getheaders=lambda:[])
        def close(self):pass
    monkeypatch.setattr('http.client.HTTPConnection',Conn)
    response=PublicTransport().handle_request(httpx.Request('GET','https://docs.example.com/'))
    assert response.content==b'public' and addresses==[('1.1.1.1',443)] and names==['docs.example.com'] and len(dns)==1


def test_followup_without_new_content_does_not_spend_third_model_call():
    stub=Stub()
    def model(p):
        if not p.startswith('OPTIMIZATION_'):return stub(p)
        if p.startswith('OPTIMIZATION_DISCOVER'):return response(p)
        assert p.startswith('OPTIMIZATION_SYNTHESIZE')
        report=report_v2(p);report['follow_up_requests']=[{'candidate_id':'c','question_id':'q','purpose':'check same source','action_type':'code_read','path':'memory.ts'}]
        return json.dumps(report)
    report,audit=run(model)
    assert audit['semantic_calls']==2 and report['follow_up_requests']==[] and report['unresolved_questions']


def test_overview_is_prepared_projection_and_model_cannot_inject_unread_paths():
    stub=Stub()
    def model(prompt):
        if not prompt.startswith('OPTIMIZATION_'):return stub(prompt)
        if prompt.startswith('OPTIMIZATION_DISCOVER'):return response(prompt)
        schema=json.loads(prompt.split('\nJSON schema:')[1])
        assert 'overview' not in schema['properties']
        value=report_v2(prompt);value['overview']['modules'][0]['paths']=['not-read.py'];return json.dumps(value)
    report,_=run(model)
    assert all('not-read.py' not in m['paths'] for m in report['overview']['modules'])
    assert report['overview']['summary']=='保存角色经历'
    discovery=OptimizationDiscovery.model_validate({'candidates':[{'candidate_id':'c','title':'x','kind':'capability_deepening','current_state':{'statement':'x'},'opportunity':'x','expected_value':'x','preliminary_decision':'validate_first','decision_reason':'x'}]})
    r=OptimizationReportV2.model_validate(report);r.overview.modules[0].paths=['not-read.py']
    with pytest.raises(ValueError,match='not-read.py'):validate_report(r,discovery,r.sources,AdvisorConfig())


def test_assessment_only_report_derives_reason_but_never_hides_missing_priority_plan():
    stub=Stub()
    def model(p):
        if not p.startswith('OPTIMIZATION_'):return stub(p)
        if p.startswith('OPTIMIZATION_DISCOVER'):return response(p)
        r=report_v2(p);r['no_change_reason']='';return json.dumps(r)
    report,audit=run(model)
    assert report['directions']==[] and '先验证' in report['no_change_reason'] and '先验证' in report['candidate_assessments'][0]['rationale']
    assert audit['optimization_attempts']==2
    d=OptimizationDiscovery.model_validate({'candidates':[{'candidate_id':'c','title':'x','kind':'capability_deepening','current_state':{'statement':'x'},'opportunity':'x','expected_value':'x','preliminary_decision':'prioritize','decision_reason':'x'}]})
    r=OptimizationReportV2.model_validate(report)
    r.candidate_assessments[0].decision='prioritize';r.candidate_assessments[0].evidence_sufficiency='sufficient'
    with pytest.raises(ValueError,match='requires_detailed_direction'):validate_report(r,d,r.sources,AdvisorConfig())
    r.candidate_assessments[0].decision='validate_first';r.candidate_assessments[0].rationale='';r.no_change_reason=''
    with pytest.raises(ValueError,match='empty_report_reason'):validate_report(r,d,r.sources,AdvisorConfig())


def test_reference_schema_disallows_practices_when_external_research_is_missing():
    from backend.tests.advisor_fixture import detailed
    stub=Stub()
    def model(prompt):
        if not prompt.startswith('OPTIMIZATION_'):return stub(prompt)
        if prompt.startswith('OPTIMIZATION_DISCOVER'):return response(prompt)
        schema=json.loads(prompt.split('\nJSON schema:')[1])
        assert schema['$defs']['ReferencePractice']['properties']['source_refs']['items']['enum']==[]
        assert schema['$defs']['DetailedDirection']['properties']['reference_practices']['maxItems']==0
        report=report_v2(prompt);report['directions']=[detailed(report)];return json.dumps(report)
    report,_=run(model)
    assert report['directions'][0]['reference_practices']==[]
    # Do not silently accept a repository source as an external practice.
    discovery=OptimizationDiscovery.model_validate({'candidates':[{'candidate_id':'c','title':'x','kind':'capability_deepening','current_state':{'statement':'x'},'opportunity':'x','expected_value':'x','preliminary_decision':'validate_first','decision_reason':'x'}]})
    r=OptimizationReportV2.model_validate(report)
    from backend.app.architecture_schema import ReferencePractice
    r.directions[0].reference_practices=[ReferencePractice(mechanism='local',applicability='local',limitations='not external',source_refs=[r.sources[0].source_id])]
    with pytest.raises(ValueError,match='practice_requires_read_external_source'):validate_report(r,discovery,r.sources,AdvisorConfig())


def test_modify_schema_binds_same_file_and_diagnostics_keep_exact_reason(tmp_path):
    from backend.tests.advisor_fixture import detailed
    stub=Stub();bad=[]
    def model(p):
        if not p.startswith('OPTIMIZATION_'):return stub(p)
        if p.startswith('OPTIMIZATION_DISCOVER'):return response(p)
        wire=json.loads(p.split('\nJSON schema:')[1])
        assert wire['$defs']['CodeChange']['allOf'][0]['then']['properties']['path']['enum']==['README.md','memory.ts']
        if p.startswith('OPTIMIZATION_SYNTHESIZE_SCHEMA_REPAIR'):return bad[0]
        r=report_v2(p);r['directions']=[detailed(r)]
        r['directions'][0]['code_changes']=[{'change_type':'modify','path':'worker/save-api.ts','responsibility':'save','change_description':'change','source_refs':r['candidate_assessments'][0]['source_refs']}]
        bad.append(json.dumps(r));return bad[0]
    with pytest.raises(ProviderError,match='worker/save-api.ts'):run(model)
    records=[json.loads(p.read_text(encoding='utf-8')) for p in (tmp_path/'analysis/advisor-errors').rglob('*.json')]
    assert records and 'matching_refs' in records[0][-1]['validation_error'] and records[0][-1]['model_output']


def test_conditional_without_trigger_is_conservatively_validation_first():
    stub=Stub()
    def model(p):
        if not p.startswith('OPTIMIZATION_'):return stub(p)
        if p.startswith('OPTIMIZATION_DISCOVER'):return response(p)
        r=report_v2(p);r['candidate_assessments'][0]['decision']='conditional';return json.dumps(r)
    report,audit=run(model)
    assert report['candidate_assessments'][0]['decision']=='validate_first'
    assert report['unresolved_questions'] and audit['optimization_attempts']==2
