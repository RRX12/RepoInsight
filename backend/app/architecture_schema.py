from typing import Literal
from pydantic import Field
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
