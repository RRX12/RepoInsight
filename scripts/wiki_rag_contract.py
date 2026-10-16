"""Wiki-only data contracts and frozen settings. No task orchestration imports."""
import os
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator

FLOW_VERSION='wiki-rag-v1'
class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class Budgets(Strict):
    model_calls:int=Field(default=6,ge=1,le=6)
    rounds:int=Field(default=2,ge=0,le=2)
    tools:int=Field(default=20,ge=1,le=100)
    semantic:int=Field(default=6,ge=0,le=24)
    files:int=Field(default=8,ge=1,le=32)
    evidence:int=Field(default=12000,ge=1,le=48000)
    initial_evidence:int=Field(default=8000,ge=1,le=32000)
    input:int=Field(default=18000,ge=1,le=72000)
    output:int=Field(default=4000,ge=1,le=16000)
    page_limit:int=Field(default=12,ge=1,le=12)
    task_models:int=Field(default=72,ge=1,le=288)
    task_semantic:int=Field(default=72,ge=0,le=288)
    structure_models:int=Field(default=2,ge=1,le=2)
    max_new_vectors:int=Field(default=0,ge=0,le=10000)
    index_mode:Literal['reuse_only','auto']='reuse_only'
    auto_vector_limit:int=Field(default=10000,ge=1,le=100000)
    index_concurrency:int=Field(default=2,ge=1,le=8)
    index_batch_size:int=Field(default=32,ge=1,le=128)
    index_timeout:int=Field(default=7200,ge=60,le=86400)
    chunk_target:int=Field(default=600,ge=1,le=4000)
    chunk_max:int=Field(default=1200,ge=1,le=8000)
    chunk_overlap:int=Field(default=80,ge=0,le=1000)
    @model_validator(mode='after')
    def coherent(self):
        if self.initial_evidence>self.evidence or self.chunk_target>self.chunk_max or self.chunk_overlap>=self.chunk_max:raise ValueError('inconsistent_wiki_budget')
        return self

def settings_from_env():
    mode=os.getenv('WIKI_RETRIEVAL_MODE','legacy')
    if mode not in ('legacy','enhanced'):raise ValueError('invalid_WIKI_RETRIEVAL_MODE')
    values={name:(os.environ['WIKI_RAG_'+name.upper()] if name=='index_mode' else int(os.environ['WIKI_RAG_'+name.upper()])) for name in Budgets.model_fields if os.getenv('WIKI_RAG_'+name.upper())}
    if 'max_new_vectors' not in values:values['max_new_vectors']=int(os.getenv('CODE_INDEX_NEW_VECTOR_BUDGET','0'))
    return {'mode':mode,'version':FLOW_VERSION,'provider':os.getenv('DEEPWIKI_PROVIDER','google'),'model':os.getenv('DEEPWIKI_MODEL','') or None,'budgets':Budgets(**values).model_dump()}

class Question(Strict):
    question_id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    question:str=Field(min_length=1,max_length=800)
    importance:Literal['core','supporting']='core'
    path_hints:list[str]=Field(default_factory=list,max_length=4)
    symbol_hints:list[str]=Field(default_factory=list,max_length=4)
    semantic_query:str=Field(default='',max_length=300)
    assumptions:list[str]=Field(default_factory=list,max_length=4)
class ChapterPlan(Strict):
    chapter_id:str
    title:str
    scope:str=Field(max_length=1000)
    candidate_paths:list[str]=Field(default_factory=list,max_length=12)
    questions:list[Question]=Field(min_length=1,max_length=4)
    schema_version:Literal['wiki-rag-v1']=FLOW_VERSION
    prompt_version:Literal['wiki-plan-v1']='wiki-plan-v1'
    @model_validator(mode='after')
    def distinct(self):
        if not any(q.importance=='core' for q in self.questions):raise ValueError('missing_core_question')
        if len({q.question_id for q in self.questions})!=len(self.questions):raise ValueError('duplicate_question_id')
        if len({q.question.strip().casefold() for q in self.questions})!=len(self.questions):raise ValueError('duplicate_question')
        return self
class ToolArgs(Strict):
    path:str|None=None
    query:str|None=Field(default=None,max_length=300)
    symbol:str|None=Field(default=None,max_length=300)
    start_line:int|None=Field(default=None,ge=1)
    end_line:int|None=Field(default=None,ge=1)
class Action(Strict):
    tool:Literal['search_exact','search_semantic','read_range','read_symbol']
    gap_id:str
    purpose:str=Field(min_length=1,max_length=500)
    question_id:str
    args:ToolArgs
    @model_validator(mode='after')
    def parameters(self):
        allowed={'search_exact':{'query','path'},'search_semantic':{'query'},'read_range':{'path','start_line','end_line'},'read_symbol':{'path','symbol'}}[self.tool]
        actual={k for k,v in self.args.model_dump().items() if v is not None}
        required={'search_exact':{'query'},'search_semantic':{'query'},'read_range':{'path','start_line','end_line'},'read_symbol':{'path','symbol'}}[self.tool]
        if not required<=actual or actual-allowed:raise ValueError('invalid_tool_parameters')
        if self.tool=='read_range' and self.args.end_line<self.args.start_line:raise ValueError('invalid_line_range')
        return self
class Coverage(Strict):
    question_id:str
    status:Literal['supported','partial','unresolved']
    evidence_ids:list[str]=Field(default_factory=list,max_length=40)
    reason:str=Field(max_length=1000)
class Gap(Strict):
    gap_id:str
    question_id:str
    description:str=Field(min_length=1,max_length=1000)
    importance:Literal['core','supporting']
    status:Literal['open','resolved']='open'
class Review(Strict):
    coverage:list[Coverage]=Field(min_length=1,max_length=4)
    gaps:list[Gap]=Field(default_factory=list,max_length=12)
    actions:list[Action]=Field(default_factory=list,max_length=3)
    finish:bool=False
class PageDraft(Strict):
    content:str=Field(min_length=1,max_length=30000)
    citations:list[str]=Field(min_length=1,max_length=40)
