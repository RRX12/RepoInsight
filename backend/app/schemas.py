from typing import Literal
from pydantic import BaseModel, Field, ConfigDict
class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
class WorkspaceInput(Strict):
    interest: str = Field(min_length=1, max_length=2000)
    role: str = Field(default='Python 开发', max_length=1000)
    skills: str = Field(default='', max_length=2000)
    time_budget: str = Field(default='', max_length=1000)
    environment: str = Field(default='', max_length=1000)
class TextInput(Strict):
    content: str = Field(min_length=1, max_length=20000)
class EvidenceInput(Strict):
    type: Literal['user_statement','diff','test_report','external_analysis']
    excerpt: str = Field(min_length=1, max_length=200000)
    source_ref: str = Field(default='用户提交', max_length=500)
class Verification(Strict):
    scope: str = ''
    source: str = ''
    limitations: str = ''
class ContributionInput(Strict):
    personal_role: str = Field(default='', max_length=2000)
    problem: str = Field(default='', max_length=4000)
    action: str = Field(min_length=1, max_length=4000)
    tradeoffs: str = Field(default='', max_length=4000)
    outcome: str = Field(default='', max_length=4000)
    state: Literal['proposed','in_progress','implemented','validated','abandoned'] = 'proposed'
    improvement_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list, max_length=50)
    verification: Verification = Field(default_factory=Verification)
class ContributionPatch(ContributionInput):
    expected_version: int = Field(ge=1)
    workspace_id: str
class RunInput(Strict):
    url: str = Field(min_length=1, max_length=300)
    idempotency_key: str = Field(min_length=1, max_length=100)
    demo: bool = True
class ArchitectureRunInput(Strict):
    snapshot_id: str
    idempotency_key: str = Field(min_length=1,max_length=100)
    demo: bool = False
class RepositoryLinkInput(Strict):
    url: str = Field(min_length=1,max_length=300)
class TargetInput(Strict):
    role: str = Field(min_length=1,max_length=1000)
    jd: str = Field(default='',max_length=20000)
class ExperimentInput(Strict):
    contribution_id: str
    baseline_snapshot: str = Field(min_length=1)
    modified_ref: str = Field(min_length=1)
    dataset_description: str = Field(min_length=1)
    conditions: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    baseline_value: float = Field(allow_inf_nan=False)
    modified_value: float = Field(allow_inf_nan=False)
    limitations: str = Field(min_length=1)
    source_evidence_ids: list[str] = Field(min_length=1)
class AttemptInput(Strict):
    contribution_id: str
    approach: str = Field(min_length=1,max_length=4000)
    action: str = Field(min_length=1,max_length=4000)
    result: str = Field(min_length=1,max_length=4000)
    reason: str = Field(min_length=1,max_length=4000)
    evidence_ids: list[str] = Field(default_factory=list,max_length=50)
