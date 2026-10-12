"""Public interactive editing contracts; no workflow imports."""
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid')
class Operation(Strict):
    op: Literal['update_jd','update_contribution','create_improvement','edit_improvement','delete_improvement','update_improvement_decision','report_improvement_completed','create_metric','update_metric','request_resume_generation','request_resume_review']
    target_id: str | None=None
    data: dict=Field(default_factory=dict)
class Mutation(Strict):
    expected_version: str
    mutation_id: str=Field(min_length=1,max_length=100)
    operations: list[Operation]=Field(min_length=1,max_length=10)
class DiscussionInput(Strict):
    expected_version: str
    mutation_id: str=Field(min_length=1,max_length=100)
    content: str=Field(min_length=1,max_length=20000)
class DiscussionResult(Strict):
    known_facts: str=''
    advice_and_tradeoffs: str=''
    missing_information: str=''
    clarification: str=''
    intent: Literal['discussion','explicit_update','ambiguous','hypothetical']='discussion'
    operations: list[Operation]=Field(default_factory=list,max_length=10)
class ImprovementData(Strict):
    title: str=Field(min_length=1,max_length=300)
    problem: str=''
    proposal: str=''
    alternatives: list[str]=Field(default_factory=list,max_length=5)
    recommendation: Literal['recommend','conditional','not_recommended','insufficient_context']='insufficient_context'
    reason: str=''
    risks: str=''
    validation: str=''
    evidence_ids: list[str]=Field(default_factory=list,max_length=20)
    finding_ids: list[str]=Field(default_factory=list,max_length=20)
    supersedes_id: str | None=None
class MetricData(Strict):
    name: str=Field(min_length=1,max_length=200)
    value: float=Field(allow_inf_nan=False)
    unit: str=Field(max_length=80)
    change_type: Literal['relative_decrease','absolute_decrease','final_value','unspecified']='unspecified'
    baseline: float | None=Field(default=None,allow_inf_nan=False)
    sample_size: str=''
    method: str=''
    improvement_id: str | None=None
    contribution_id: str | None=None
class EditInput(Strict):
    expected_version: str
    mutation_id: str=Field(min_length=1,max_length=100)
    content: str=Field(max_length=20000)
    output_mode: Literal['project_reference','personal_resume']='project_reference'
    restore_id: str | None=None
class ReviewInput(Strict):
    expected_version: str
    mutation_id: str=Field(min_length=1,max_length=100)
    content: str=Field(max_length=20000)
    output_mode: Literal['project_reference','personal_resume']='project_reference'
class ReviewIssue(Strict):
    category: Literal['expression','relevance_or_duplicate','fact_metric_attribution']
    issue: str
class ReviewResult(Strict):
    suggested_text: str=Field(max_length=20000)
    issues: list[ReviewIssue]=Field(default_factory=list,max_length=12)
    sync_candidates: list[Operation]=Field(default_factory=list,max_length=8)
class DecisionInput(Strict):
    expected_version: str
    mutation_id: str=Field(min_length=1,max_length=100)
    proposal_id: str
    accept: bool

class GenerateInput(Strict):
    expected_version: str
    mutation_id: str=Field(min_length=1,max_length=100)
    output_mode: Literal['project_reference','personal_resume']='project_reference'
    writing_mode: Literal['model','reference']='model'
