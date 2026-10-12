"""Versioned facts and structured prose contracts, separate from writing provider."""
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .source_reader import SourceEvidence

VERSION='resume-quality-v5'
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
    output_mode: Literal['project_reference','personal_resume']='project_reference'
    target_dimensions: list[str]=Field(default_factory=list,max_length=6)
class Requirement(Strict):
    requirement_id: str
    description: str
    priority: Literal['high','medium','low']='medium'
    origin: Literal['jd','role_inferred']
    question: str
    search_terms: list[str]=Field(min_length=1,max_length=12)
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
    scope: str=''
    limitations: list[str]=Field(default_factory=list,max_length=8)
    reason: str=''
    supersedes_claim_id: str | None=None
class MechanismFact(Strict):
    text: str=Field(min_length=1,max_length=500)
    claim_ids: list[str]=Field(min_length=1,max_length=8)
class Candidate(Strict):
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
class Choice(Strict):
    selected_ids: list[str]=Field(max_length=4)
    reasons: dict[str,str]
    omitted: dict[str,str]=Field(default_factory=dict)
    coverage: list[Coverage]=Field(default_factory=list,max_length=6)
    outline: list[str]=Field(default_factory=list,max_length=6)
class Metric(Strict):
    id: str
    name: str
    value: float
    unit: str
    baseline: float | None=None
    sample_scope: str
    environment: str
    measurement_method: str
    change_type: str="unspecified"
    state: Literal['user_reported','measured','proposed']='user_reported'
    experiment_id: str | None=None
    user_statement_id: str | None=None
    contribution_id: str | None=None
class Prose(Strict):
    text: str=Field(max_length=1600)
    claim_ids: list[str]=Field(default_factory=list,max_length=12)
    metric_ids: list[str]=Field(default_factory=list,max_length=4)
    contribution_ids: list[str]=Field(default_factory=list,max_length=8)
class Bullet(Prose):
    id: str
    title: str
    candidate_ids: list[str]=Field(min_length=1,max_length=4)
class ResumeDraft(Strict):
    output_mode: Literal['project_reference','personal_resume']
    project_intro: Prose
    bullets: list[Bullet]=Field(max_length=4)
    outcome: Prose | None=None
    questions: list[str]=Field(default_factory=list,max_length=3)
    limitations: list[str]=Field(default_factory=list,max_length=8)
class Feedback(Strict):
    category: Literal['expression','needs_evidence','important_omission','candidate_omission','mechanism_missing','fact_attribution']
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
class Rating(Strict):
    score: float=Field(ge=0,le=4)
    reason: str=Field(min_length=1,max_length=600)
    part_ids: list[str]=Field(default_factory=list,max_length=6)
    suggested_action: str=''
class QualityReview(Strict):
    approved: bool
    feedback: list[Feedback]=Field(default_factory=list,max_length=8)
    scores: dict[Literal['role_fit','engineering_depth','important_coverage','project_spine','readability'],Rating]=Field(default_factory=dict)

def check_claims(claims,evidence,context,contributions):
    ids=[c.id for c in claims]
    if len(set(ids))!=len(ids):raise ValueError('claim ID重复')
    for c in claims:
        if any(e not in evidence for e in c.evidence_ids):raise ValueError('claim '+c.id+'引用未知证据：'+','.join(e for e in c.evidence_ids if e not in evidence))
        sources=[evidence[e] for e in c.evidence_ids]
        code=[e for e in sources if e.kind in ('code','test_source')]
        if any(e.commit_sha!=context.commit_sha for e in code):raise ValueError('claim引用旧版本源码')
        if c.attribution=='upstream' and c.contribution_id:raise ValueError('上游不能绑定个人贡献')
        if c.attribution in ('user_confirmed','user_evidenced'):
            person=contributions.get(c.contribution_id)
            if not person or person['state'] not in ('implemented','validated') or any(t in person['action'] for t in ('未实现','没实现','尚未完成','只是讨论')):raise ValueError('个人已完成claim必须绑定当前确认贡献')
            if not any(e.id=='optimization:'+person['id'] for e in sources):raise ValueError('个人claim缺当前贡献证据')
            if c.attribution=='user_evidenced' and not any(e.id.removeprefix('user-material:') in person['evidence_ids'] and e.kind in ('diff','test_report') for e in sources):raise ValueError('个人claim缺独立佐证')
        if c.validation_level in ('test_passed','runtime_measured') and not any(e.kind=='experiment' for e in sources):raise ValueError('没有实验不能宣称通过测试或运行效果')
        if c.validation_level=='test_defined' and not any(e.kind=='test_source' for e in sources):raise ValueError('没有测试源码')
        if c.validation_level in ('code_present','integrated') and not code:raise ValueError('Wiki不能标成源码核验')
        if c.support=='supported' and all(e.kind=='wiki' for e in sources):
            c.validation_level='unknown'
            c.limitations=list(dict.fromkeys(c.limitations+['仅Wiki描述，未核验当前源码']))
    return claims

def check_draft(draft,claims,candidates,choice,metrics,contributions):
    issues=[];selected=set(choice.selected_ids)
    if len({b.id for b in draft.bullets})!=len(draft.bullets):issues.append('正文条目ID重复')
    used=[]
    for part in [draft.project_intro,*draft.bullets,*([draft.outcome] if draft.outcome else [])]:
        if not part.text.strip():continue
        if not part.claim_ids or any(i not in claims for i in part.claim_ids):issues.append('正文缺claim映射');continue
        linked=[claims[i] for i in part.claim_ids]
        selected_facts={i for cid in selected if cid in candidates for i in candidates[cid].claim_ids}
        if part is not draft.project_intro and any(i not in selected_facts for i in part.claim_ids):issues.append('项目主线事实仅可用于简介，成果和亮点须来自已选主题')
        if re.search(r'本人|我独立|独立设计|主导实现|主导设计',part.text) and not any(c.attribution in ('user_confirmed','user_evidenced') and c.contribution_id in part.contribution_ids for c in linked):issues.append('个人归属词没有确认贡献支持')
        if any(c.support!='supported' or c.implementation_state in ('proposed','in_progress','unknown') for c in linked):issues.append('正文引用未充分支持或未完成claim')
        if any(i not in contributions or contributions[i]['state'] not in ('implemented','validated') for i in part.contribution_ids):issues.append('正文引用失效个人贡献')
        if draft.output_mode=='personal_resume' and isinstance(part,Bullet) and not any(c.attribution in ('user_confirmed','user_evidenced') and c.contribution_id in part.contribution_ids for c in linked):issues.append('个人亮点缺确认贡献')
        if isinstance(part,Bullet):
            used.extend(part.candidate_ids)
            if any(i not in selected for i in part.candidate_ids):issues.append('正文新增未选候选')
            allowed={i for cid in part.candidate_ids if cid in candidates for i in candidates[cid].claim_ids}
            if any(i not in allowed for i in part.claim_ids):issues.append('正文claim不属于关联候选')
        # Numeric meaning is constrained to linked claims/metrics, not global material/JD.
        text_numbers=set(re.findall(r'\d+(?:\.\d+)?',part.text))
        claim_numbers=set(re.findall(r'\d+(?:\.\d+)?',' '.join(c.statement for c in linked)))
        if text_numbers-claim_numbers and not part.metric_ids:issues.append('正文数字不在所引用claim中')
        if re.search(r'\d+(?:\.\d+)?\s*(?:%|％|倍|ms|秒|分钟|QPS)',part.text) and not part.metric_ids:issues.append('效果指标缺独立Metric')
        if part.metric_ids:
            bound_numbers=claim_numbers|{format(v,'g') for mid in part.metric_ids if mid in metrics for v in (metrics[mid].value,metrics[mid].baseline) if v is not None}
            for mid in part.metric_ids:
                if mid in metrics:bound_numbers.update(re.findall(r'\d+(?:\.\d+)?',metrics[mid].sample_scope+' '+metrics[mid].environment))
            if text_numbers-bound_numbers:issues.append('正文数字超出绑定指标口径')
        for mid in part.metric_ids:
            m=metrics.get(mid)
            if not m or m.state=='proposed' or m.contribution_id not in part.contribution_ids:issues.append('指标来源或状态不允许');continue
            if m.name not in part.text or m.unit not in part.text or format(m.value,'g') not in part.text:issues.append('指标名称/值/单位不匹配')
            if m.sample_scope not in part.text or m.environment not in part.text or '用户' not in part.text:issues.append('指标缺样本/环境/用户来源说明')
        if re.search(r'计划|拟采用|尚未|待验证|未确认',part.text):issues.append('计划与待核实说明应在正文外')
    if len(used)!=len(set(used)):issues.append('重复候选导致内容重复')
    if len(render(draft))>1800:issues.append('正文超过1800字符')
    return list(dict.fromkeys(issues))

def render(draft):
    lines=['**项目简介：** '+draft.project_intro.text]
    if draft.bullets:
        lines+=['## 技术亮点']+[f'- **{b.title}**：{b.text}' for b in draft.bullets]
    if draft.outcome and draft.outcome.text.strip():lines+=['**项目成果：** '+draft.outcome.text]
    return '\n\n'.join(lines)
