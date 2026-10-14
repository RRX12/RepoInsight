import json,pytest
from backend.app.analysis_contract import Discovery,Candidate,Claim
from backend.app.analysis_revision import discovery_transition,restore_verification_identity
from backend.app.providers import ProviderError
from backend.app.source_reader import SourceReader
def discovery():
    return Discovery(claims=[Claim(id='c',statement='版本检查',evidence_ids=['e'])],
                     candidates=[Candidate(candidate_id='n',title='记忆',claim_ids=['c'])])


def test_new_evidence_can_correct_and_split_without_erasing_history():
    before=discovery()
    after=Discovery(claims=[Claim(id='c2',statement='拒绝旧版本',evidence_ids=['new'],supersedes_claim_id='c')],
                    candidates=[Candidate(candidate_id='n2',title='版本',claim_ids=['c2'],supersedes_candidate_ids=['n']),
                                Candidate(candidate_id='n3',title='权限',claim_ids=['c2'],supersedes_candidate_ids=['n'])])
    record=discovery_transition(before,after,{'new':object()})
    assert record['claim_replacements']=={'c':['c2']}
    assert record['candidate_replacements']=={'n':['n2','n3']}
    assert record['previous']==before.model_dump()
    assert discovery_transition(after,after,{'new':object()})['claim_replacements']=={}


def test_unexplained_deletion_or_in_place_fact_change_rejected():
    before=discovery()
    with pytest.raises(ProviderError):discovery_transition(before,Discovery(claims=[],candidates=[]),{})
    after=before.model_copy(deep=True);after.claims[0].statement='无限制写入'
    with pytest.raises(ProviderError):discovery_transition(before,after,{'e':object()})


def test_stage_cache_depends_on_prompt_model_scope_and_checks_cancellation(tmp_path):
    from backend.app.analysis_harness import Harness
    calls=[]
    h=Harness(lambda _:calls.append('paid'),model='m',cache_dir=tmp_path)
    scope={'workspace':'a','sha':'fixed'}
    key=h.stage_cache_key('template-v1|jd-a|evidence-a',scope)
    result=Discovery(claims=[],candidates=[])
    assert h.read_stage(key,Discovery) is None
    h.save_stages({key:result})
    assert h.read_stage(key,Discovery)==result and calls==[]
    for prompt in ('template-v2|jd-a|evidence-a','template-v1|jd-b|evidence-a','template-v1|jd-a|evidence-b'):
        assert h.read_stage(h.stage_cache_key(prompt,scope),Discovery) is None
    assert h.read_stage(h.stage_cache_key('template-v1|jd-a|evidence-a',{'workspace':'b','sha':'fixed'}),Discovery) is None
    changed=Harness(lambda _:None,model='m2',cache_dir=tmp_path)
    assert changed.read_stage(changed.stage_cache_key('template-v1|jd-a|evidence-a',scope),Discovery) is None
    def cancel():raise ProviderError('cancelled','cancelled')
    h.check_active=cancel
    with pytest.raises(ProviderError):h.read_stage(key,Discovery)


def test_source_search_reaches_late_guards_not_only_type_declarations(tmp_path):
    from backend.app.source_reader import SourceReader,sha256
    repo='example/demo';sha='a'*40;path='src/state.ts'
    text='\n'.join(['type Revision = {baseVersion:string; readVersions:string[]};']*1000+['// padding']*260+[
        'function commit(proposal) {',
        'if (proposal.baseVersion !== latest || !readVersions.includes(latest)) return reject();',
        'if (!visibleEvents.has(proposal.event)) return reject();',
        'return save(proposal);','}'])
    (tmp_path/(sha256(repo+'|'+sha+'|'+path)+'.json')).write_text(json.dumps({'text':text,'hash':sha256(text)}),encoding='utf-8')
    reader=SourceReader('test',cache_dir=tmp_path)
    try:
        rows=reader.search_ranges(repo,sha,path,['baseVersion','readVersions','visibleEvents'])
        assert any('return reject()' in r.excerpt for r in rows)
        assert len(rows)<=3 and reader.calls==0
        assert reader.trace[-1]['unread_matched_lines']
        assert all(r.commit_sha==sha for r in rows)
    finally:reader.close()


def test_explicit_whole_topic_replacement_archives_unmapped_old_claims():
    before=discovery()
    after=Discovery(claims=[Claim(id='new',statement='新证据的原子断言',evidence_ids=['e'])],
        candidates=[Candidate(candidate_id='new-topic',title='纠正后主题',claim_ids=['new'],supersedes_candidate_ids=['n'])])
    transition=discovery_transition(before,after,{'e':object()})
    assert transition['retired_claims'][0]['claim_id']=='c'
    assert transition['claim_replacements']=={}  # No guessed semantic equivalence.


def test_verification_can_omit_identity_but_not_erase_or_invent_evidence():
    from backend.app.analysis_revision import restore_verification_identity
    original=[{'id':'known','statement':'原断言','evidence_ids':['e']}]
    parsed={'claims':[{'id':'known','support':'insufficient'}]}
    assert len(restore_verification_identity(parsed,original))==2
    assert parsed['claims'][0]['evidence_ids']==['e']
    assert parsed['claims'][0]['support']=='insufficient'
    for row in ({'id':'known','statement':'新断言'},{'id':'unknown','statement':'原断言'},{'id':'known','statement':'原断言','evidence_ids':[]}):
        assert restore_verification_identity({'claims':[row]},original)==[]
