"""Deterministic discovery evolution and review reporting, without model/client state."""
from .providers import ProviderError

def restore_verification_identity(parsed, original_claims):
    """Carry forward omitted immutable identity/provenance, never model judgments.

    An explicit empty/changed citation is not omission and is still validated.
    Only the exact known claim ID and unchanged statement may inherit provenance.
    """
    if not isinstance(parsed,dict) or not isinstance(parsed.get('claims'),list):return []
    originals={c['id']:c for c in original_claims};restored=[]
    for claim in parsed['claims']:
        if not isinstance(claim,dict):continue
        base=originals.get(claim.get('id'))
        if not base or claim.get('statement',base['statement'])!=base['statement']:continue
        for field in ('statement','evidence_ids'):
            if field not in claim and field in base:
                claim[field]=base[field]
                restored.append({'claim_id':claim['id'],'field':field,'source':'same_input_claim'})
    return restored

def discovery_transition(previous, updated, evidence):
    old={c.id:c for c in previous.claims};new={c.id:c for c in updated.claims}
    old_cards={c.candidate_id:c for c in previous.candidates};new_cards={c.candidate_id:c for c in updated.candidates}
    if len(new)!=len(updated.claims) or len(new_cards)!=len(updated.candidates):
        raise ProviderError('增量发现ID重复','resume_contract')
    replaced={}
    for claim in updated.claims:
        if claim.id in old and claim.statement!=old[claim.id].statement:
            raise ProviderError('旧事实陈述不能原地修改；使用新ID和替代关联','resume_contract')
        if claim.id in old and claim.supersedes_claim_id!=old[claim.id].supersedes_claim_id:
            raise ProviderError('不能改写事实历史关联','resume_contract')
        if claim.supersedes_claim_id and claim.id not in old:
            if claim.id in old or claim.supersedes_claim_id not in old:
                raise ProviderError('事实替代关联必须指向上一版事实','resume_contract')
            if not claim.evidence_ids or any(e not in evidence for e in claim.evidence_ids):
                raise ProviderError('事实纠正缺少可追溯证据','resume_contract')
            replaced.setdefault(claim.supersedes_claim_id,[]).append(claim.id)
    replacements={};reference_expansions=[];candidate_updates=[]
    for card in updated.candidates:
        # A self-reference is a same-ID card revision, not a semantic replacement.
        if card.candidate_id in old_cards and card.candidate_id in card.supersedes_candidate_ids:
            card.supersedes_candidate_ids=[i for i in card.supersedes_candidate_ids if i!=card.candidate_id]
            candidate_updates.append(card.candidate_id)
        detailed=[i for step in card.mechanism_steps+card.exception_boundaries for i in step.claim_ids]
        detailed+=card.atomic_fact_ids+card.problem_claim_ids+card.contribution_claim_ids+card.result_claim_ids
        # The model already explicitly linked these IDs inside this card. Expand
        # only its redundant index; never guess a source ID or map unknown facts.
        additions=list(dict.fromkeys(i for i in detailed if i in new and i not in card.claim_ids))
        if additions:
            card.claim_ids=list(dict.fromkeys(card.claim_ids+additions))
            reference_expansions.append({'candidate_id':card.candidate_id,'claim_ids':additions})
        if card.candidate_id in old_cards:
            if card.supersedes_candidate_ids!=old_cards[card.candidate_id].supersedes_candidate_ids:
                raise ProviderError('不能改写候选历史关联','resume_contract')
            continue
        for ident in card.supersedes_candidate_ids:
            if ident not in old_cards or card.candidate_id in old_cards:
                raise ProviderError('候选拆分/替代必须使用新ID关联上一版','resume_contract')
            replacements.setdefault(ident,[]).append(card.candidate_id)
    if set(old_cards)-set(new_cards)-set(replacements):
        raise ProviderError('增量发现丢失原候选；需要显式替代关联','resume_contract')
    retired=[]
    for ident in set(old)-set(new)-set(replaced):
        owners={c.candidate_id for c in previous.candidates if ident in c.claim_ids}
        if not owners or not owners<=set(replacements) or any(ident in c.claim_ids for c in updated.candidates):
            raise ProviderError('增量发现丢失原事实；需要显式替代关联','resume_contract')
        # A whole-topic replacement may retire its old claims without pretending
        # to know a one-to-one semantic equivalence. Preserve the full old version.
        retired.append({'claim_id':ident,'former_candidate_ids':sorted(owners),
                        'reason':'候选显式替代，旧断言只进入历史，未认定新旧事实等价'})
    return {'previous':previous.model_dump(),'claim_replacements':replaced,'candidate_replacements':replacements,
            'candidate_updates':candidate_updates,'explicit_reference_expansions':reference_expansions,
            'retired_claims':retired,
            'added_claim_ids':sorted(set(new)-set(old)),'added_candidate_ids':sorted(set(new_cards)-set(old_cards))}

def fact_gate(issues, rejected, reviews, final_model_reviewed):
    """Contract checks do not certify semantic accuracy of an unreviewed revision."""
    failures=list(issues)
    failures.extend('正文已移除不安全内容：'+str(r.get('id',r.get('part',''))) for r in rejected)
    pending=[f for review in reviews for role in review['perspectives'] for f in role['feedback']
             if f['category'] in ('needs_evidence','fact_attribution','mechanism_missing')]
    return {'status':'failed' if failures else 'pending' if pending or not final_model_reviewed else 'passed',
            'issues':failures,'unresolved_feedback':pending,
            'scope':'程序契约及本次模型审查，不代表人工事实认证',
            'final_semantic_reviewed':final_model_reviewed}

SCORE_WEIGHTS={'role_fit':25,'engineering_depth':30,'important_coverage':20,'project_spine':15,'readability':10}

def quality_score(dimensions, independent_benchmark=False):
    """For explicit evaluator/human input only. Never invent ratings from keywords."""
    if set(dimensions)!=set(SCORE_WEIGHTS):raise ValueError('需要五项独立评分')
    for value in dimensions.values():
        if not isinstance(value,dict) or type(value.get('score')) not in (int,float) or not 0<=value['score']<=4 or not value.get('reason'):
            raise ValueError('每项需0–4分及依据')
    score=sum(dimensions[k]['score']*weight/4 for k,weight in SCORE_WEIGHTS.items())
    return {'weighted_score':score,'dimensions':dimensions,'provisional':not independent_benchmark,
            'threshold_met':score>=75 and dimensions['role_fit']['score']>=3 and dimensions['engineering_depth']['score']>=3,
            'fact_gate_independent':True}

def reviewed_score(reviews, final_model_reviewed):
    dimensions={}
    for review in reviews:
        for role in review['perspectives']:
            owned=('role_fit','project_spine','readability') if role['perspective']=='hr' else ('engineering_depth','important_coverage')
            dimensions.update({k:v for k,v in role.get('scores',{}).items() if k in owned})
    if set(dimensions)!=set(SCORE_WEIGHTS):
        return {'status':'not_evaluated','reason':'角色评分不完整，不以通过标志或测试代替分数','dimensions':dimensions}
    return {'status':'provisional_model_review',**quality_score(dimensions),
            'applies_to':'final_draft' if final_model_reviewed else 'first_draft',
            'note':'同源模型自评；缺独立完整性基准和人工校准，不证明质量达标'}


from .resume_contract import Discovery

def discard_unlinked_card_details(discovery):
    """Discard unsupported optional annotations; never guess evidence-to-claim links."""
    changes=[]
    for c in discovery.candidates:
        allowed=set(c.claim_ids)
        for field in ('atomic_fact_ids','problem_claim_ids','contribution_claim_ids','result_claim_ids'):
            refs=getattr(c,field);invalid=[i for i in refs if i not in allowed]
            if invalid:
                setattr(c,field,[i for i in refs if i in allowed])
                if field=='problem_claim_ids':c.problem=''
                changes.append({'candidate_id':c.candidate_id,'field':field,'removed_refs':invalid})
        for field in ('mechanism_steps','exception_boundaries'):
            kept=[]
            for step in getattr(c,field):
                if set(step.claim_ids)<=allowed:kept.append(step)
                else:changes.append({'candidate_id':c.candidate_id,'field':field,'removed_text':step.text,'removed_refs':[i for i in step.claim_ids if i not in allowed]})
            setattr(c,field,kept)
        if any(x['candidate_id']==c.candidate_id for x in changes):
            c.gaps=list(dict.fromkeys(['机制标注引用不匹配，已移除；关键连接仍待补证']+c.gaps))[:5]
    return changes

def apply_reference_patches(discovery,repair):
    """Transactional structural edits: no statement, state or new entity can be changed."""
    updated=discovery.model_copy(deep=True);seen=set();deletions=[]
    for patch in repair.patches:
        key=(patch.target,patch.target_id,patch.field,patch.index)
        if key in seen:raise ValueError('重复关联补丁')
        seen.add(key)
        rows=updated.claims if patch.target=='claim' else updated.candidates
        row=next((r for r in rows if (r.id if patch.target=='claim' else r.candidate_id)==patch.target_id),None)
        if row is None:raise ValueError('关联补丁目标不存在')
        if patch.target=='claim':
            if patch.field!='evidence_ids' or patch.index is not None or patch.drop:raise ValueError('事实补丁只能修改证据引用')
            if not patch.refs:raise ValueError('关联修复未提供有效证据：'+patch.target_id+'；已保留原事实，请核对材料来源')
            row.evidence_ids=patch.refs
        elif patch.field in ('mechanism_steps','exception_boundaries'):
            steps=getattr(row,patch.field)
            if patch.index is None or patch.index>=len(steps):raise ValueError('机制补丁位置不存在')
            if patch.drop:
                if patch.refs:raise ValueError('删除补丁不得附带引用')
                deletions.append((row,patch.field,patch.index))
            else:steps[patch.index].claim_ids=patch.refs
        else:
            if patch.field=='evidence_ids' or patch.index is not None or patch.drop:raise ValueError('候选补丁字段无效')
            setattr(row,patch.field,patch.refs)
    # Indices always refer to the original response, including multiple deletions.
    for row,field,index in sorted(deletions,key=lambda x:x[2],reverse=True):getattr(row,field).pop(index)
    return Discovery.model_validate(updated.model_dump())
