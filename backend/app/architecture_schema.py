from typing import Literal
from pydantic import Field,ConfigDict
from .schemas import Strict

class Module(Strict):
    name: str = Field(min_length=1,max_length=300)
    responsibility: str = Field(min_length=1,max_length=5000)
    paths: list[str] = Field(default_factory=list,max_length=30)
class Flow(Strict):
    name: str = Field(min_length=1,max_length=300)
    description: str = Field(min_length=1,max_length=5000)
    paths: list[str] = Field(default_factory=list,max_length=30)
class Overview(Strict):
    summary: str = Field(min_length=1,max_length=10000)
    current_architecture: str = Field(min_length=1,max_length=10000)
    modules: list[Module] = Field(min_length=1,max_length=40)
    core_flows: list[Flow] = Field(min_length=1,max_length=15)
    existing_capabilities: list[Module] = Field(default_factory=list,max_length=30)
    coverage_notes: list[str] = Field(min_length=1,max_length=30)
class Direction(Strict):
    title: str = Field(min_length=1,max_length=300)
    scope: Literal['architecture']
    direction: str = Field(min_length=1,max_length=500)
    necessity: Literal['recommended','conditional','not_recommended']
    business_problem: str = Field(min_length=1,max_length=5000)
    current_design: str = Field(min_length=1,max_length=5000)
    why_now: str = Field(min_length=1,max_length=5000)
    proposal: str = Field(min_length=1,max_length=5000)
    affected_modules: list[str] = Field(min_length=1,max_length=15)
    source_paths: list[str] = Field(min_length=1,max_length=30)
    existing_solution_checked: str = Field(min_length=1,max_length=5000)
    alternatives: str = Field(min_length=1,max_length=5000)
    tradeoffs: str = Field(min_length=1,max_length=5000)
    validation_plan: str = Field(min_length=1,max_length=5000)
    jd_relation: str = Field(min_length=1,max_length=5000)
    assumptions: list[str] = Field(default_factory=list,max_length=20)
class JDAssessment(Strict):
    requirement: str = Field(min_length=1,max_length=500)
    current_fit: str = Field(min_length=1,max_length=4000)
    recommendation: Literal['use_existing','consider_change','not_needed','insufficient_evidence']
    reason: str = Field(min_length=1,max_length=5000)
class ArchitectureReport(Strict):
    overview: Overview
    directions: list[Direction] = Field(default_factory=list,max_length=3)
    jd_assessment: list[JDAssessment] = Field(default_factory=list,max_length=20)
    no_change_reason: str = Field(default='',max_length=5000)

def validate_paths(report, available):
    paths=[]
    for m in report.overview.modules+report.overview.existing_capabilities: paths+=m.paths
    for f in report.overview.core_flows: paths+=f.paths
    for d in report.directions: paths+=d.source_paths
    unknown=set(paths)-set(available)
    if unknown: raise ValueError('分析引用了未读取路径：'+', '.join(sorted(unknown)[:10]))
    if not report.directions and not report.no_change_reason:
        raise ValueError('没有建议时需解释为何维持现状')
    return report

# History retains ArchitectureReport; V2 is a separately versioned contract.
Kind = Literal['engineering_fix','capability_deepening','feature_extension']
Decision = Literal['prioritize','conditional','validate_first','not_recommended']
class SourceStatement(Strict):
    statement: str
    source_refs: list[str] = Field(default_factory=list,max_length=30)
class ResearchAction(Strict):
    candidate_id: str
    question_id: str
    purpose: str
    action_type: Literal['code_search','code_read','web_search','web_read']
    query: str = Field(default='',max_length=300)
    path: str = ''
    start_line: int|None = Field(default=None,ge=1)
    end_line: int|None = Field(default=None,ge=1)
    url: str = ''
class Candidate(Strict):
    candidate_id: str
    title: str
    kind: Kind
    current_state: SourceStatement
    opportunity: str
    jd_links: list[str] = Field(default_factory=list,max_length=6)
    expected_value: str
    preliminary_decision: Decision
    decision_reason: str
    assumptions: list[str] = Field(default_factory=list,max_length=12)
    investigation_questions: list[str] = Field(default_factory=list,max_length=6)
    research_actions: list[ResearchAction] = Field(default_factory=list,max_length=8)
class OptimizationDiscovery(Strict):
    candidates: list[Candidate] = Field(default_factory=list,max_length=6)
    no_change_reason: str = ''
    coverage_notes: list[str] = Field(default_factory=list,max_length=20)
class ResearchSource(Strict):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=False)
    source_id: str
    kind: Literal['repository_code','repository_doc','test_source','external_source']
    locator: str
    path: str|None = None
    start_line: int|None = None
    end_line: int|None = None
    excerpt: str
    content_hash: str
    retrieved_at: str
    source_version: str|None = None
    read_status: Literal['read','partial','snippet_only'] = 'read'
class CandidateAssessment(Strict):
    candidate_id: str
    title: str
    kind: Kind
    decision: Decision
    project_value: str
    jd_relation: str
    fit: str
    effort: str
    verifiability: str
    evidence_sufficiency: Literal['sufficient','partial','insufficient']
    rationale: str
    source_refs: list[str] = Field(default_factory=list,max_length=30)
    assumptions: list[str] = Field(default_factory=list,max_length=20)
    merged_into: str|None = None
class ReferencePractice(Strict):
    mechanism: str
    applicability: str
    limitations: str
    source_refs: list[str] = Field(min_length=1,max_length=10)
class TechnicalOption(Strict):
    name: str
    mechanism: str
    prerequisites: str
    benefits_expected: str
    costs: str
    tradeoffs: str
    source_refs: list[str] = Field(default_factory=list,max_length=10)
class RecommendedDesign(Strict):
    chosen_option: str
    rationale: str
    components: list[str]
    execution_steps: list[str]
    failure_handling: str
class CodeChange(Strict):
    change_type: Literal['modify','add']
    path: str
    symbol: str|None = None
    responsibility: str
    change_description: str
    source_refs: list[str] = Field(default_factory=list,max_length=10)
class ImplementationStep(Strict):
    step_id: str
    action: str
    dependencies: list[str] = Field(default_factory=list)
    deliverable: str
class ValidationStep(Strict):
    scenario: str
    baseline: str
    method: str
    metric_or_acceptance: str
    measurement_status: Literal['not_measured','user_reported','measured'] = 'not_measured'
class DetailedDirection(Strict):
    candidate_id: str
    title: str
    kind: Kind
    current_design: SourceStatement
    goal: str
    scenario: str
    why_now: str
    jd_relation: str
    reference_practices: list[ReferencePractice] = Field(default_factory=list,max_length=6)
    technical_options: list[TechnicalOption] = Field(min_length=1,max_length=3)
    recommended_design: RecommendedDesign
    code_changes: list[CodeChange] = Field(default_factory=list,max_length=15)
    implementation_steps: list[ImplementationStep] = Field(min_length=1,max_length=10)
    validation_plan: list[ValidationStep] = Field(min_length=1,max_length=8)
    assumptions: list[str] = Field(default_factory=list,max_length=20)
class ValidationAction(Strict):
    candidate_id: str
    experiment: str
    decision_condition: str
class RoadmapItem(Strict):
    candidate_id: str
    dependencies: list[str] = Field(default_factory=list)
    order: int = Field(ge=1)
    reason: str
class OptimizationReportV2(Strict):
    schema_version: Literal['optimization-v2'] = 'optimization-v2'
    overview: Overview
    candidate_assessments: list[CandidateAssessment] = Field(default_factory=list,max_length=6)
    directions: list[DetailedDirection] = Field(default_factory=list,max_length=3)
    validation_actions: list[ValidationAction] = Field(default_factory=list,max_length=6)
    roadmap: list[RoadmapItem] = Field(default_factory=list,max_length=6)
    sources: list[ResearchSource] = Field(default_factory=list,max_length=80)
    coverage: dict = Field(default_factory=dict)
    unresolved_questions: list[str] = Field(default_factory=list,max_length=30)
    follow_up_requests: list[ResearchAction] = Field(default_factory=list,max_length=6)
    no_change_reason: str = ''

def legacy_direction(direction, report):
    if report.get('schema_version')!='optimization-v2':return direction
    import json
    d=direction;a=next(a for a in report['candidate_assessments'] if a['candidate_id']==d['candidate_id'])
    refs=set(d['current_design']['source_refs']+[r for c in d['code_changes'] for r in c['source_refs']])
    paths=sorted({s['path'] for s in report['sources'] if s.get('path') and s['source_id'] in refs})
    return {**d,'schema_version':'optimization-v2','v2_plan':d,'scope':'architecture','direction':d['goal'],
        'necessity':{'prioritize':'recommended','conditional':'conditional','validate_first':'conditional','not_recommended':'not_recommended'}[a['decision']],
        'business_problem':d['scenario'],'current_design':d['current_design']['statement'],
        'proposal':d['recommended_design']['rationale'],'source_paths':paths,
        'alternatives':json.dumps(d['technical_options'],ensure_ascii=False),'tradeoffs':'; '.join(o['tradeoffs'] for o in d['technical_options']),
        'validation_plan':json.dumps(d['validation_plan'],ensure_ascii=False),'source_summary':[s for s in report['sources'] if s['source_id'] in refs]}
