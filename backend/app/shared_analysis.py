"""Workspace-isolated, immutable JD/source analysis shared by both output branches."""
import json
import os
import threading
from pathlib import Path
from pydantic import Field,model_validator
from .analysis_contract import Strict,Requirement,Investigation,Discovery,Verification,GenerationContext,VERSION,validate_discovery,check_claims,Analysis,ReferenceRepair
from .analysis_revision import apply_reference_patches,discard_unlinked_card_details
from .project_inputs import ProjectValue,validate_product
from .model_support import cache_directory
from .analysis_harness import digest
from .source_reader import SourceEvidence,resolved
from .code_retrieval import CodeRetrieval
from .providers import ProviderError

def verification_schema(original,evidence,ctx):
    class CheckedVerification(Verification):
        @model_validator(mode='after')
        def validate_evidence(self):
            if {c.id:c.statement for c in self.claims}!={c.id:c.statement for c in original}:raise ValueError('核验改变事实集合')
            check_claims(self.claims,evidence,ctx,{})
            return self
    return CheckedVerification

def jd_sources(jd):
    # Preserve original text; line IDs are scoped to this frozen JD, not semantic guesses.
    return {f'JD-{i+1:02d}':line for i,line in enumerate(jd.splitlines()) if line.strip()}


def jd_plan_schema(jd,origin):
    sources=jd_sources(jd)
    class PlannedRequirement(Requirement):
        jd_source_ids:list[str]=Field(min_length=1 if origin=='jd' else 0,max_length=6,
            json_schema_extra={'items':{'type':'string','enum':list(sources)}})

        @model_validator(mode='before')
        @classmethod
        def bind_source(cls,value):
            if not isinstance(value,dict):return value
            result=dict(value);refs=result.get('jd_source_ids',[])
            # Read compatibility for old exact excerpts only; never fuzzy-match a paraphrase.
            if not refs and result.get('original_excerpt') and result['original_excerpt'] in jd:
                refs=[key for key,text in sources.items() if result['original_excerpt'] in text]
                if len(refs)!=1:refs=[]
            if not isinstance(refs,list) or any(not isinstance(k,str) or k not in sources for k in refs):
                raise ValueError('jd_source_ids必须选择输入中的JD编号')
            result['jd_source_ids']=list(dict.fromkeys(refs))
            result['origin']=origin
            result['original_excerpt']='\n'.join(sources[k] for k in result['jd_source_ids'])
            return result

    class JDPlan(Investigation):
        requirements:list[PlannedRequirement]=Field(min_length=1,max_length=6)
        @model_validator(mode='after')
        def validate_original(self):
            if len({r.requirement_id for r in self.requirements})!=len(self.requirements):raise ValueError('职责ID重复')
            for r in self.requirements:
                if len(r.queries)!=2 or any(not q.strip() or len(q)>300 for q in r.queries):raise ValueError('每项需两个不超过300字符的短查询')
            return self
    return JDPlan

_lock=threading.RLock()
class SharedAnalysisPack(Strict):
    analysis_pack_id:str
    schema_version:str=VERSION
    identity:dict
    product:ProjectValue
    target:Investigation
    discovery:Discovery
    evidence:list[SourceEvidence]
    retrieval:list[dict]
    reads:list[dict]
    gaps:list[str]
    confirmed_flow:list[str]=Field(default_factory=list)
    supplemental_rounds:int=0
    parent_id:str|None=None
    content_hash:str=''

def get_or_build_analysis(snapshot,material,ctx,reader,call,emit,*,model='configured',check_active=None,retriever=None):
    check=check_active or (lambda:None)
    if not resolved(ctx.commit_sha) and not ctx.commit_sha.startswith('archive-sha256:'):raise ProviderError('共享源码调查需要已解析的目标SHA；未知Wiki版本不能替代','source_revision')
    owned=retriever is None;retriever=retriever or CodeRetrieval(check_active=check)
    try:
        # Explicit prepare can reuse cached vectors only by default. Paid builds require operator budget.
        if ctx.commit_sha.startswith('archive-sha256:'):
            uploaded={}
            for path in reader.list_tree(material['repo'],ctx.commit_sha)['paths']:
                check();uploaded[path]=reader.read_document(material['repo'],ctx.commit_sha,path)
            manifest=retriever.prepare(material['repo'],ctx.commit_sha,int(os.getenv('CODE_INDEX_NEW_VECTOR_BUDGET','0')),uploaded_files=uploaded)
        else:manifest=retriever.prepare(material['repo'],ctx.commit_sha,int(os.getenv('CODE_INDEX_NEW_VECTOR_BUDGET','0')))
        identity={'workspace_id':ctx.workspace_id,'snapshot_id':ctx.snapshot_id,'revision':ctx.commit_sha,'index':manifest,'jd':material.get('jd',''),'jd_version_id':material.get('jd_version_id'),'role':ctx.role,'dimensions':ctx.target_dimensions,'corrections':material.get('project_corrections',[]),'constraints':material.get('constraints',{}),'version':VERSION,'jd_plan_version':'source-ids-v1','model':model,'templates':digest([(p.name,p.read_text(encoding='utf-8')) for p in sorted((Path(__file__).resolve().parents[1]/'prompts/analysis'/name) for name in ('common.md','technical_investigation.md'))])}
        ident=digest(identity);path=cache_directory()/'shared'/ctx.workspace_id/(ident+'.json')
        with _lock:
            check()
            if path.exists():
                pack=SharedAnalysisPack.model_validate_json(path.read_text(encoding='utf-8'))
                if pack.identity!=identity or pack.content_hash!=digest(pack.model_dump(exclude={'content_hash'})):raise ProviderError('共享分析缓存身份或哈希错误','analysis_cache')
                validate_discovery(pack.discovery,{e.id:e for e in pack.evidence},pack.target.requirements,ctx,{})
                emit('SHARED_ANALYSIS','reused_analysis',{'analysis_pack_id':ident,'current_usage':None});return pack
            emit('SHARED_ANALYSIS','cache_miss',{'reason':'无完整匹配包：版本／JD／约束／更正／模型／模板或索引身份不同'})
            tree=reader.list_tree(material['repo'],ctx.commit_sha);paths=set(tree['paths']);evidence={};reads=[];chars=0;gaps=[]
            max_files=min(16,max(1,int((os.getenv('PROJECT_SOURCE_FILES') or os.getenv('RESUME_SOURCE_FILES','12')))))
            read_paths=set()
            def add(e):
                nonlocal chars
                if e.id in evidence:return
                if chars+len(e.excerpt)>30000:gaps.append('源码内容预算未读取：'+str(e.path));return
                evidence[e.id]=e;chars+=len(e.excerpt);read_paths.add(e.path)
            def read(path,terms=()):
                check()
                if path not in paths:gaps.append('路径不在目标版本：'+path);return
                if path not in read_paths and len(read_paths)>=max_files:gaps.append('文件预算未读取：'+path);return
                try:
                    items=reader.search_ranges(material['repo'],ctx.commit_sha,path,list(terms)) if terms else [reader.read_source(material['repo'],ctx.commit_sha,path)]
                    for e in items:add(e)
                    reads.append({'path':path,'status':'read','evidence_ids':[e.id for e in items if e.id in evidence]})
                except ProviderError as exc:
                    if exc.code=='cancelled':raise
                    reads.append({'path':path,'status':exc.code});gaps.append('读取未完成：'+path)
            readmes=sorted(p for p in paths if p.lower() in ('readme.md','readme','readme.zh.md'))
            for p in readmes[:2]:read(p)
            product=call('PROJECT_CONTEXT',ProjectValue,{'sources':[e.model_dump() for e in evidence.values()],'paths':sorted(paths)[:500],'unlisted_paths':max(0,len(paths)-500)},'只按源码文档说明场景、用户流程、组件组织和未知；概况不等于调用连接证据，不捏造行业痛点。source_refs仅用提供的证据ID，evidence_level可用code_present。')
            validate_product(product,{i:'project_existing' for i in evidence})
            target=call('JD_PLAN',jd_plan_schema(material.get('jd',''),ctx.target_origin),{'jd_sources':jd_sources(material.get('jd','')),'role':ctx.role,'target_dimensions':ctx.target_dimensions},'最多6项。通过jd_source_ids选择输入中的JD编号，可关联多条；不要抄写或改写original_excerpt，程序自动填入原文；无JD时jd_source_ids=[]。priority_basis区分明确要求与模型判断。先业务整体架构、组件协作、关键策略、状态传递、失败兜底，再具体缺口。每项queries恰好2条短查询：机制问题及中英文术语别名；不推断已有实现，不强制覆盖所有JD。')
            if tree.get('truncated'):gaps.append('源码目录未完整返回，不能推断未找到的功能不存在')
            retrieved=[];seen=set();hit_batches=[]
            for requirement in target.requirements:
                for n,q in enumerate(requirement.queries):
                    check();hits=retriever.search(manifest,q,8);hit_batches.append(hits)
                    retrieved.append({'requirement_id':requirement.requirement_id,'query_id':requirement.requirement_id+':'+str(n),'query':q,'hits':[h.model_dump(exclude={'text'}) for h in hits],'status':'hits' if hits else 'empty'})
            # Round-robin across requirements: earlier JD items cannot consume all files.
            for rank in range(8):
                for hits in hit_batches:
                    if rank>=len(hits):continue
                    hit=hits[rank];key=(hit.path,hit.start_line,hit.end_line,hit.content_hash)
                    if key in seen:continue
                    seen.add(key)
                    if hit.path not in paths or (hit.path not in read_paths and len(read_paths)>=max_files) or chars>=30000:
                        gaps.append('命中未读：'+hit.path);continue
                    try:add(retriever.reread(reader,manifest,hit))
                    except ProviderError as exc:
                        if exc.code=='cancelled':raise
                        reads.append({'path':hit.path,'status':exc.code});gaps.append('命中补读失败：'+hit.path+' / '+exc.code)
            instruction='按业务主线组织互补工程主题，多个职责可对应同一执行链；同名不同链路不合并。只用当前版本源码证据。调用连接/条件/状态/异常必须有依据，import不是运行集成，测试定义不等于通过。Claim保持原子断言，默认不足待核验；候选每步绑定claim_ids。scope=project_intro的Claim用于项目主线。只为影响判断的缺口提出最多4个next_reads，路径必须来自paths。纯项目能力attribution=upstream，不推断个人贡献。'
            data={'project_corrections':material.get('project_corrections',[]),'product':product.model_dump(),'requirements':target.model_dump(),'sources':[e.model_dump() for e in evidence.values()],'paths':sorted(paths)[:500],'coverage':{'tree_truncated':tree.get('truncated',False),'unlisted_paths':max(0,len(paths)-500),'gaps':gaps}}
            analysis=call('INVESTIGATE',Analysis,data,instruction)
            supplemental=int(bool(analysis.next_reads))
            if supplemental:
                for request in analysis.next_reads:read(request.path,request.terms)
                analysis=call('SYNTHESIZE',Analysis,{**data,'previous':analysis.model_dump(),'sources':[e.model_dump() for e in evidence.values()],'remaining_gaps':gaps},instruction+'补读已用完，不再请求循环；保留尚未查明问题。')
            discovery=Discovery.model_validate(analysis.model_dump(exclude={'next_reads','confirmed_flow','unresolved_questions'}))
            for c in discovery.claims:
                if c.attribution in ('user_confirmed','user_evidenced'):
                    c.attribution='unknown';c.contribution_id=None
                    emit('INVESTIGATE','attribution_capped',{'claim_id':c.id,'reason':'共享项目调查不推断个人贡献'})
            try:validate_discovery(discovery,evidence,target.requirements,ctx,{},verified=False)
            except ValueError as error:
                repair=call('INVESTIGATE_LINK_REPAIR',ReferenceRepair,{'previous':discovery.model_dump(),'error':str(error),'evidence_ids':list(evidence)},'只修复证据/claim引用，不改断言、不创建事实；无法关联的可选机制标注应删除。')
                discovery=apply_reference_patches(discovery,repair)
                removed=discard_unlinked_card_details(discovery)
                if removed:emit('INVESTIGATE','unlinked_details_removed',{'removed':removed})
                validate_discovery(discovery,evidence,target.requirements,ctx,{},verified=False)
            checked=call('CLAIM_VERIFY',verification_schema(discovery.claims,evidence,ctx),{'claims':[{k:v for k,v in c.model_dump().items() if k in ('id','statement','evidence_ids')} for c in discovery.claims],'sources':[e.model_dump() for e in evidence.values()]},'独立核验各原子断言。保持id/statement集合不变，只核对支持程度、实现范围、集成/测试层级。归属只能upstream/unknown；没有运行报告不能test_passed/runtime_measured。没有调用/配置证据不得integrated。')
            if {c.id:c.statement for c in checked.claims}!={c.id:c.statement for c in discovery.claims}:raise ValueError('核验改变事实集合')
            discovery.claims=checked.claims
            validate_discovery(discovery,evidence,target.requirements,ctx,{})
            pack=SharedAnalysisPack(analysis_pack_id=ident,identity=identity,product=product,target=target,discovery=discovery,evidence=list(evidence.values()),retrieval=retrieved,reads=reads+retriever.trace,gaps=list(dict.fromkeys(gaps+analysis.unresolved_questions)),confirmed_flow=analysis.confirmed_flow,supplemental_rounds=supplemental)
            pack.content_hash=digest(pack.model_dump(exclude={'content_hash'}));check()
            path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.'+os.urandom(6).hex()+'.tmp');tmp.write_text(pack.model_dump_json(),encoding='utf-8');check();tmp.replace(path)
            emit('SHARED_ANALYSIS','published',{'analysis_pack_id':ident,'gaps':pack.gaps,'retrieval_usage':retriever.trace});return pack
    finally:
        if owned:retriever.close()


def extend_analysis(pack,feedback,material,ctx,reader,call,emit,check_active=None,retriever=None):
    """At most one derived investigation; immutable parent remains available."""
    if pack.supplemental_rounds:return pack
    check=check_active or (lambda:None);check()
    owned=retriever is None;retriever=retriever or CodeRetrieval(check_active=check,max_queries=4)
    evidence={e.id:e for e in pack.evidence};paths={e.path for e in pack.evidence};chars=sum(len(e.excerpt) for e in pack.evidence)
    max_files=min(16,max(1,int((os.getenv('PROJECT_SOURCE_FILES') or os.getenv('RESUME_SOURCE_FILES','12')))));reads=list(pack.reads);gaps=[]
    tree=set(reader.list_tree(material['repo'],ctx.commit_sha)['paths'])
    def add(e):
        nonlocal chars
        if e.id in evidence:return
        if (e.path not in paths and len(paths)>=max_files) or chars+len(e.excerpt)>30000:
            gaps.append('补读预算未覆盖：'+str(e.path));return
        evidence[e.id]=e;paths.add(e.path);chars+=len(e.excerpt)
    try:
        for f in feedback[:4]:
            check()
            for hit in retriever.search(pack.identity['index'],f.issue[:1000],4):
                if hit.path not in tree or (hit.path not in paths and len(paths)>=max_files):continue
                try:add(retriever.reread(reader,pack.identity['index'],hit))
                except ProviderError as e:
                    if e.code=='cancelled':raise
                    gaps.append('补读失败：'+hit.path+' / '+e.code)
            for path in f.paths:
                if path not in tree or (path not in paths and len(paths)>=max_files):continue
                try:
                    for e in reader.search_ranges(material['repo'],ctx.commit_sha,path,[f.issue[:120]]):add(e)
                except ProviderError as e:
                    if e.code=='cancelled':raise
                    gaps.append('补读失败：'+path+' / '+e.code)
        updated=call('SYNTHESIZE',Analysis,{'previous':pack.discovery.model_dump(),'product':pack.product.model_dump(),'requirements':pack.target.model_dump(),'feedback':[f.model_dump() for f in feedback],'sources':[e.model_dump() for e in evidence.values()]},'仅依据新增证据补全缺口或发现候选。不原地修改旧事实陈述；纠正用新ID和supersedes_claim_id，主题拆分/合并用supersedes_candidate_ids。未知留缺口；不再请求补读。纯项目归属，不引入个人贡献。')
        discovery=Discovery.model_validate(updated.model_dump(exclude={'next_reads','confirmed_flow','unresolved_questions'}))
        from .analysis_revision import discovery_transition
        history=discovery_transition(pack.discovery,discovery,evidence)
        validate_discovery(discovery,evidence,pack.target.requirements,ctx,{},verified=False)
        checked=call('CLAIM_VERIFY_INCREMENTAL',verification_schema(discovery.claims,evidence,ctx),{'claims':[{k:v for k,v in c.model_dump().items() if k in ('id','statement','evidence_ids')} for c in discovery.claims],'sources':[e.model_dump() for e in evidence.values()]},'独立核验，不改变id或statement；源码存在不代表集成/测试通过，不推断个人贡献。')
        if {c.id:c.statement for c in checked.claims}!={c.id:c.statement for c in discovery.claims}:raise ValueError('核验改变事实集合')
        discovery.claims=checked.claims;validate_discovery(discovery,evidence,pack.target.requirements,ctx,{})
        identity={**pack.identity,'parent_id':pack.analysis_pack_id,'feedback':digest([f.model_dump() for f in feedback])}
        derived=pack.model_copy(deep=True);derived.identity=identity;derived.analysis_pack_id=digest(identity);derived.parent_id=pack.analysis_pack_id
        derived.discovery=discovery;derived.evidence=list(evidence.values());derived.reads=reads+retriever.trace
        derived.supplemental_rounds=1;derived.gaps=list(dict.fromkeys(pack.gaps+gaps+updated.unresolved_questions));derived.confirmed_flow=updated.confirmed_flow or pack.confirmed_flow
        derived.content_hash=digest(derived.model_dump(exclude={'content_hash'}));check()
        path=cache_directory()/'shared'/ctx.workspace_id/(derived.analysis_pack_id+'.json');path.parent.mkdir(parents=True,exist_ok=True)
        tmp=path.with_suffix('.'+os.urandom(6).hex()+'.tmp');tmp.write_text(derived.model_dump_json(),encoding='utf-8');check();tmp.replace(path)
        emit('SHARED_ANALYSIS','derived',{'analysis_pack_id':derived.analysis_pack_id,'parent_id':pack.analysis_pack_id,'transition':history,'retrieval_usage':retriever.trace})
        return derived
    finally:
        if owned:retriever.close()
