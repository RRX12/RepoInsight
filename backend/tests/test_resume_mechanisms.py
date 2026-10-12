"""Production writer contracts, not a claim of real model content quality."""
import json
import pytest
from backend.app.providers import ProviderError
from backend.app.resume_contract import Candidate, Claim, Choice, Discovery, Requirement
from backend.app.resume_quality import writing_pack, source_investigation, validate_discovery
from backend.app.source_reader import SourceEvidence
from backend.tests.test_resume_quality import Stub, MATERIAL, SHA, claim, candidate, context
from backend.app.resume_writer import write

def test_writer_packet_excludes_rejected_and_unsupported_mechanisms():
    supported=Claim(**claim(support='supported'))
    absent=Claim(**claim('c2'))
    c=Candidate(**{**candidate(),'claim_ids':['c1','c2'],'atomic_fact_ids':['c1','c2'],
        'mechanism_steps':[{'text':'拒绝过期更新','claim_ids':['c1']},{'text':'未证明的自动恢复','claim_ids':['c2']}],
        'personal_contribution':'我独立实现全部模块'})
    cards,claims=writing_pack({'n1':c,'n2':Candidate(**candidate('n2','c2'))},{'c1':supported,'c2':absent},Choice(selected_ids=['n1'],reasons={'n1':'版本一致性'}))
    assert set(claims)=={'c1'} and [c['candidate_id'] for c in cards]==['n1']
    assert cards[0]['atomic_fact_ids']==['c1']
    assert len(cards[0]['mechanism_steps'])==1 and 'personal_contribution' not in cards[0]
    assert cards[0]['problem']=='' and 'reason' not in cards[0]

def test_card_fact_reference_must_belong_to_candidate():
    d=Discovery(claims=[Claim(**claim())],candidates=[Candidate(**{**candidate(),'exception_boundaries':[{'text':'撤销时终止','claim_ids':['invented']}]})])
    with pytest.raises(ValueError,match='机制卡片事实'):
        validate_discovery(d,{'wiki:0:chunk:0:span:0':SourceEvidence(id='wiki:0:chunk:0:span:0',kind='wiki',repo='example/demo',commit_sha='unknown',content_hash='h',excerpt='x',revision_status='unknown')},[Requirement(requirement_id='r1',description='memory',origin='jd',question='memory?',search_terms=['memory'])],context(),{})

def test_source_reads_are_candidate_driven_and_share_budget(monkeypatch):
    monkeypatch.setenv('RESUME_SOURCE_FILES','2')
    class Reader:
        def __init__(self):self.reads=[]
        def list_tree(self,*args):return {'paths':['README.md','app/View.tsx','lib/boundary.ts','lib/consent.ts','lib/memory.ts'],'truncated':False}
        def search_ranges(self,repo,sha,path,terms):
            self.reads.append((path,terms))
            return [SourceEvidence(id=path,kind='code',repo=repo,commit_sha=sha,path=path,content_hash='h',excerpt='x',revision_status='resolved')]
    reader=Reader();ledger={'paths':set(),'chars':0};evidence={}
    c=Candidate(**{**candidate(),'investigation_questions':['consent withdraw 如何终止？'],'source_paths':['lib/boundary.ts','lib/consent.ts']})
    first=source_investigation(reader,{**MATERIAL,'commit':SHA},evidence,[],cards=[c],ledger=ledger)
    c.source_paths=['lib/memory.ts']
    second=source_investigation(reader,{**MATERIAL,'commit':SHA},evidence,[],cards=[c],ledger=ledger)
    assert {p for p,_ in reader.reads}=={'lib/boundary.ts','lib/consent.ts'}
    assert len(reader.reads)==2 and ledger['chars']==2
    assert first[0]['candidates'][0]['candidate_id']=='n1'
    assert any(r['status']=='budget' for r in second)

def test_no_gap_does_not_read_source_or_invent_connection():
    class Reader:
        def list_tree(self,*args):raise AssertionError('no gap means no source scan')
    assert source_investigation(Reader(),{**MATERIAL,'commit':SHA},{},[],cards=[Candidate(**candidate())])[0]['status']=='not_needed'

def test_missing_mechanism_repairs_only_downstream_once():
    stub=Stub();rounds=0
    def model(prompt):
        nonlocal rounds
        stage=prompt.split('\n',1)[0]
        if stage=='REVIEW_TECHNICAL':
            rounds+=1
            return json.dumps({'approved':rounds>1,'feedback':[] if rounds>1 else [{'category':'mechanism_missing','issue':'解释过期更新拒绝','candidate_ids':['n1']}]})
        if stage=='DISCOVER_INCREMENTAL':return stub('DISCOVER\n')
        return stub(prompt)
    _,audit=write(None,MATERIAL,model)
    stages=[r['stage'] for r in audit['harness']['calls']]
    assert stages.count('DISCOVER_INCREMENTAL')==1
    assert stages.count('PRODUCT')==stages.count('JD_PLAN')==stages.count('DISCOVER')==1
    assert stages.count('CLAIM_VERIFY_RESELECT')==1
    assert audit['reselected'] and len(audit['reviews'])==2 and audit['final_model_reviewed'] is True

def test_production_writer_keeps_project_spine_but_not_unselected_cards():
    stub=Stub();_,audit=write(None,MATERIAL,stub)
    prompt=next(p for stage,p in stub.calls if stage=='WRITE')
    assert '"id": "c2"' in prompt and '"candidate_id": "n2"' not in prompt
    assert audit['project_spine_claim_ids']==['c1','c2']
    assert '"product":' not in prompt
    assert 'mechanism' not in audit['selection']['selected'][0]['card']
    assert audit['selection']['selected'][0]['card']['gaps']==[]

def test_fact_feedback_reverifies_only_named_fact_without_source_restart():
    stub=Stub();reviews=0
    def model(prompt):
        nonlocal reviews
        stage=prompt.split('\n',1)[0]
        if stage=='REVIEW_TECHNICAL':
            reviews+=1
            return json.dumps({'approved':reviews>1,'feedback':[] if reviews>1 else [{'category':'fact_attribution','issue':'核对归属','claim_ids':['c1'],'part_ids':['b1']}]})
        if stage=='CLAIM_VERIFY_FEEDBACK':
            assert '"id": "c2"' not in prompt
            return json.dumps({'claims':[claim(support='supported')]})
        if stage=='RESELECT_FACT':return stub('SELECT\n')
        return stub(prompt)
    _,audit=write(None,MATERIAL,model)
    stages=[r['stage'] for r in audit['harness']['calls']]
    assert stages.count('CLAIM_VERIFY_FEEDBACK')==1
    assert stages.count('JD_PLAN')==stages.count('DISCOVER')==1
    assert not any(r['stage']=='DISCOVER_INCREMENTAL' for r in audit['trace'])
    assert audit['reviews'][0]['perspectives'][1]['feedback'][0]['blocking'] is True

def test_checkpoint_runner_caps_paid_calls_and_labels_replay(monkeypatch):
    import importlib.util
    from pathlib import Path
    from backend.app.providers import ProviderError
    spec=importlib.util.spec_from_file_location('resume_eval',Path('scripts/eval-resume-quality.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    class Provider:
        model='offline-test';usage=[]
        def request(self,*args,**kwargs):return '{}'
        def close(self):pass
    monkeypatch.setattr('backend.app.resume_support.WritingModel',Provider)
    audit={'candidates':[candidate()],'generated_claims':[claim()], 'project_map':{'facts':[]}}
    model=module.CheckpointModel(audit,MATERIAL,'n1',1)
    assert json.loads(model.request('ANALYZE\n',stage='ANALYZE'))=={'facts':[],'uncertainties':[]}
    assert model.paid==0 and model.replayed==['ANALYZE']
    model.request('WRITE\n',stage='WRITE')
    with pytest.raises(ProviderError,match='付费调用预算'):model.request('WRITE\n',stage='WRITE')
    assert model.paid==1

def test_actual_artifact_api_keeps_selected_fact_packet_and_idempotent_output(client,wid,monkeypatch):
    from backend.app.db import Session,Run
    snap=client.post(f'/api/workspaces/{wid}/repository-link',json={'url':'https://github.com/example/demo'}).json()
    with Session.begin() as s:
        s.add(Run(workspace_id=wid,status='completed',request={'snapshot_id':snap['id']},result={'wiki':{'generated_pages':{'memory':MATERIAL['_full_wiki_pages'][0]}}},idempotency_key='mechanism-wiki'))
    stub=Stub();monkeypatch.setattr('backend.app.resume_support.WritingModel',lambda:stub)
    body={'type':'resume','writing_mode':'model','target_role':'AI','target_jd':'多轮记忆','idempotency_key':'mechanism-resume'}
    first=client.post(f'/api/workspaces/{wid}/artifacts',json=body)
    assert first.status_code==200,first.text
    audit=next(c for c in first.json()['claims'] if c['kind']=='writing_review')
    assert audit['schema_version']=='resume-quality-v5'
    assert audit['structured_draft']['bullets'][0]['claim_ids']==['c1']
    count=len(stub.calls)
    second=client.post(f'/api/workspaces/{wid}/artifacts',json=body)
    assert second.status_code==200 and second.json()['id']==first.json()['id']
    assert len(stub.calls)==count

def test_unbound_model_personal_label_is_capped_without_promoting_fact():
    from backend.app.resume_quality import bound_attribution
    c=Claim(**{**claim(support='supported'),'attribution':'user_confirmed'})
    evidence={ref:SourceEvidence(id=ref,kind='wiki',repo='example/demo',commit_sha='unknown',content_hash='h',excerpt='项目已实现机制',revision_status='unknown') for ref in c.evidence_ids}
    original=bound_attribution(c,{},evidence)
    assert original['attribution']=='user_confirmed'
    assert c.attribution=='unknown'
    assert c.implementation_state=='implemented'
    assert c.validation_level==claim(support='supported').get('validation_level','unknown')
    assert c.contribution_id is None and c.support=='supported'
    user_plan=Claim(**{**claim(support='supported'),'attribution':'user_confirmed','evidence_ids':['plan']})
    plan=SourceEvidence(id='plan',kind='user_statement',repo='example/demo',commit_sha='unknown',content_hash='h',excerpt='只是讨论，尚未实现',revision_status='user_submitted')
    bound_attribution(user_plan,{}, {'plan':plan})
    assert user_plan.implementation_state=='unknown' and user_plan.attribution=='unknown'
    confirmed=Claim(**{**claim(support='supported'),'attribution':'user_confirmed','contribution_id':'u'})
    assert bound_attribution(confirmed,{'u':{'state':'implemented'}}) is None
    assert confirmed.attribution=='user_confirmed'

def test_discovery_link_repair_is_bounded_and_preserves_claim_collection():
    stub=Stub();repairs=[]
    def model(prompt):
        stage=prompt.split('\n',1)[0]
        if stage=='DISCOVER':
            d=json.loads(stub(prompt))
            d['candidates'][0]['exception_boundaries']=[{'text':'过期拒绝','claim_ids':['c2']}]
            return json.dumps(d)
        if stage=='DISCOVER_LINK_REPAIR':
            repairs.append(stage);return json.dumps({'patches':[{'target':'candidate','target_id':'n1','field':'exception_boundaries','index':0,'drop':True}]})
        return stub(prompt)
    _,audit=write(None,MATERIAL,model)
    assert repairs==['DISCOVER_LINK_REPAIR']
    assert {c['id'] for c in audit['generated_claims']}=={'c1','c2'}
    assert audit['status']=='passed'

def test_review_never_receives_unsupported_mechanism_as_fact():
    stub=Stub(invalid=True);write(None,MATERIAL,stub)
    prompt=next(p for stage,p in stub.calls if stage=='REVIEW_TECHNICAL')
    assert '"claim_limits":' in prompt and '"mechanism": "拒绝过期更新"' not in prompt
    assert '"id": "c1", "statement"' not in prompt

def test_followup_can_read_new_range_of_same_file_without_double_counting():
    class Reader:
        def __init__(self):self.count=0
        def list_tree(self,*args):return {'paths':['lib/memory.ts'],'truncated':False}
        def search_ranges(self,repo,sha,path,terms):
            self.count+=1
            return [SourceEvidence(id='range:'+str(self.count),kind='code',repo=repo,commit_sha=sha,path=path,content_hash='h',excerpt='abc',revision_status='resolved')]
    r=Reader();c=Candidate(**{**candidate(),'source_paths':['lib/memory.ts'],'investigation_questions':['version check']})
    ledger={'paths':set(),'chars':0};evidence={}
    source_investigation(r,{**MATERIAL,'commit':SHA},evidence,[],cards=[c],ledger=ledger)
    c.investigation_questions=['reject stale caller']
    source_investigation(r,{**MATERIAL,'commit':SHA},evidence,[],['lib/memory.ts'],cards=[c],ledger=ledger)
    source_investigation(r,{**MATERIAL,'commit':SHA},evidence,[],['lib/memory.ts'],cards=[c],ledger=ledger)
    assert r.count==2 and len(ledger['paths'])==1 and ledger['chars']==6

def test_combined_feedback_does_not_select_twice_before_rewrite():
    stub=Stub();rounds=0
    def model(prompt):
        nonlocal rounds
        stage=prompt.split('\n',1)[0]
        if stage=='REVIEW_TECHNICAL':
            rounds+=1
            return json.dumps({'approved':rounds>1,'feedback':[] if rounds>1 else [
                {'category':'fact_attribution','issue':'局部核验','claim_ids':['c1'],'part_ids':['b1']},
                {'category':'important_omission','issue':'补另一候选','candidate_ids':['n2']} ]})
        if stage=='CLAIM_VERIFY_FEEDBACK':return json.dumps({'claims':[claim(support='supported')]})
        return stub(prompt)
    _,audit=write(None,MATERIAL,model)
    stages=[r['stage'] for r in audit['harness']['calls']]
    assert stages.count('RESELECT')==1 and 'RESELECT_FACT' not in stages
    assert stages.count('PRODUCT')==1 and audit['status']=='passed'


def test_single_writer_uses_selected_facts_and_distinct_reviews():
    stub=Stub()
    _,audit=write(None,MATERIAL,chat=stub)
    stages=[stage for stage,_ in stub.calls]
    assert stages.index('SELECT')<stages.index('WRITE')<stages.index('REVIEW_HR')
    assert not any(s.startswith('DRAFT_') for s in stages)
    assert stages.count('WRITE')==1
    assert audit['writing_strategy']=='single_writer_distinct_reviews'
    prompts={stage:p for stage,p in stub.calls}
    assert 'perspective_drafts' not in prompts['WRITE']
    assert '你仅从 HR 阅读角度' in prompts['REVIEW_HR']
    assert '你仅从技术面试官角度' in prompts['REVIEW_TECHNICAL']
    assert '"evidence":' not in prompts['REVIEW_HR']
    assert '"evidence":' in prompts['REVIEW_TECHNICAL']
    assert {t['output_structure']['task'] for t in audit['trace'] if t['status']=='prompt_ready'}=={'hr_selection','hr_review','technical_review'}


def test_repair_drops_unlinked_annotations_without_guessing_fact_links():
    stub=Stub()
    def model(prompt):
        stage=prompt.split('\n',1)[0]
        if stage=='DISCOVER_LINK_REPAIR':return json.dumps({'patches':[]})
        if stage=='DISCOVER':
            d=json.loads(stub('DISCOVER\n'))
            card=d['candidates'][0]
            card['mechanism_steps']=[{'text':'已知事实','claim_ids':['c1']},{'text':'不能猜测的越界机制','claim_ids':['wiki:0','c2']}]
            card['problem_claim_ids']=['wiki:0']
            return json.dumps(d)
        return stub(prompt)
    _,audit=write(None,MATERIAL,model)
    card=audit['candidates'][0]
    assert card['mechanism_steps']==[{'text':'已知事实','claim_ids':['c1']}]
    assert card['problem']=='' and card['problem_claim_ids']==[]
    assert any(t['status']=='unlinked_details_removed' for t in audit['trace'])
    assert {c['id'] for c in audit['generated_claims']}=={'c1','c2'}


def test_supported_unknown_state_stops_before_selection_or_empty_writing():
    stub=Stub()
    def model(prompt):
        if prompt.startswith('CLAIM_VERIFY\n'):
            d=json.loads(stub(prompt))
            for c in d['claims']:c['implementation_state']='unknown'
            return json.dumps(d)
        return stub(prompt)
    with pytest.raises(ProviderError) as caught:write(None,MATERIAL,model)
    assert caught.value.code=='resume_no_candidates'
    assert not any(stage.startswith(('DRAFT_','WRITE','REVIEW_','SELECT')) for stage,_ in stub.calls)


def test_optional_source_path_budget_does_not_request_schema_repair():
    stub=Stub()
    def model(prompt):
        if prompt.startswith('DISCOVER\n'):
            d=json.loads(stub(prompt));d['candidates'][0]['source_paths']=['a.ts','b.ts','c.ts','d.ts','e.ts']
            return json.dumps(d)
        return stub(prompt)
    _,audit=write(None,MATERIAL,model)
    assert audit['candidates'][0]['source_paths']==['a.ts','b.ts','c.ts','d.ts']
    assert any(t['status']=='source_paths_budgeted' for t in audit['trace'])
    assert not any(stage=='DISCOVER_SCHEMA_REPAIR' for stage,_ in stub.calls)


def test_project_spine_only_accepts_supported_implemented_upstream():
    from backend.app.resume_quality import project_spine
    rows=[Claim(**claim('ok',support='supported')),Claim(**claim('partial',support='partial')),Claim(**{**claim('unknown',support='supported'),'implementation_state':'unknown'}),Claim(**{**claim('person',support='supported'),'attribution':'user_confirmed','contribution_id':'u'})]
    assert list(project_spine({c.id:c for c in rows}))==['ok']


def test_spine_fact_allowed_in_intro_but_not_unselected_bullet_or_outcome():
    from backend.app.resume_contract import ResumeDraft,check_draft
    claims={i:Claim(**claim(i,support='supported')) for i in ('c1','c2')}
    candidates={'n1':Candidate(**candidate())};choice=Choice(selected_ids=['n1'],reasons={'n1':'相关'})
    draft=ResumeDraft(output_mode='project_reference',project_intro={'text':claims['c2'].statement,'claim_ids':['c2']},bullets=[])
    assert check_draft(draft,claims,candidates,choice,{}, {})==[]
    draft.outcome=draft.project_intro.model_copy()
    assert check_draft(draft,claims,candidates,choice,{}, {})
    draft.outcome=None
    from backend.app.resume_contract import Bullet
    draft.bullets=[Bullet(id='b',title='主题',text=claims['c2'].statement,claim_ids=['c2'],candidate_ids=['n1'])]
    assert '正文claim不属于关联候选' in check_draft(draft,claims,candidates,choice,{}, {})


def test_reference_selector_receives_scope_policy_and_only_eligible_facts():
    stub=Stub(invalid=True);write(None,MATERIAL,stub)
    prompt=next(p for stage,p in stub.calls if stage=='SELECT')
    assert '缺少个人贡献或量化成果不是舍弃理由' in prompt
    assert '"id": "c1"' not in prompt
    assert '"candidate_id": "n1"' not in prompt


def test_mapping_inventory_preserves_tail_and_distinguishes_page_prefixes():
    from backend.app.resume_quality import mapping_inventory
    material={'_full_wiki_pages':[{'title':str(i),'content':'x'} for i in range(12)]}
    mapped={'facts':[{'source_ref':'wiki:11:chunk:0:span:0','mechanism':'尾部异常恢复'}]}
    rows=mapping_inventory(material,mapped)
    assert len(rows)==12 and rows[11]['mechanisms']==['尾部异常恢复']
    assert rows[1]['mapped_fact_count']==0 and rows[1]['status']=='no_mapped_facts'


def test_local_import_hints_resolve_only_existing_safe_paths():
    from backend.app.source_reader import related_source_paths
    tree={'lib/memory.ts','lib/storage/index.ts','outside.ts'}
    text="import { read } from './memory.js'; const store = require('./storage'); import '../../../outside';"
    assert related_source_paths('lib/engine.ts',text,tree)==['lib/memory.ts','lib/storage/index.ts']


def test_source_investigation_follows_one_hop_within_shared_budget(monkeypatch):
    monkeypatch.setenv('RESUME_SOURCE_FILES','6')
    class Reader:
        def __init__(self):self.reads=[]
        def list_tree(self,*args):return {'paths':['lib/engine.ts','lib/state.ts','lib/deeper.ts'],'truncated':False}
        def search_ranges(self,repo,sha,path,terms):
            self.reads.append(path)
            text="import {save} from './state';" if path=='lib/engine.ts' else "import {write} from './deeper';"
            return [SourceEvidence(id=path,kind='code',repo=repo,commit_sha=sha,path=path,content_hash='h',excerpt=text,revision_status='resolved')]
    reader=Reader();ledger={'paths':set(),'chars':0};evidence={}
    card=Candidate(**{**candidate(),'investigation_questions':['engine提交在哪里发生'],'source_paths':['lib/engine.ts']})
    trace=source_investigation(reader,{**MATERIAL,'commit':SHA},evidence,[],cards=[card],ledger=ledger)
    assert reader.reads==['lib/engine.ts','lib/state.ts']
    assert ledger['paths']==set(reader.reads)
    assert any(t['status']=='dependency_hint' for t in trace)


def test_reference_patch_preserves_facts_and_rejects_unknown_targets():
    from backend.app.resume_contract import ReferenceRepair
    from backend.app.resume_quality import apply_reference_patches
    d=Discovery(claims=[Claim(**claim())],candidates=[Candidate(**candidate())])
    patch=ReferenceRepair(patches=[{'target':'claim','target_id':'c1','field':'evidence_ids','refs':['wiki:1']}])
    changed=apply_reference_patches(d,patch)
    assert changed.claims[0].statement==d.claims[0].statement
    assert changed.claims[0].support==d.claims[0].support
    assert d.claims[0].evidence_ids!=changed.claims[0].evidence_ids
    with pytest.raises(ValueError):
        apply_reference_patches(d,ReferenceRepair(patches=[{'target':'claim','target_id':'invented','field':'evidence_ids','refs':['wiki:1']}]))
    with pytest.raises(ValueError):
        ReferenceRepair(patches=[{'target':'claim','target_id':'c1','field':'statement','refs':[]}])


def test_empty_evidence_patch_is_rejected_without_mutating_original():
    from backend.app.resume_contract import ReferenceRepair
    from backend.app.resume_quality import apply_reference_patches
    d=Discovery(claims=[Claim(**claim())],candidates=[Candidate(**candidate())])
    before=d.model_dump()
    with pytest.raises(ValueError,match='未提供有效证据'):
        apply_reference_patches(d,ReferenceRepair(patches=[{'target':'claim','target_id':'c1','field':'evidence_ids','refs':[]}]))
    assert d.model_dump()==before


def test_discovery_unbound_personal_label_does_not_trigger_link_repair():
    stub=Stub()
    def model(prompt):
        if prompt.startswith('DISCOVER\n'):
            d=json.loads(stub(prompt));d['claims'][0]['attribution']='user_confirmed'
            return json.dumps(d)
        return stub(prompt)
    _,audit=write(None,MATERIAL,model)
    assert any(t['stage']=='DISCOVER' and t['status']=='attribution_capped' for t in audit['trace'])
    assert not any(r['stage']=='DISCOVER_LINK_REPAIR' for r in audit['harness']['calls'])


@pytest.mark.parametrize('field,index',[('claim_ids',None),('mechanism_steps',0),('exception_boundaries',0)])
def test_patch_claim_alias_normalizes_without_mutating_input(field,index):
    from backend.app.resume_contract import ReferencePatch
    raw={'target':'candidate','target_id':'n1','field':field,'index':index,'claim_ids':['c1']}
    parsed=ReferencePatch.model_validate(raw)
    assert parsed.refs==['c1'] and 'claim_ids' not in parsed.model_dump()
    assert raw['claim_ids']==['c1'] and 'refs' not in raw
    assert ReferencePatch.model_validate({**raw,'refs':['c1']}).refs==['c1']
    with pytest.raises(ValueError):ReferencePatch.model_validate({**raw,'refs':['c2']})


def test_patch_claim_alias_cannot_be_used_as_evidence_or_ignore_unknown_fields():
    from backend.app.resume_contract import ReferencePatch
    for raw in [
        {'target':'claim','target_id':'c1','field':'evidence_ids','claim_ids':['wiki:0']},
        {'target':'candidate','target_id':'n1','field':'result_refs','claim_ids':['wiki:0']},
        {'target':'candidate','target_id':'n1','field':'claim_ids','claim_ids':['c1'],'invented':True},
    ]:
        with pytest.raises(ValueError):ReferencePatch.model_validate(raw)


def test_discovery_budget_is_separate_from_compact_link_repair(monkeypatch):
    import httpx
    from backend.app.resume_support import WritingModel
    monkeypatch.setenv('RESUME_MODEL_API_KEY','offline-test')
    monkeypatch.delenv('RESUME_DISCOVERY_MAX_TOKENS',raising=False)
    payloads=[]
    def handle(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200,json={'choices':[{'message':{'content':'{}'},'finish_reason':'stop'}]})
    model=WritingModel(transport=httpx.MockTransport(handle))
    try:
        model.request('DISCOVER',stage='DISCOVER')
        model.request('repair',stage='DISCOVER_LINK_REPAIR')
        assert [p['max_tokens'] for p in payloads]==[12000,3500]
    finally:model.close()
