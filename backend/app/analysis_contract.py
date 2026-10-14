"""Versioned project facts and investigation contracts."""
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .source_reader import SourceEvidence

VERSION='project-analysis-v1'
class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class GenerationContext(Strict):
    workspace_id: str
    snapshot_id: str
    commit_sha: str
    revision_status: str
    role: str
    jd_version_id: str | None
    target_origin: Literal['jd','role_inferred']
    material_fingerprint: str
    prompt_version: str=VERSION
    schema_version: str=VERSION
    model: str='configured'
    target_dimensions: list[str]=Field(default_factory=list,max_length=6)
class Requirement(Strict):
    requirement_id: str
    description: str
    priority: Literal['high','medium','low']='medium'
    origin: Literal['jd','role_inferred']
    question: str
    search_terms: list[str]=Field(min_length=1,max_length=12)
    jd_source_ids: list[str]=Field(default_factory=list,max_length=6)
    original_excerpt: str=''
    priority_basis: Literal['jd_explicit','model_judgment']='model_judgment'
    queries: list[str]=Field(default_factory=list,max_length=2)
class Investigation(Strict):requirements:list[Requirement]=Field(min_length=1,max_length=6)
class Coverage(Strict):
    requirement_id: str
    status: Literal['direct','partial','unknown','not_applicable']
    claim_ids: list[str]=Field(default_factory=list)
    candidate_ids: list[str]=Field(default_factory=list)
    gaps: list[str]=Field(default_factory=list)
    next_query: str=''
    reason: str=''
class Claim(Strict):
    id: str
    statement: str=Field(min_length=1,max_length=1200)
    evidence_ids: list[str]=Field(min_length=1,max_length=8)
    support: Literal['supported','partial','insufficient','contradicted']='insufficient'
    implementation_state: Literal['proposed','in_progress','implemented','unknown']='unknown'
    attribution: Literal['upstream','user_confirmed','user_evidenced','unknown']='unknown'
    validation_level: Literal['code_present','integrated','test_defined','test_passed','runtime_measured','unknown']='unknown'
    contribution_id: str | None=None
    integration_evidence_ids:list[str]=Field(default_factory=list,max_length=6)
    integration_basis:str=Field(default='',max_length=700)
    scope: str=''
    limitations: list[str]=Field(default_factory=list,max_length=8)
    reason: str=''
    supersedes_claim_id: str | None=None
class MechanismFact(Strict):
    text: str=Field(min_length=1,max_length=500)
    claim_ids: list[str]=Field(min_length=1,max_length=8)
class Candidate(Strict):
    @model_validator(mode='before')
    @classmethod
    def retain_unlinked_details_as_gaps(cls,value):
        # Optional prose without references is a question, never a verified fact.
        if not isinstance(value,dict):return value
        result=dict(value);gaps=list(value.get('gaps',[])) if isinstance(value.get('gaps',[]),list) else None
        if gaps is None:return value
        for field in ('mechanism_steps','exception_boundaries'):
            rows=value.get(field,[])
            if not isinstance(rows,list):continue
            kept=[]
            for row in rows:
                if isinstance(row,dict) and set(row)=={'text','claim_ids'} and row['claim_ids']==[] and isinstance(row['text'],str) and 0<len(row['text'])<=500:
                    gap='待补证（'+field+'，缺少事实引用）：'+row['text']
                    if gap not in gaps:gaps.append(gap)
                else:kept.append(row)
            result[field]=kept
        result['gaps']=gaps
        return result
    candidate_id: str
    title: str
    problem: str=''
    mechanism: str=''
    tradeoff: str=''
    claim_ids: list[str]=Field(min_length=1,max_length=32)
    requirement_ids: list[str]=Field(default_factory=list,max_length=6)
    personal_contribution: str=''
    result_refs: list[str]=Field(default_factory=list)
    gaps: list[str]=Field(default_factory=list,max_length=5)
    reason: str=''
    atomic_fact_ids: list[str]=Field(default_factory=list,max_length=8)
    problem_claim_ids: list[str]=Field(default_factory=list,max_length=8)
    mechanism_steps: list[MechanismFact]=Field(default_factory=list,max_length=6)
    exception_boundaries: list[MechanismFact]=Field(default_factory=list,max_length=6)
    investigation_questions: list[str]=Field(default_factory=list,max_length=3)
    source_paths: list[str]=Field(default_factory=list,max_length=4)
    contribution_claim_ids: list[str]=Field(default_factory=list,max_length=8)
    result_claim_ids: list[str]=Field(default_factory=list,max_length=8)
    supersedes_candidate_ids: list[str]=Field(default_factory=list,max_length=4)
class Discovery(Strict):
    project_intro: str=''
    claims: list[Claim]=Field(max_length=32)
    candidates: list[Candidate]=Field(max_length=10)
class NextRead(Strict):
    path:str
    terms:list[str]=Field(default_factory=list,max_length=5)
    reason:str
class Analysis(Discovery):
    next_reads:list[NextRead]=Field(default_factory=list,max_length=4)
    confirmed_flow:list[str]=Field(default_factory=list,max_length=8)
    unresolved_questions:list[str]=Field(default_factory=list,max_length=8)

class ReferencePatch(Strict):
    target: Literal['claim','candidate']
    target_id: str
    field: Literal['evidence_ids','claim_ids','requirement_ids','result_refs','atomic_fact_ids','problem_claim_ids','contribution_claim_ids','result_claim_ids','mechanism_steps','exception_boundaries']
    refs: list[str]=Field(default_factory=list,max_length=8)
    index: int | None=Field(default=None,ge=0,le=5)
    drop: bool=False
    @model_validator(mode='before')
    @classmethod
    def normalize_claim_refs(cls,value):
        if not isinstance(value,dict) or 'claim_ids' not in value:return value
        if value.get('target')!='candidate' or value.get('field') not in ('claim_ids','atomic_fact_ids','problem_claim_ids','contribution_claim_ids','result_claim_ids','mechanism_steps','exception_boundaries'):
            raise ValueError('claim_ids别名仅适用于候选事实引用补丁')
        if 'refs' in value and value['refs']!=value['claim_ids']:
            raise ValueError('补丁refs与claim_ids冲突')
        normalized=dict(value)
        normalized['refs']=normalized.pop('claim_ids')
        return normalized

class ReferenceRepair(Strict):
    patches: list[ReferencePatch]=Field(default_factory=list,max_length=32)

class Verification(Strict):claims:list[Claim]=Field(max_length=32)
class Feedback(Strict):
    category: Literal['expression','needs_evidence','important_omission','candidate_omission','mechanism_missing','fact_attribution','contribution_gap']
    issue: str
    candidate_ids: list[str]=Field(default_factory=list,max_length=3)
    claim_ids: list[str]=Field(default_factory=list,max_length=8)
    paths: list[str]=Field(default_factory=list,max_length=4)
    part_ids: list[str]=Field(default_factory=list,max_length=6)
    blocking: bool=False
    evidence_ids: list[str]=Field(default_factory=list,max_length=8)
    jd_requirement_ids: list[str]=Field(default_factory=list,max_length=6)
    suggested_action: str=''
    priority: Literal['high','medium','low']='medium'
    interview_question: str=''
def check_claims(claims,evidence,context,contributions):
    ids=[c.id for c in claims]
    if len(set(ids))!=len(ids):raise ValueError('claim ID重复')
    for c in claims:
        if any(e not in evidence for e in c.evidence_ids):raise ValueError('claim '+c.id+'引用未知证据：'+','.join(e for e in c.evidence_ids if e not in evidence))
        sources=[evidence[e] for e in c.evidence_ids]
        code=[e for e in sources if e.kind in ('code','test_source')]
        if any(e.commit_sha!=context.commit_sha for e in sources if e.kind in ('code','test_source','documentation')):raise ValueError('claim引用旧版本源码')
        if c.attribution=='upstream' and c.contribution_id:raise ValueError('上游不能绑定个人贡献')
        if c.attribution in ('user_confirmed','user_evidenced'):
            person=contributions.get(c.contribution_id)
            if not person or person['state'] not in ('implemented','validated') or any(t in person['action'] for t in ('未实现','没实现','尚未完成','只是讨论')):raise ValueError('个人已完成claim必须绑定当前确认贡献')
            if not any(e.id=='optimization:'+person['id'] for e in sources):raise ValueError('个人claim缺当前贡献证据')
            if c.attribution=='user_evidenced' and not any(e.id.removeprefix('user-material:') in person['evidence_ids'] and e.kind in ('diff','test_report') for e in sources):raise ValueError('个人claim缺独立佐证')
        if c.validation_level in ('test_passed','runtime_measured') and not any(e.kind=='experiment' for e in sources):raise ValueError('没有实验不能宣称通过测试或运行效果')
        if c.validation_level=='test_defined' and not any(e.kind=='test_source' for e in sources):raise ValueError('没有测试源码')
        if c.validation_level=='integrated':
            if not c.integration_basis.strip() or not c.integration_evidence_ids or not set(c.integration_evidence_ids)<=set(c.evidence_ids):raise ValueError('集成判断缺入口/调用/配置证据关联')
            if not all(evidence[i].kind=='code' for i in c.integration_evidence_ids):raise ValueError('测试或文档不能证明生产集成')
        if c.validation_level in ('code_present','integrated') and not code:raise ValueError('claim '+c.id+'标记为'+c.validation_level+'，但引用证据仅含 '+','.join(sorted({e.kind for e in sources}))+'；文档/Wiki不能作为源码核验，需引用真实代码证据或将validation_level改为unknown')
        if c.support=='supported' and all(e.kind=='wiki' for e in sources):
            c.validation_level='unknown'
            c.limitations=list(dict.fromkeys(c.limitations+['仅Wiki描述，未核验当前源码']))
    return claims

def validate_discovery(discovery,evidence,requirements,context,contributions,*,verified=True):
    if verified:check_claims(discovery.claims,evidence,context,contributions)
    else:
        # Before the independent verifier, labels are proposals, not accepted facts.
        if len({c.id for c in discovery.claims})!=len(discovery.claims):raise ValueError('claim ID重复')
        for c in discovery.claims:
            if not set(c.evidence_ids)<=set(evidence):raise ValueError('claim '+c.id+'引用未知证据')
            if any(evidence[i].kind in ('code','test_source','documentation') and evidence[i].commit_sha!=context.commit_sha for i in c.evidence_ids):raise ValueError('claim引用旧版本源码')
    cs={c.id for c in discovery.claims};rs={r.requirement_id for r in requirements}
    ids=[c.candidate_id for c in discovery.candidates]
    if len(set(ids))!=len(ids):raise ValueError('候选ID重复')
    for c in discovery.candidates:
        if not set(c.claim_ids)<=cs or not set(c.requirement_ids)<=rs:raise ValueError('候选引用未知claim/职责')
        refs=set(c.atomic_fact_ids+c.problem_claim_ids+c.contribution_claim_ids+c.result_claim_ids)
        refs.update(i for step in c.mechanism_steps+c.exception_boundaries for i in step.claim_ids)
        if not refs<=set(c.claim_ids):raise ValueError('候选 '+c.candidate_id+'机制卡片事实引用不属于候选claim：'+','.join(sorted(refs-set(c.claim_ids))))
        if any(i not in evidence for i in c.result_refs):raise ValueError('候选结果来源不存在')
    return discovery
