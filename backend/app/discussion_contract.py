"""Discussion-only contracts. No contribution/JD/resume mutation operations."""
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class OpenConversation(Strict):
    surface:Literal['wiki','discussion','legacy']='wiki'
class Question(Strict):
    request_id:str=Field(min_length=1,max_length=100)
    expected_revision:int=Field(ge=0)
    content:str=Field(min_length=1,max_length=20000)
    run_id:str|None=None
    page_id:str|None=None
class MemoryChange(Strict):
    expected_revision:int=Field(ge=0)
    request_id:str=Field(min_length=1,max_length=100)
    kind:Literal['constraint','correction','proposal_note','open_question','code_observation']='constraint'
    scope:Literal['conversation','topic','workspace']='conversation'
    subject_key:str=Field(min_length=1,max_length=200)
    content:str=Field(min_length=1,max_length=2000)
    target_id:str|None=None
    action:Literal['ADD','MERGE','SUPERSEDE','RETRACT','RESOLVE']='ADD'
class MemoryCandidate(Strict):
    kind:Literal['constraint','correction','proposal_note','open_question','code_observation']
    scope:Literal['conversation','topic','workspace']='conversation'
    subject_key:str=Field(min_length=1,max_length=200)
    content:str=Field(min_length=1,max_length=2000)
    origin:Literal['user_explicit','assistant_proposal','source_observation']
    source_message_ids:list[str]=Field(min_length=1,max_length=4)
    evidence_refs:list[str]=Field(default_factory=list,max_length=6)
    source_revision:str='unknown'
    target_id:str|None=None
    action:Literal['ADD','MERGE','SUPERSEDE']='ADD'
class Plan(Strict):
    topic_relation:Literal['continue','switch','return','compare']='continue'
    topic_title:str=Field(default='',max_length=120)
    focused_refs:list[str]=Field(default_factory=list,max_length=6)
    standalone_query:str=Field(default='',max_length=4000)
    history_needed:bool=False
    history_query:str=Field(default='',max_length=200)
    source_lookup_needed:bool=False
    memory_candidates:list[MemoryCandidate]=Field(default_factory=list,max_length=5)
    clarification:str=Field(default='',max_length=500)

class CancelTurn(Strict):
    request_id:str=Field(min_length=1,max_length=100)
