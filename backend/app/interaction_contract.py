"""Public project form contracts; no workflow imports."""
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid')
class Operation(Strict):
    op: Literal['update_jd','update_contribution','create_improvement','edit_improvement','delete_improvement','update_improvement_decision','report_improvement_completed','create_metric','update_metric']
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