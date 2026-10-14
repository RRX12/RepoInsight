"""Neutral project contract and frozen inputs; no resume/editor/report dependency."""
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field

class ValueClaim(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    statement: str=Field(min_length=1,max_length=1200)
    mechanism_chain: list[str]=Field(min_length=1,max_length=8)
    source_refs: list[str]=Field(min_length=1,max_length=8)
    limitations: list[str]=Field(default_factory=list,max_length=8)
    evidence_level: Literal['wiki_documented','wiki_analysis','user_unconfirmed','code_present']

class EngineeringChain(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    name: str
    steps: list[str]=Field(min_length=1,max_length=8)
    source_refs: list[str]=Field(min_length=1,max_length=8)
    limitations: list[str]=Field(default_factory=list,max_length=8)

class ProjectValue(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    audience: str=''
    scenario: str=''
    background: str=''
    value_summary: str=''
    product_flow: list[str]=Field(default_factory=list,max_length=8)
    architecture: list[EngineeringChain]=Field(default_factory=list,max_length=6)
    key_chains: list[EngineeringChain]=Field(default_factory=list,max_length=6)
    claims: list[ValueClaim]=Field(default_factory=list,max_length=5)
    uncertainties: list[str]=Field(default_factory=list,max_length=10)

def validate_product(product,refs):
    for item in product.claims+product.architecture+product.key_chains:
        if any(ref not in refs or refs[ref]!='project_existing' for ref in item.source_refs):
            raise ValueError('产品全貌或架构链路只能引用有效项目材料')
    return product


def collect_project(s,wid):
    from fastapi import HTTPException
    from .db import Workspace,Snapshot,Evidence
    from .memory import require,scoped,latest_jd
    from .analysis_harness import digest
    w=require(s,Workspace,wid);jd=latest_jd(s,wid);snaps=scoped(s,Snapshot,wid)
    if not snaps:raise HTTPException(422,'请先保存仓库链接')
    snap=snaps[-1]
    material={'workspace_id':wid,'snapshot_id':snap.id,'repo':snap.owner+'/'+snap.repo,'commit':snap.commit_sha,'role':w.role,'jd':jd.raw_text if jd else '', 'jd_version_id':jd.id if jd else None,
              'project_corrections':[{'id':e.id,'excerpt':e.excerpt,'source':e.source_ref} for e in scoped(s,Evidence,wid) if e.type=='user_statement' and e.source_ref=='用户确认的项目分析更正' and (e.snapshot_id is None or e.snapshot_id==snap.id)]}
    return snap,material,digest(material)
