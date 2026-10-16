"""Candidate-fair bounded research; no model calls or imported code execution."""
import os
import re
from datetime import datetime,timezone
from urllib.parse import quote
from pydantic import BaseModel,Field,ConfigDict
from .architecture_schema import ResearchSource
from .analysis_harness import digest
from .providers import ProviderError,safe_path
from .source_reader import sha256

class AdvisorConfig(BaseModel):
    model_config=ConfigDict(extra='forbid')
    web_enabled:bool=False
    web_refresh:bool=False
    max_candidates:int=Field(default=6,ge=1,le=6)
    max_detailed_directions:int=Field(default=3,ge=0,le=3)
    max_semantic_calls:int=Field(default=3,ge=2,le=3)
    max_request_attempts:int=Field(default=4,ge=2,le=4)
    max_web_queries:int=Field(default=6,ge=0,le=20)
    max_web_reads:int=Field(default=6,ge=0,le=20)
    max_parallel_tools:int=Field(default=3,ge=1,le=3)
    followup_rounds:int=Field(default=1,ge=0,le=1)
    plan_output_tokens:int=Field(default=4000,ge=1000,le=16000)
    report_output_tokens:int=Field(default=10000,ge=1000,le=16000)
    @classmethod
    def environment(cls):
        values={}
        for key in cls.model_fields:
            raw=os.getenv('OPTIMIZATION_'+key.upper())
            if raw is None:continue
            if key in ('web_enabled','web_refresh'):
                if raw.lower() not in ('true','false'):raise ValueError('invalid_boolean:'+key)
                values[key]=raw.lower()=='true'
            else:values[key]=int(raw)
        return cls(**values)

class Research:
    def __init__(self,pack,material,reader,retriever,web,config,check):
        self.pack=pack;self.material=material;self.reader=reader;self.retriever=retriever;self.web=web;self.config=config;self.check=check
        self.sources={};self.code_evidence={};self.results=[];self.seen=set();self.queries=0;self.web_reads=0
        self.code_calls=min(32,len(pack.reads));self.chars=0;self.files=set();self.tree=None
        self.max_files=min(16,max(1,int(os.getenv('PROJECT_SOURCE_FILES','12'))))
        for e in pack.evidence:self.add_code(e)
    def add_code(self,e):
        if e.repo!=self.material['repo'] or e.commit_sha!=self.material['commit'] or e.revision_status!='resolved':raise ValueError('research_source_identity')
        ident='src_'+digest([e.repo,e.commit_sha,e.path,e.start_line,e.end_line,e.content_hash])[:24]
        if ident in self.sources:return ident
        if e.start_line is not None and e.end_line is not None:
            for prior in self.sources.values():
                if prior.path!=e.path or prior.source_version!=e.commit_sha or prior.start_line is None or prior.end_line is None:continue
                if max(prior.start_line,e.start_line)>min(prior.end_line,e.end_line)+1:continue
                old_lines=prior.excerpt.splitlines(keepends=True);new_lines=e.excerpt.splitlines(keepends=True)
                if len(old_lines)!=prior.end_line-prior.start_line+1 or len(new_lines)!=e.end_line-e.start_line+1:continue
                merged={prior.start_line+i:line for i,line in enumerate(old_lines)}
                for i,line in enumerate(new_lines):
                    n=e.start_line+i
                    if n in merged and merged[n]!=line:raise ValueError('source_overlap_mismatch')
                    merged[n]=line
                excerpt=''.join(merged[n] for n in sorted(merged))
                if self.chars-len(prior.excerpt)+len(excerpt)>30000:return None
                self.chars+=len(excerpt)-len(prior.excerpt)
                prior.start_line=min(merged);prior.end_line=max(merged);prior.excerpt=excerpt;prior.content_hash=sha256(excerpt)
                prior.locator='https://github.com/'+e.repo+'/blob/'+e.commit_sha+'/'+quote(e.path,safe='/')+'#L'+str(prior.start_line)+'-L'+str(prior.end_line)
                # Keep stable source_id so already-planned candidates retain their source mapping.
                self.code_evidence[e.id+':'+str(e.path)+':'+str(e.start_line)]=e
                return prior.source_id
        if e.path not in self.files and len(self.files)>=self.max_files:return None
        if self.chars+len(e.excerpt)>30000:return None
        kind={'documentation':'repository_doc','test_source':'test_source'}.get(e.kind,'repository_code')
        self.sources[ident]=ResearchSource(source_id=ident,kind=kind,locator='https://github.com/'+e.repo+'/blob/'+e.commit_sha+'/'+quote(e.path,safe='/')+('#L'+str(e.start_line) if e.start_line else ''),path=e.path,start_line=e.start_line,end_line=e.end_line,excerpt=e.excerpt,content_hash=e.content_hash,retrieved_at=datetime.now(timezone.utc).isoformat(),source_version=e.commit_sha)
        self.code_evidence[e.id+':'+str(e.path)+':'+str(e.start_line)]=e
        self.files.add(e.path);self.chars+=len(e.excerpt);return ident
    def run(self,actions,candidate_ids):
        # Serial execution is bounded at 1 <= max_parallel_tools; candidate round-robin.
        groups={k:[] for k in candidate_ids}
        for action in actions:
            if action.candidate_id not in groups:raise ValueError('unknown_research_candidate')
            groups[action.candidate_id].append(action)
        ordered=[]
        for rank in range(max([len(v) for v in groups.values()]+[0])):
            ordered += [v[rank] for v in groups.values() if rank<len(v)]
        for a in ordered:
            self.check();key=digest(a.model_dump(exclude={'candidate_id','question_id','purpose'}))
            prior=next((r for r in self.results if r.get('action_key')==key),None)
            if prior:
                self.results.append({**prior,'candidate_id':a.candidate_id,'question_id':a.question_id,'cached':True});continue
            result={'candidate_id':a.candidate_id,'question_id':a.question_id,'action_key':key,'source_ids':[],'status':'read','unresolved_reason':None}
            try:
                if a.action_type.startswith('code_'):
                    if self.code_calls>=32:raise ValueError('source_budget')
                    self.code_calls+=1
                    if self.tree is None:self.tree=set(self.reader.list_tree(self.material['repo'],self.material['commit'])['paths'])
                    if a.action_type=='code_read':
                        if not safe_path(a.path) or a.path not in self.tree:raise ValueError('unverified_path')
                        if a.start_line is not None or a.end_line is not None:
                            if a.start_line is None or a.end_line is None or a.end_line<a.start_line:raise ValueError('invalid_range')
                        requested=(a.start_line,a.end_line) if a.start_line is not None else None
                        e=self.reader.read_source(self.material['repo'],self.material['commit'],a.path,requested)
                        if requested:
                            if e.start_line is None or e.end_line is None or not(e.start_line<=a.start_line<=a.end_line<=e.end_line):raise ValueError('range_not_loaded')
                        rows=[e]
                    else:
                        if not a.query.strip():raise ValueError('empty_query')
                        hits=self.retriever.search(self.pack.identity['index'],a.query,4)
                        rows=[]
                        for hit in hits:
                            self.check()
                            if self.code_calls>=32:break
                            self.code_calls+=1
                            rows.append(self.retriever.reread(self.reader,self.pack.identity['index'],hit))
                    result['source_ids']=[ident for e in rows if (ident:=self.add_code(e))]
                    if not result['source_ids']:raise ValueError('source_budget_or_no_hits')
                elif a.action_type=='web_search':
                    if self.queries>=self.config.max_web_queries:raise ValueError('web_query_budget')
                    self.queries+=1
                    self.public_query(a.query)
                    answer=self.web.search(a.query);result['status']=answer['status'];result['hits']=[{k:v for k,v in h.items() if k!='raw_content'} for h in answer['hits']]
                    if answer['status']!='ok':result['unresolved_reason']='外部调研未完成：'+answer['status']
                else:
                    if self.web_reads>=self.config.max_web_reads:raise ValueError('web_read_budget')
                    self.web_reads+=1;answer=self.web.read(a.url);result['status']=answer['status']
                    if answer['status']=='ok':
                        ident='web_'+digest([answer['url'],answer['content_hash']])[:24]
                        self.sources[ident]=ResearchSource(source_id=ident,kind='external_source',locator=answer['url'],excerpt=answer['excerpt'],content_hash=answer['content_hash'],retrieved_at=datetime.fromtimestamp(answer['retrieved_at'],timezone.utc).isoformat(),source_version=answer['source_version'],read_status='partial' if answer['partial'] else 'read')
                        result['source_ids']=[ident]
                    else:result['unresolved_reason']='外部调研未完成：'+answer['status']
            except (ValueError,ProviderError) as exc:
                if isinstance(exc,ProviderError) and exc.code in ('cancelled','source_revision'):raise
                result['status']='failed';result['unresolved_reason']=str(exc)
            self.check();self.results.append(result)
        # Search hits are discovery only. Read bounded bodies before handing references to synthesis.
        search_results=[r for r in self.results if r.get('hits') and not r.get('body_checked')]
        for rank in range(2):
            for result in search_results:
                self.check()
                if rank>=len(result['hits']) or self.web_reads>=self.config.max_web_reads:continue
                url=result['hits'][rank]['url'];key=digest(['auto_read',url])
                if key in self.seen:continue
                self.seen.add(key);self.web_reads+=1
                answer=self.web.read(url)
                self.check()
                if answer['status']=='ok':
                    ident='web_'+digest([answer['url'],answer['content_hash']])[:24]
                    self.sources[ident]=ResearchSource(source_id=ident,kind='external_source',locator=answer['url'],excerpt=answer['excerpt'],content_hash=answer['content_hash'],retrieved_at=datetime.fromtimestamp(answer['retrieved_at'],timezone.utc).isoformat(),source_version=answer['source_version'],read_status='partial' if answer['partial'] else 'read')
                    result['source_ids'].append(ident)
                else:result['unresolved_reason']='外部正文未完成：'+answer['status']
        for result in search_results:result['body_checked']=True
        return self.payload()
    def public_query(self,query):
        if not query.strip() or len(query)>200 or re.search(r'https?://|[{};=]|(?:sk-|tvly-)[\w-]+',query):raise ValueError('non_public_query')
        private=[self.material.get('jd',''),*self.material.get('constraints',{}).values(),*[s.excerpt for s in self.sources.values() if s.kind!='external_source']]
        # Fail closed on material fragments; generic technical queries must be independently phrased.
        for text in private:
            if any(query[i:i+12].casefold() in text.casefold() for i in range(max(0,len(query)-11))):raise ValueError('query_contains_private_material')
    def payload(self):
        return {'sources':[s.model_dump() for s in self.sources.values()],'question_results':self.results,
                'coverage':{'queried':len(self.results),'read':sum(bool(r['source_ids']) for r in self.results),'failed':sum(r['status']=='failed' for r in self.results),'omitted':[r for r in self.results if r['unresolved_reason']],'web_status':'enabled' if self.web.enabled and self.web.key else '未完成外部调研：disabled_or_not_configured','source_tool_calls':self.code_calls,'web_tools':self.web.trace}}
