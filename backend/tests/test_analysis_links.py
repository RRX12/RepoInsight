from backend.tests.analysis_fixture import claim,candidate
import json,pytest
from backend.app.analysis_contract import Discovery,Candidate,Claim,ReferenceRepair,ReferencePatch
from backend.app.analysis_revision import apply_reference_patches
from backend.app.providers import ProviderError
def test_local_import_hints_resolve_only_existing_safe_paths():
    from backend.app.source_reader import related_source_paths
    tree={'lib/memory.ts','lib/storage/index.ts','outside.ts'}
    text="import { read } from './memory.js'; const store = require('./storage'); import '../../../outside';"
    assert related_source_paths('lib/engine.ts',text,tree)==['lib/memory.ts','lib/storage/index.ts']


def test_reference_patch_preserves_facts_and_rejects_unknown_targets():
    from backend.app.analysis_contract import ReferenceRepair
    from backend.app.analysis_revision import apply_reference_patches
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
    from backend.app.analysis_contract import ReferenceRepair
    from backend.app.analysis_revision import apply_reference_patches
    d=Discovery(claims=[Claim(**claim())],candidates=[Candidate(**candidate())])
    before=d.model_dump()
    with pytest.raises(ValueError,match='未提供有效证据'):
        apply_reference_patches(d,ReferenceRepair(patches=[{'target':'claim','target_id':'c1','field':'evidence_ids','refs':[]}]))
    assert d.model_dump()==before


@pytest.mark.parametrize('field,index',[('claim_ids',None),('mechanism_steps',0),('exception_boundaries',0)])
def test_patch_claim_alias_normalizes_without_mutating_input(field,index):
    from backend.app.analysis_contract import ReferencePatch
    raw={'target':'candidate','target_id':'n1','field':field,'index':index,'claim_ids':['c1']}
    parsed=ReferencePatch.model_validate(raw)
    assert parsed.refs==['c1'] and 'claim_ids' not in parsed.model_dump()
    assert raw['claim_ids']==['c1'] and 'refs' not in raw
    assert ReferencePatch.model_validate({**raw,'refs':['c1']}).refs==['c1']
    with pytest.raises(ValueError):ReferencePatch.model_validate({**raw,'refs':['c2']})


def test_patch_claim_alias_cannot_be_used_as_evidence_or_ignore_unknown_fields():
    from backend.app.analysis_contract import ReferencePatch
    for raw in [
        {'target':'claim','target_id':'c1','field':'evidence_ids','claim_ids':['wiki:0']},
        {'target':'candidate','target_id':'n1','field':'result_refs','claim_ids':['wiki:0']},
        {'target':'candidate','target_id':'n1','field':'claim_ids','claim_ids':['c1'],'invented':True},
    ]:
        with pytest.raises(ValueError):ReferencePatch.model_validate(raw)
