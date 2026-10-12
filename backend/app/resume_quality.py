"""Production quality pipeline: bounded investigation, source verification and mapped prose."""
import json
import os
import re
import time
from pathlib import Path
from .providers import ProviderError
from .source_reader import SourceReader, SourceEvidence, resolved, sha256, related_source_paths
from .resume_harness import Harness, GUARD, chunks, spans, parse_json, digest
from .resume_contract import *
from .resume_prompts import compose, task_for_stage, validate_configuration

from .resume_index import retrieve, section_index, ALIASES
from .resume_revision import discovery_transition, fact_gate, reviewed_score, restore_verification_identity

def material_evidence(material):
    ev={};repo=material.get('repo','');sha=material.get('commit','unresolved')
    def add(ident,kind,text,**kw):
        ev[ident]=SourceEvidence(id=ident,kind=kind,repo=repo,commit_sha='unknown' if kind=='wiki' else sha,content_hash=sha256(text),excerpt=text,revision_status='unknown' if kind=='wiki' else 'user_submitted',**kw)
    for i,p in enumerate(material.get('_full_wiki_pages',material.get('wiki_pages',[]))):
        add(f'wiki:{i}','wiki',p['content'],wiki_page_id=p.get('page_id',str(i)))
    for c in chunks(material):
        add(c['id'],'wiki',c['content'])
        for s in spans(c):add(s['id'],'wiki',s['content'])
    for section in section_index(material):add(section['id'],'wiki',section['content'],wiki_page_id=section['page_ref'])
    if material.get('overview'):add('overview','wiki',json.dumps(material['overview'],ensure_ascii=False))
    for c in material.get('user_optimizations',[]):add('optimization:'+c['id'],'user_statement',json.dumps(c,ensure_ascii=False))
    for e in material.get('user_materials',[]):add('user-material:'+e['id'],e.get('type','user_statement'),e['excerpt'])
    for e in material.get('experiments',[]):add('experiment:'+e['id'],'experiment',json.dumps(e['details'],ensure_ascii=False))
    for m in material.get('reported_metrics',[]):add('reported-metric:'+m['id'],'user_statement',json.dumps(m,ensure_ascii=False))
    for i in material.get('improvement_states',[]):add('improvement-state:'+i['id'],'user_statement',json.dumps(i,ensure_ascii=False))
    return ev

def mapping_inventory(material,mapped):
    """Expose page-level mapping loss without treating word hits as semantic coverage."""
    rows=[]
    for i,page in enumerate(material.get('_full_wiki_pages',material.get('wiki_pages',[]))):
        prefix=f'wiki:{i}'
        facts=[f for f in mapped['facts'] if f['source_ref']==prefix or f['source_ref'].startswith(prefix+':')]
        rows.append({'page_ref':prefix,'title':page.get('title',''),'mapped_fact_count':len(facts),'mechanisms':list(dict.fromkeys(f['mechanism'] for f in facts if f.get('mechanism'))),'status':'mapped_facts_available' if facts else 'no_mapped_facts'})
    return rows

def metric_records(material):
    records={e['id']:Metric(id=e['id'],name=e['details']['metric'],value=e['details']['modified_value'],unit=e['details']['unit'],baseline=e['details']['baseline_value'],sample_scope=e['details']['dataset_description'],environment=e['details']['conditions'],measurement_method='用户提交的对照实验',state='user_reported',experiment_id=e['id'],contribution_id=e['contribution_id']) for e in material.get('experiments',[])}
    for m in material.get('reported_metrics',[]):
        records[m['id']]=Metric(id=m['id'],name=m['name'],value=m['value'],unit=m['unit'],baseline=m.get('baseline'),sample_scope=m.get('sample_size') or '样本未提供',environment='用户提供，未独立核验',measurement_method=m.get('method') or '方法未提供',state='user_reported',user_statement_id='reported-metric:'+m['id'],contribution_id=m.get('contribution_id'),change_type=m['change_type'])
    return records

def source_investigation(reader,material,evidence,requirements,extra_paths=(),*,cards=None,ledger=None):
    records=[];repo=material['repo'];sha=material['commit']
    if not resolved(sha) and not sha.startswith('archive-sha256:'):
        return [{'status':'unresolved','reason':'历史快照没有真实SHA，只使用Wiki线索，不追认源码核验'}]
    questions=[]
    if cards is not None:
        questions=[{'candidate_id':c.candidate_id,'questions':c.investigation_questions or c.gaps,'paths':c.source_paths} for c in cards if c.investigation_questions or c.gaps]
        if not questions:return [{'status':'not_needed','reason':'候选未提出缺失连接，不重复按JD扫描源码'}]
    try:tree=reader.list_tree(repo,sha)
    except ProviderError as exc:return [{'status':'failed','error':exc.code,'reason':str(exc)}]
    paths=set(tree['paths']);terms=list({t for q in requirements for t in q.search_terms}|{a for key,values in ALIASES.items() if any(key in t.lower() for q in requirements for t in q.search_terms) for a in values})
    hints={p for page in material.get('_full_wiki_pages',[]) for p in page.get('filePaths',[]) if isinstance(p,str)}
    if cards is not None:
        # Candidate questions and named implementation symbols drive the read, not JD keywords.
        terms=list(dict.fromkeys(t for c in cards if c.investigation_questions or c.gaps for t in re.findall(r'[A-Za-z_][A-Za-z0-9_]{2,}',c.mechanism+' '+' '.join(c.investigation_questions+c.gaps))))
        hints={p for q in questions for p in q['paths']}
        extra_paths=tuple(set(extra_paths)|hints)
        records.append({'status':'questions','candidates':questions})
        records.extend({'path':p,'status':'not_found','reason':'候选线索不在固定版本文件树中，不作为源码证据'} for p in sorted(set(extra_paths)-paths))
    scored=[]
    for p in paths:
        if Path(p).suffix.lower() not in ('.py','.ts','.tsx','.js','.jsx','.go','.rs','.java','.md','.mjs','.cjs'):continue
        score=4*sum(t.lower() in p.lower() for t in terms)+2*(p in hints)+40*(p in extra_paths)
        if Path(p).suffix.lower()=='.md':score-=4
        if cards is None and any(x in p.lower() for x in ('agent','memory','runtime','orchestr','boundary','context')):score+=3
        if score>0 or (cards is None and p.lower().startswith('readme')):scored.append((score,p))
    scored.sort(key=lambda row:(-row[0],row[1]));chars=0
    max_files=min(16,max(1,int(os.getenv('RESUME_SOURCE_FILES','12'))))
    ledger=ledger if ledger is not None else {'paths':set(),'chars':0}
    initial=not ledger['paths'];queries=ledger.setdefault('queries',set())
    char_limit=20000 if cards is not None and initial else 30000
    remaining=max(0,max_files-len(ledger['paths']))
    if cards is not None and not ledger['paths'] and max_files>=4:
        remaining=min(remaining,max_files-max_files//3)  # reserve capacity for the one repair pass
    unread=[row for row in scored if row[1] not in ledger['paths']]
    query_key=tuple(sorted(terms))
    rereads=[row for row in scored if row[1] in ledger['paths'] and row[1] in extra_paths and (row[1],query_key) not in queries]
    initial_paths=set(ledger['paths'])
    queue=[(path,0) for _,path in [*rereads,*unread[:remaining-2 if cards is not None and remaining>=4 else remaining]]]
    scheduled={p for p,_ in queue};linked_count=0
    for path,depth in queue:
        ledger['paths'].add(path)
        queries.add((path,query_key))
        try:
            items=reader.search_ranges(repo,sha,path,terms)
            for item in items:
                if item.id in evidence:continue
                if ledger['chars']+len(item.excerpt)>char_limit:
                    records.append({'path':path,'status':'budget','reason':f'本轮源码上下文上限{char_limit}字符（总额30000），未将未读范围标为已核验'});continue
                evidence[item.id]=item;chars+=len(item.excerpt);ledger['chars']+=len(item.excerpt)
            accepted=[i.id for i in items if i.id in evidence]
            records.append({'path':path,'status':'read' if accepted else 'budget','evidence_ids':accepted})
            searches=[t for t in getattr(reader,'trace',[]) if t.get('stage')=='source_search' and t.get('path')==path]
            if searches:records.append({**searches[-1],'status':'matched_ranges','note':'未读命中不是不存在'})
            if cards is not None and depth==0 and accepted:
                for item in items:
                    if item.id not in evidence:continue
                    for linked in related_source_paths(path,item.excerpt,paths):
                        if linked in scheduled or linked in ledger['paths'] or linked_count>=2:continue
                        # One-hop imports share the original file and character budget.
                        if len({p for p,_ in queue}-initial_paths)>=remaining:
                            continue
                        queue.append((linked,1));scheduled.add(linked);linked_count+=1
                        records.append({'status':'dependency_hint','from_path':path,'path':linked,'reason':'静态相对导入线索，不代表调用链已确认'})
        except (ProviderError,OSError) as exc:records.append({'path':path,'status':'failed','error':getattr(exc,'code','source_io'),'reason':str(exc)[:200]})
    if tree['truncated']:records.append({'status':'partial','reason':'GitHub文件树截断，不能声明全仓覆盖'})
    if any(path not in ledger['paths'] for _,path in unread):records.append({'status':'budget','reason':f'累计最多定向读取{max_files}文件，剩余候选路径未核验'})
    return records

def validate_discovery(discovery,evidence,requirements,context,contributions):
    check_claims(discovery.claims,evidence,context,contributions)
    cs={c.id for c in discovery.claims};rs={r.requirement_id for r in requirements}
    ids=[c.candidate_id for c in discovery.candidates]
    if len(set(ids))!=len(ids):raise ValueError('候选ID重复')
    for c in discovery.candidates:
        if not set(c.claim_ids)<=cs or not set(c.requirement_ids)<=rs:raise ValueError('候选引用未知claim/职责')
        refs=set(c.atomic_fact_ids+c.problem_claim_ids+c.contribution_claim_ids+c.result_claim_ids)
        refs.update(i for step in c.mechanism_steps+c.exception_boundaries for i in step.claim_ids)
        if not refs<=set(c.claim_ids):raise ValueError('候选 '+c.candidate_id+'机制卡片事实引用不属于候选claim：'+','.join(sorted(refs-set(c.claim_ids))))
        if any(i not in evidence for i in c.result_refs):raise ValueError('候选结果来源不存在')
    return discovery

def discard_unlinked_card_details(discovery):
    """Discard unsupported optional annotations; never guess evidence-to-claim links."""
    changes=[]
    for c in discovery.candidates:
        allowed=set(c.claim_ids)
        for field in ('atomic_fact_ids','problem_claim_ids','contribution_claim_ids','result_claim_ids'):
            refs=getattr(c,field);invalid=[i for i in refs if i not in allowed]
            if invalid:
                setattr(c,field,[i for i in refs if i in allowed])
                if field=='problem_claim_ids':c.problem=''
                changes.append({'candidate_id':c.candidate_id,'field':field,'removed_refs':invalid})
        for field in ('mechanism_steps','exception_boundaries'):
            kept=[]
            for step in getattr(c,field):
                if set(step.claim_ids)<=allowed:kept.append(step)
                else:changes.append({'candidate_id':c.candidate_id,'field':field,'removed_text':step.text,'removed_refs':[i for i in step.claim_ids if i not in allowed]})
            setattr(c,field,kept)
        if any(x['candidate_id']==c.candidate_id for x in changes):
            c.gaps=list(dict.fromkeys(['机制标注引用不匹配，已移除；关键连接仍待补证']+c.gaps))[:5]
    return changes

def apply_reference_patches(discovery,repair):
    """Transactional structural edits: no statement, state or new entity can be changed."""
    updated=discovery.model_copy(deep=True);seen=set();deletions=[]
    for patch in repair.patches:
        key=(patch.target,patch.target_id,patch.field,patch.index)
        if key in seen:raise ValueError('重复关联补丁')
        seen.add(key)
        rows=updated.claims if patch.target=='claim' else updated.candidates
        row=next((r for r in rows if (r.id if patch.target=='claim' else r.candidate_id)==patch.target_id),None)
        if row is None:raise ValueError('关联补丁目标不存在')
        if patch.target=='claim':
            if patch.field!='evidence_ids' or patch.index is not None or patch.drop:raise ValueError('事实补丁只能修改证据引用')
            if not patch.refs:raise ValueError('关联修复未提供有效证据：'+patch.target_id+'；已保留原事实，请核对材料来源')
            row.evidence_ids=patch.refs
        elif patch.field in ('mechanism_steps','exception_boundaries'):
            steps=getattr(row,patch.field)
            if patch.index is None or patch.index>=len(steps):raise ValueError('机制补丁位置不存在')
            if patch.drop:
                if patch.refs:raise ValueError('删除补丁不得附带引用')
                deletions.append((row,patch.field,patch.index))
            else:steps[patch.index].claim_ids=patch.refs
        else:
            if patch.field=='evidence_ids' or patch.index is not None or patch.drop:raise ValueError('候选补丁字段无效')
            setattr(row,patch.field,patch.refs)
    # Indices always refer to the original response, including multiple deletions.
    for row,field,index in sorted(deletions,key=lambda x:x[2],reverse=True):getattr(row,field).pop(index)
    return Discovery.model_validate(updated.model_dump())

def validate_choice(choice,candidates,claims,requirements,mode):
    if len(set(choice.selected_ids))!=len(choice.selected_ids) or not set(choice.selected_ids)<=set(candidates):raise ValueError('选题ID无效')
    for cid in choice.selected_ids:
        if cid not in choice.reasons:raise ValueError('选题缺理由')
        supported=[claims[i] for i in candidates[cid].claim_ids if claims[i].support=='supported' and claims[i].implementation_state=='implemented']
        if not supported:raise ValueError('入选候选没有已实现的支持claim')
        if mode=='personal_resume' and not any(c.attribution in ('user_confirmed','user_evidenced') for c in supported):raise ValueError('个人选题没有确认贡献')
    rids={r.requirement_id for r in requirements}
    if {c.requirement_id for c in choice.coverage}!=rids:raise ValueError('岗位覆盖必须记录每项调查职责')
    for c in choice.coverage:
        if not set(c.claim_ids)<=set(claims) or not set(c.candidate_ids)<=set(candidates):raise ValueError('覆盖引用无效')
        if c.status=='not_applicable' and not c.reason:raise ValueError('不适用必须解释')
        if c.status=='direct' and not any(claims[i].support=='supported' for i in c.claim_ids):raise ValueError('无支持claim不能直接覆盖职责')
    return choice

def writing_pack(candidates,claims,choice):
    """No rejected themes or unsupported mechanisms in the writer's fact packet."""
    selected=[candidates[i] for i in choice.selected_ids]
    ids={i for c in selected for i in c.claim_ids}
    writable={i:c for i,c in claims.items() if i in ids and c.support=='supported' and c.implementation_state=='implemented'}
    cards=[]
    for c in selected:
        card=c.model_dump()
        for field in ('claim_ids','atomic_fact_ids','problem_claim_ids','contribution_claim_ids','result_claim_ids'):
            card[field]=[i for i in card[field] if i in writable]
        if not c.problem_claim_ids or not set(c.problem_claim_ids)<=set(writable):card['problem']=''
        for field in ('mechanism_steps','exception_boundaries'):
            card[field]=[s for s in card[field] if set(s['claim_ids'])<=set(writable)]
        # Free-form discovery prose is a hypothesis; only mapped facts may describe mechanisms.
        for field in ('mechanism','personal_contribution','tradeoff','result_refs','reason'):card.pop(field,None)
        cards.append(card)
    return cards,writable

def project_spine(claims):
    """Whole-project context remains available for the introduction, not new bullets."""
    return {i:c for i,c in claims.items() if c.support=='supported' and c.implementation_state=='implemented' and c.attribution=='upstream'}

def bound_attribution(claim,contributions,evidence=None):
    """Conservatively cap model labels; never create confirmed personal evidence."""
    if claim.attribution not in ('user_confirmed','user_evidenced'):return None
    current=contributions.get(claim.contribution_id)
    if current and current['state'] in ('implemented','validated'):return None
    original={'claim_id':claim.id,'attribution':claim.attribution,'implementation_state':claim.implementation_state}
    claim.attribution='unknown';claim.contribution_id=None
    # Preserve project facts only when there is project evidence independent of
    # an unbound user statement. A plan is not an implementation by relabelling it.
    if not any(ref in (evidence or {}) and evidence[ref].kind in ('code','test_source','wiki') for ref in claim.evidence_ids):
        claim.implementation_state='unknown';claim.validation_level='unknown'
    claim.limitations=list(dict.fromkeys(claim.limitations+['未关联当前确认贡献，个人归属未知；事实支持与实现状态独立判断']))[:8]
    return original

def generate(snapshot,material,chat=None,source_reader=None):
    from .resume_support import WritingModel, ProjectValue, ROOT, validate_product, cache_directory
    provider=WritingModel() if chat is None else None;chat=provider or chat
    owned=source_reader is None;reader=source_reader or SourceReader(material.get('workspace_id','offline'),snapshot)
    max_downstream=min(20,max(8,int(os.getenv('RESUME_GENERATION_CALLS','16'))))
    h=Harness(chat,model=provider.base+'|'+provider.model if provider else 'injected',cache_dir=cache_directory() if provider else None,max_calls=128+max_downstream,check_active=material.get('_check_active'),structured_output=True)
    ctx=GenerationContext(**material.get('_generation_context',dict(workspace_id=material.get('workspace_id','offline'),snapshot_id=material.get('snapshot_id','offline'),commit_sha=material.get('commit','unresolved'),revision_status='resolved' if resolved(material.get('commit')) else 'unresolved',role=material.get('role',''),jd_version_id=material.get('jd_version_id'),target_origin='jd' if material.get('jd') else 'role_inferred',material_fingerprint=digest({k:v for k,v in material.items() if not k.startswith('_')}),output_mode=material.get('_output_mode','project_reference'),target_dimensions=material.get('_target_dimensions',[]))))
    discovery_history=[];stage_cache={}
    ctx.model=provider.model if provider else getattr(chat,'model','injected');trace=[];progress=material.get('_progress');downstream=0;repair_calls=0
    def emit(stage,status,structure=None,error=None):
        record={'stage':stage,'status':status,'output_structure':structure or {},'input_refs':{'snapshot_id':ctx.snapshot_id,'commit_sha':ctx.commit_sha,'jd_version_id':ctx.jd_version_id},'error':error,'retry_count':int(stage.endswith('_RESELECT'))}
        trace.append(record)
        if progress:progress(record,{'context':ctx.model_dump(),'calls':h.records,'trace':trace})
    def call(stage,schema,data,instruction):
        nonlocal downstream,repair_calls
        start=time.monotonic();emit(stage,'running')
        try:
            prompt=stage+'\n'+GUARD+'\n'+instruction+'\n'+json.dumps(data,ensure_ascii=False)+'\nJSON schema:'+json.dumps(schema.model_json_schema(),ensure_ascii=False)
            task=task_for_stage(stage)
            if task:
                prompt,metadata=compose(task,stage,schema,data,instruction)
                emit(stage,'prompt_ready',{**metadata,'context':ctx.model_dump()})
            key=h.stage_cache_key(prompt,{'workspace_id':ctx.workspace_id,'snapshot_id':ctx.snapshot_id,'commit_sha':ctx.commit_sha,'version':VERSION})
            cached=h.read_stage(key,schema) if not stage.endswith('_REPAIR') else None
            if cached is not None:
                emit(stage,'completed',{'output':cached.model_dump(),'cached':True,'usage':None,'cache_key':key})
                return cached
            if downstream>=max_downstream:raise ProviderError('本次生成请求次数达到上限，不是模型账户余额不足','resume_budget')
            if stage.endswith('_REPAIR'):
                if repair_calls>=1:raise ProviderError('本次契约修复已达一次上限；检查点保留，不继续重复修复','resume_contract')
                repair_calls+=1
            downstream+=1
            raw=h.call(prompt,stage=stage)
            try:
                parsed=parse_json(raw)
                if schema is Verification:
                    restored=restore_verification_identity(parsed,data.get('claims',[]))
                    if restored:emit(stage,'identity_restored',{'fields':restored})
                if schema is Discovery and isinstance(parsed,dict):
                    for card in parsed.get('candidates',[]):
                        paths=card.get('source_paths')
                        if isinstance(paths,list) and all(isinstance(p,str) for p in paths):
                            selected=list(dict.fromkeys(paths))[:4]
                            if paths!=selected:emit(stage,'source_paths_budgeted',{'candidate_id':card.get('candidate_id'),'omitted_paths':[p for p in paths if p not in selected]})
                            card['source_paths']=selected
                result=schema.model_validate(parsed)
            except (ValueError, TypeError) as validation:
                details=[{'loc':list(e['loc']),'type':e['type']} for e in validation.errors()] if hasattr(validation,'errors') else [{'type':type(validation).__name__}]
                emit(stage,'schema_repair',{'errors':details[:20],'response':raw})
                if repair_calls>=1:raise ProviderError('本次契约修复已达一次上限；结构错误记录保留','resume_contract')
                repair_calls+=1
                if downstream>=max_downstream:raise ProviderError('本次生成请求次数达到上限，无法继续结构修复','resume_budget')
                downstream+=1
                repair=stage+'_SCHEMA_REPAIR\n'+GUARD+'\n仅修复下列JSON结构错误，保留原断言、ID、证据和事实状态，不增加事实。\n'+json.dumps({'errors':details[:20],'previous':raw,'original_claims':data.get('claims',[])},ensure_ascii=False)+'\nJSON schema:'+json.dumps(schema.model_json_schema(),ensure_ascii=False)
                result=schema.model_validate(parse_json(h.call(repair,stage=stage+'_SCHEMA_REPAIR')))
            if not stage.endswith('_REPAIR'):stage_cache[key]=result.model_copy(deep=True)
            emit(stage,'completed',{'output':result.model_dump(),'elapsed_seconds':round(time.monotonic()-start,3)});return result
        except Exception as exc:
            details=[{'loc':list(e['loc']),'type':e['type']} for e in exc.errors()] if hasattr(exc,'errors') else []
            emit(stage,'failed',{'validation_errors':details[:20]},error=getattr(exc,'code',type(exc).__name__))
            if isinstance(exc,ProviderError):raise
            raise ProviderError(stage+'返回结构不合格；阶段记录已保留','resume_contract') from exc
    try:
        validate_configuration()
        emit('MAPPING','running');mapped=h.map_wiki(material);emit('MAPPING','completed',{'batches':mapped['batches'],'cache_hits':mapped['cache_hits']})
        evidence=material_evidence(material);contributions={c['id']:c for c in material.get('user_optimizations',[]) if c['state']!='abandoned'}
        compact=[{k:v for k,v in f.items() if k!='quote'} for f in mapped['facts']]
        inventory=mapping_inventory(material,mapped)
        emit('MAPPING_INVENTORY','completed',{'pages':inventory,'note':'记录映射材料，不代表语义理解完整'})
        product=call('PRODUCT',ProjectValue,{'facts':compact,'uncertainties':mapped['uncertainties']},'独立于JD提炼产品全貌、用户闭环、整体架构和关键机制连接。引用有效Wiki编号；不从模块存在推断已集成或运行效果，作者背景须有来源，缺失连接列limitations。')
        product_refs={i:'project_existing' for i,e in evidence.items() if e.kind=='wiki'}
        try:validate_product(product,product_refs)
        except ValueError:
            invalid=list({ref for item in product.claims+product.architecture+product.key_chains for ref in item.source_refs if ref not in product_refs})
            emit('PRODUCT','reference_repair',{'invalid_refs':invalid})
            product=call('PRODUCT_REFERENCE_REPAIR',ProjectValue,{'previous':product.model_dump(),'invalid_refs':invalid,'facts':compact},'修复引用：只能引用facts中实际出现的source_ref。不得推断编号拼写或生成证据；断言找不到原文支持时删除该断言/链路，记录uncertainties。保持项目能力与个人贡献分开。')
            validate_product(product,product_refs)
        target=call('JD_PLAN',Investigation,{'role':ctx.role,'jd':material.get('jd',''),'editable_dimensions':material.get('_target_dimensions',[])},'有JD按原文职责规划最多6个关于当前项目机制的中性调查问题，不问候选人经历，不预设个人实现；search_terms必须含简短英文技术名/代码标识别名而非长句；无JD按岗位名称推断临时维度，origin=role_inferred，不冒充招聘JD。每项稳定requirement_id和优先级；先抽象岗位能力，再提中性实现问题，例如任务推进/终止、上下文选择与更新、工具结果校验、失败恢复；框架名不是能力证明，不要求项目具备JD所有技术。中英文别名检索词，不预设RAG等方案。')
        if len({r.requirement_id for r in target.requirements})!=len(target.requirements) or any(r.origin!=ctx.target_origin for r in target.requirements):raise ProviderError('职责ID或推断来源不一致','resume_contract')
        def accept_discovery(result,stage):
            # Discovery labels are hypotheses; cap unbound personal claims before link validation.
            for claim in result.claims:
                capped=bound_attribution(claim,contributions,evidence)
                if capped:emit(stage,'attribution_capped',capped)
            try:return validate_discovery(result,evidence,target.requirements,ctx,contributions)
            except ValueError as exc:
                emit(stage,'link_repair',{'error':str(exc)})
                repair_input={'error':str(exc),'claims':[{'id':c.id,'statement':c.statement,'evidence_ids':c.evidence_ids} for c in result.claims],'candidates':[{k:v for k,v in c.model_dump().items() if k in ('candidate_id','claim_ids','requirement_ids','result_refs','atomic_fact_ids','problem_claim_ids','contribution_claim_ids','result_claim_ids','mechanism_steps','exception_boundaries')} for c in result.candidates],'allowed_evidence_ids':list(evidence),'allowed_requirement_ids':[r.requirement_id for r in target.requirements]}
                repair=call(stage+'_LINK_REPAIR',ReferenceRepair,repair_input,'只返回有误引用字段的patches，不返回完整Discovery。target_id必须已存在。claim仅可改evidence_ids；candidate的机制步骤用field+原始index修改claim_ids或drop=true删除整条。只修有错字段，不重写正确引用。candidate机制引用必须属于该候选claim_ids，证据编号不能写进claim_ids。不猜事实与证据的语义关联，无法确定的可选步骤删除。claim.evidence_ids至少保留一个真实支持来源；禁止通过refs=[]清空证据来修复归属问题。禁止新增实体、修改正文或状态。')
                repaired=apply_reference_patches(result,repair)
                removed=discard_unlinked_card_details(repaired)
                if removed:emit(stage,'unlinked_details_removed',{'details':removed})
                return validate_discovery(repaired,evidence,target.requirements,ctx,contributions)
        retrieval=retrieve(material,target.requirements,int(os.getenv('RESUME_RETRIEVAL_CHARS','18000')))
        for q in retrieval:
            for item in q['candidate_evidence']:
                evidence[item['source_ref']]=SourceEvidence(id=item['source_ref'],kind='wiki',repo=material['repo'],commit_sha='unknown',content_hash=sha256(item['content']),excerpt=item['content'],wiki_page_id=item['page_ref'],revision_status='unknown')
        emit('RETRIEVE','completed',{'requirement_ids':[r.requirement_id for r in target.requirements],'candidate_segments':sum(len(q['candidate_evidence']) for q in retrieval)})
        def source_pack():return [e.model_dump() for e in evidence.values() if e.kind!='wiki']
        discovery_instruction='先检查project_inventory的每个已映射页面机制，避免只采用README和用户优化；页面只是调查线索，不强制每页生成亮点。先独立于JD从项目全貌和Wiki发现互补工程主题，再映射岗位；用户优化只是其中一部分，不能取代原项目。按用户闭环追踪输入、调度/处理、状态存储、输出以及失败路径，材料没有的环节不补写；不同仓库按实际业务链路发现，不套Agent/RAG模板。最多32条原子claim，准确statement和evidence_ids，默认support=insufficient待独立核验。输出紧凑JSON：claim发现时仅写id/statement/evidence_ids及确有依据的非默认字段；省略空数组、空字符串、null和默认状态字段，程序会补齐。候选只填有依据的可选字段，不重复在mechanism/reason/步骤里复述同一段事实。保留所有重要机制，不为省字将不同事实混成一条。候选保存有依据的业务约束problem及problem_claim_ids、atomic_fact_ids、mechanism_steps有序处理步骤（明确触发条件、输入、状态转换和输出，每条描述实际动作而非模块名）、exception_boundaries失败/拒绝/降级边界；每一步text绑定本候选claim_ids。贡献claim与上游分开，结果claim与结果来源result_refs分开；无依据字段留空，不猜作者动机。缺失关键调用连接写investigation_questions（最多3问，含代码符号英文别名）和已有线索source_paths，不生成路径；gaps区分缺代码连接与缺个人/测试材料。'
        discovery=call('DISCOVER',Discovery,{'project_inventory':[{k:v for k,v in row.items() if k!='mechanisms'} for row in inventory],'product':product.model_dump(),'facts':compact,'job_evidence':[{k:v for k,v in packet.items() if k in ('requirement_id','question','candidate_evidence','status')} for packet in retrieval],'requirements':target.model_dump(),'sources':source_pack(),'allowed_evidence_ids':list(evidence)},discovery_instruction+' evidence_ids只能逐字复制facts.source_ref、job_evidence.source_ref或allowed_evidence_ids；fact-1不是证据ID。candidate.claim_ids只能引用本次claims已有id，不得引用未输出的claim。')
        discovery=accept_discovery(discovery,'DISCOVER')
        gap_requirements=[]
        for card in discovery.candidates:
            questions=card.investigation_questions or card.gaps
            if not questions:continue
            terms=list(dict.fromkeys(re.findall(r'[A-Za-z_][A-Za-z0-9_]{2,}', ' '.join(questions))))[:12]
            if not terms:terms=[card.title]
            gap_requirements.append(Requirement(requirement_id=card.candidate_id,description=card.title,origin=ctx.target_origin,question='；'.join(questions),search_terms=terms))
        gap_retrieval=retrieve(material,gap_requirements,6000) if gap_requirements else []
        gap_refs={row['source_ref'] for packet in gap_retrieval for row in packet['candidate_evidence']}
        emit('GAP_RETRIEVE','completed',{'results':gap_retrieval,'budget_chars':6000})
        source_ledger={'paths':set(),'chars':0}
        source_trace=source_investigation(reader,material,evidence,target.requirements,cards=discovery.candidates,ledger=source_ledger)
        emit('SOURCE','completed',{'reads':source_trace,'calls':reader.calls})
        if gap_refs or any(e.kind in ('code','test_source') for e in evidence.values()):
            enriched=call('CANDIDATE_ENRICH',Discovery,{'previous':discovery.model_dump(),'sources':source_pack()+[evidence[i].model_dump() for i in sorted(gap_refs)],'requirements':target.model_dump()},discovery_instruction+'根据新证据补全、增加、拆分或纠正候选。旧claim的statement不得原地改写；纠正使用新ID及supersedes_claim_id，候选拆分或替代使用新ID及supersedes_candidate_ids。无替代关联不得丢失旧项；总数仍最多32。新增claim优先描述输入条件、分支判断、状态转换、拒绝/退出路径和输出，不能以类型/函数名称列表替代机制。卡片应以当前已读机制为主线，旧Wiki未接通步骤列gaps，不继续作为现有链路描述。')
            discovery_history.append(discovery_transition(discovery,enriched,evidence))
            discovery=accept_discovery(enriched,'CANDIDATE_ENRICH')
        def verify(discovery,stage):
            used={i for c in discovery.claims for i in c.evidence_ids}
            # Only cited Wiki plus all bounded code evidence; no whole Wiki duplication.
            pack=[e.model_dump() for i,e in evidence.items() if i in used or e.kind!='wiki']
            checked=call(stage,Verification,{'claims':[{k:v for k,v in c.model_dump().items() if k in ('id','statement','evidence_ids','contribution_id')} for c in discovery.claims],'sources':pack,'contributions':list(contributions.values()),'context':ctx.model_dump()},'独立核对每个原claim的实际语义是否被原文支持，不沿用发现阶段的默认不足状态。只判断所写陈述，不要求陈述以外的参数、并发或测试证明：supported/partial/insufficient/contradicted并给reason。保持id和statement，允许修正证据关联及独立状态；没有调用连接不能标integrated，旧Wiki与源码冲突标contradicted。测试定义不等于通过，计划不等于实现。support只判断statement是否被原文支持，与个人贡献、测试报告和版本未知独立；原文明确描述项目能力可supported+upstream+validation_level=unknown，缺个人贡献/测试不能单独判insufficient，不提升源码核验级别。源码冲突仍contradicted。每条必须独立填写implementation_state和attribution，不能因Wiki版本未知就把明确描述现有能力的实现状态留unknown；Wiki明确描述当前能力可implemented+upstream，但validation_level仍unknown并说明版本限制。仅有规划/类型定义或内容不明确时保留proposed/unknown；禁止自动将所有supported提升implemented。只能引用提供的证据，不能新建claim；用户口述已完成可user_confirmed，有独立diff/报告可user_evidenced。')
            original={c.id:c.statement for c in discovery.claims}
            if {c.id:c.statement for c in checked.claims}!=original:raise ProviderError('语义核验篡改claim集合或原陈述','resume_contract')
            invalid=[];errors=[]
            for c in checked.claims:
                capped=bound_attribution(c,contributions,evidence)
                if capped:emit(stage,'attribution_capped',capped)
                try:check_claims([c],evidence,ctx,contributions)
                except ValueError as exc:invalid.append(c);errors.append({'claim_id':c.id,'error':str(exc)})
            if invalid:
                refs={i for c in invalid for i in c.evidence_ids}
                repaired=call(stage+'_FACT_REPAIR',Verification,{'claims':[c.model_dump() for c in invalid],'errors':errors,'sources':[e.model_dump() for i,e in evidence.items() if i in refs],'contributions':list(contributions.values())},'只修复这些claim的证据关联、支持/实现/归属/验证状态，不改id或statement。用户提议/未指明完成的材料不等于确认已实现，缺当前贡献ID时不能user_confirmed/user_evidenced。Wiki支持与源码验证分开，不能推断测试通过。只返回所列claim；没有证据降为partial/insufficient/unknown，不造事实。')
                if {c.id:c.statement for c in repaired.claims}!={c.id:c.statement for c in invalid}:raise ProviderError('事实修复篡改原陈述/集合','resume_contract')
                replacements={c.id:c for c in repaired.claims}
                checked.claims=[replacements.get(c.id,c) for c in checked.claims]
            check_claims(checked.claims,evidence,ctx,contributions);return {c.id:c for c in checked.claims}
        claims=verify(discovery,'CLAIM_VERIFY');candidates={c.candidate_id:c for c in discovery.candidates}
        def select(stage):
            eligible=[c.candidate_id for c in candidates.values() if any(claims[i].support=='supported' and claims[i].implementation_state=='implemented' and (ctx.output_mode!='personal_resume' or claims[i].attribution in ('user_confirmed','user_evidenced')) for i in c.claim_ids)]
            def fill_unknown(choice):
                missing_reasons=set(candidates)-set(choice.selected_ids)-set(choice.omitted)
                for cid in sorted(missing_reasons):choice.omitted[cid]='模型未提供舍弃依据，待人工复核'
                if missing_reasons:emit(stage,'omission_reason_unknown',{'candidate_ids':sorted(missing_reasons)})
                missing=[r.requirement_id for r in target.requirements if r.requirement_id not in {c.requirement_id for c in choice.coverage}]
                if missing:
                    choice.coverage.extend(Coverage(requirement_id=i,status='unknown',reason='模型未提供该职责覆盖判断，系统明确记录未知') for i in missing)
                    emit(stage,'coverage_unknown',{'requirement_ids':missing})
                return choice
            if not eligible:
                emit(stage,'no_eligible_candidates',{'claims':[{'id':c.id,'support':c.support,'implementation_state':c.implementation_state,'attribution':c.attribution} for c in claims.values()]})
                raise ProviderError('没有满足事实、实现状态及归属要求的候选；已停止拟稿，请检查核验记录或补充材料','resume_no_candidates')
            choice=call(stage,Choice,{'eligible_ids':eligible,'project_spine':[c.model_dump() for c in project_spine(claims).values()],'candidates':[c.model_dump() for c in candidates.values() if c.candidate_id in eligible],'claims':[c.model_dump() for c in claims.values() if any(c.id in candidates[i].claim_ids for i in eligible) and c.support=='supported' and c.implementation_state=='implemented'],'requirements':target.model_dump(),'output_mode':ctx.output_mode,'selection_policy':('按项目工程价值选题，上游能力可直接入选；缺少个人贡献或量化成果不是舍弃理由。只可因岗位不相关、主题重复或机制信息不足舍弃。' if ctx.output_mode=='project_reference' else '仅选择绑定当前确认个人贡献的主题，不把上游能力视作个人完成。')},'严格遵循selection_policy。独立于候选发现进行选题，选1–4条有支持的已实现claim；个人模式需确认个人贡献，可零条并提出缺口。不按关键词数量排序，综合岗位、工程深度、归属、证据、互补性。同链路合并，上游与优化状态不混。记录每个候选采纳/舍弃理由、每项职责覆盖direct/partial/unknown/not_applicable及下一调查问题。未找到不是不存在，证据不足记unknown，not_applicable须解释业务场景为何不需该能力。逐个比较岗位相关性、工程深度、事实依据、个人归属和重复性，理由不得只给关键词命中。outline保证整项目主线。每个采纳/舍弃理由说明岗位能力与实际机制的连接，不以缺关键词排除。记忆原有能力和用户优化若处理同一链路，应共同选入并建议合并，不混淆各自状态和归属。')
            fill_unknown(choice)
            try:validate_choice(choice,candidates,claims,target.requirements,ctx.output_mode)
            except ValueError as exc:
                emit(stage,'selection_repair',{'error':str(exc),'eligible_ids':eligible})
                choice=call(stage+'_SELECTION_REPAIR',Choice,{'previous':choice.model_dump(),'eligible_ids':eligible,'claims':[c.model_dump() for c in claims.values()],'requirements':target.model_dump()},'只修复选题契约：selected_ids只能来自eligible_ids，可空；不得改变claim支持或实现状态。移除无资格主题并调整覆盖及理由，不虚构事实。')
                fill_unknown(choice)
                validate_choice(choice,candidates,claims,target.requirements,ctx.output_mode)
            return choice
        choice=select('SELECT');metrics=metric_records(material)
        skill=(ROOT/'SKILL.md').read_text(encoding='utf-8')+'\n'+(ROOT/'references'/'writing-template.md').read_text(encoding='utf-8')
        reviews=[];issues=[];reselected=False;draft=None;blocking_parts=set()
        for iteration in range(2):
            cards,writable=writing_pack(candidates,claims,choice)
            spine=project_spine(claims)
            prose_facts={**spine,**writable}
            if not writable:raise ProviderError('选中主题没有可写事实，已停止空稿生成','resume_no_candidates')
            try:
                draft=call('WRITE',ResumeDraft,{'context':ctx.model_dump(),'project_spine':{'usage':'项目简介可引用；亮点禁止扩展未选主题','claim_ids':list(spine)},'job_focus':[{'requirement_id':r.requirement_id,'description':r.description,'priority':r.priority,'origin':r.origin} for r in target.requirements if any(r.requirement_id in c['requirement_ids'] for c in cards)],'choice':{'selected_ids':choice.selected_ids},'writing_constraints':{'max_bullets':min(4,len(choice.selected_ids)),'each_candidate_once':True,'intro_target_chars':[60,130],'bullet_target_chars':[60,140]},'candidates':cards,'claims':[c.model_dump() for c in prose_facts.values()],'metrics':[m.model_dump() for m in metrics.values() if m.contribution_id in {c.contribution_id for c in writable.values() if c.contribution_id}],'previous':draft.model_dump() if draft else None,'fix':issues,'review_actions':{category:[{'issue':f['issue'],'part_ids':f.get('part_ids',[]),'claim_ids':f.get('claim_ids',[])} for review in reviews for perspective in review['perspectives'] for f in perspective['feedback'] if f['category']==category] for category in ('expression','fact_attribution','mechanism_missing','candidate_omission','needs_evidence')}},skill+'\n首轮根据HR选题和已核验机制卡片统一写作，按同一业务链路去重，保留互补机制。第二轮只根据上一版正文与独立双视角意见修订一次。简介可以使用project_spine中的已核验项目主线事实，技术亮点和成果只消费已选机制卡片和支持claim，job_focus仅指导表达重点，不作为项目实现证据；problem/reason是选题解释，不是作者动机证据。按业务约束—关键机制—边界处理组织简洁正文，不能把模块存在写成已接通链路。无已映射步骤时只写原子事实，不补因果。返回结构化中文草稿，不输出Markdown。简介及每条核心断言绑定claim_ids，不新增解释；条目绑定候选/贡献/指标。成果可null，不强制数字。计划、缺证据、未来方向放questions/limitations。参考稿只说明项目能力，不能本人主导；个人稿亮点必须有确认贡献，无贡献可空。正文数字只用正确指标含义/单位/样本/环境及用户来源，不把配置阈值写性能效果。通常每条1–2句，保留有价值的边界条件。')
            except ProviderError as exc:
                if iteration==0 or exc.code!='resume_budget':raise
                issues.append('修订预算已耗尽，保留首稿和待复核意见，未完成最终修订')
                emit('REVISION_STOP','budget_exhausted',{'reason':str(exc),'retained':'reviewed_first_draft'})
                iteration=0
                break
            if draft.output_mode!=ctx.output_mode:raise ProviderError('输出类型与输入不一致','resume_contract')
            issues=check_draft(draft,prose_facts,candidates,choice,metrics,contributions)
            if iteration==1:
                blocking_parts=set()
                emit('REVISION_CHECK','completed',{'issues':issues,'model_reviewed':False})
                break
            perspectives=[];omissions=[];blocking_parts=set();fact_repairs=set()
            review_facts={i:c for i,c in claims.items() if c.support=='supported' and c.implementation_state=='implemented'}
            review_cards=[writing_pack({cid:c},claims,Choice(selected_ids=[cid],reasons={}))[0][0] for cid,c in candidates.items()]
            for role in ('HR','TECHNICAL'):
                review_refs={i for c in review_facts.values() for i in c.evidence_ids}
                result=call('REVIEW_'+role,QualityReview,{'draft':draft.model_dump(),'claims':[c.model_dump() for c in review_facts.values()],'claim_limits':[{'id':i,'support':c.support,'implementation_state':c.implementation_state,'attribution':c.attribution} for i,c in claims.items() if i not in review_facts],'candidates':review_cards,'choice':{'selected_ids':choice.selected_ids,'coverage':[c.model_dump() for c in choice.coverage]},'requirements':target.model_dump(),'evidence':[evidence[i].model_dump() for i in review_refs if i in evidence] if role=='TECHNICAL' else []},'只做'+role+'独立评审，不读取其他意见。参考稿归属为项目上游能力，仓库地址不能证明个人贡献；没有个人经历不能否定上游事实。unknown/proposed/in_progress和用户提议不能作为已实现架构或候选遗漏证据。候选机制描述是待核验线索，只有supported且implemented的claim可支持正文。按当前角色模板的职责独立评审。无证据用mechanism_missing或fact_attribution提出，不自动补写。分类：expression只改表达；candidate_omission只在已提供材料证明重要主题未发现时提出，不创造事实；mechanism_missing指出候选哪条关键连接缺失；fact_attribution指事实或归属错误，若claim本身有误同时列claim_ids供局部重核，blocking=true列part_ids（intro/outcome/条目id）；needs_evidence为无法内部解决的用户材料缺口。important_omission是历史兼容分类，只引用已知候选。路径只能用已提供线索。风格问题不blocking，没有成果不是失败。supported不是认证。')
                for f in result.feedback:
                    if not set(f.evidence_ids)<=set(evidence) or not set(f.jd_requirement_ids)<={r.requirement_id for r in target.requirements}:
                        raise ProviderError('评审引用未知证据或岗位职责；未采用该意见','resume_contract')
                    if f.category=='fact_attribution':
                        f.blocking=True
                        if not f.part_ids:f.part_ids=['intro','outcome',*[b.id for b in draft.bullets]]
                        if not set(f.claim_ids)<=set(claims):issues.append('评审引用未知事实')
                        else:fact_repairs.update(f.claim_ids)
                    if f.blocking:
                        available_parts={'intro','outcome'}|{b.id for b in draft.bullets}
                        if not set(f.part_ids)<=available_parts:issues.append('评审引用未知正文段落')
                        blocking_parts.update(set(f.part_ids)&available_parts)
                        issues.append(f.issue)
                    if f.category in ('expression','fact_attribution'):issues.append(f.issue)
                    elif f.category in ('important_omission','candidate_omission','mechanism_missing'):
                        if any(i not in candidates for i in f.candidate_ids):issues.append('评审引用未知候选')
                        elif f.category=='candidate_omission' and not f.candidate_ids:omissions.append(f)
                        elif any(i not in choice.selected_ids for i in f.candidate_ids):omissions.append(f)
                        elif f.category=='mechanism_missing':omissions.append(f)
                        elif f.candidate_ids:issues.append(f.issue)
                        elif len(draft.questions)<3:draft.questions.append(f.issue)
                    elif len(draft.questions)<3:draft.questions.append(f.issue)
                perspectives.append({'perspective':role.lower(),**result.model_dump()})
                if not result.approved and not any(f.category in ('expression','important_omission','candidate_omission','mechanism_missing','fact_attribution') for f in result.feedback):
                    emit('REVISION_STOP','no_actionable_feedback',{'perspective':role,'reason':'无可执行意见，不仅因低分或未通过标记重复写作'})
            reviews.append({'iteration':iteration+1,'issues':list(dict.fromkeys(issues)),'perspectives':perspectives})
            if fact_repairs and iteration==0:
                claims.update(verify(Discovery(claims=[claims[i] for i in sorted(fact_repairs)],candidates=[]),'CLAIM_VERIFY_FEEDBACK'))
                if not omissions:choice=select('RESELECT_FACT')
                issues.append('按事实/归属反馈局部核验后重写')
            if omissions and iteration==0:
                reselected=True;paths=[p for f in omissions for p in f.paths]
                affected={i for f in omissions for i in f.candidate_ids}
                investigation_cards=[c.model_copy(update={'investigation_questions':[f.issue for f in omissions if c.candidate_id in f.candidate_ids or not f.candidate_ids][:3],'source_paths':list(dict.fromkeys(c.source_paths+paths))[:4]}) for c in candidates.values() if c.candidate_id in affected or any(not f.candidate_ids for f in omissions)]
                extra=source_investigation(reader,material,evidence,target.requirements,paths,cards=investigation_cards,ledger=source_ledger);source_trace.extend(extra)
                if any(f.category in ('candidate_omission','mechanism_missing') for f in omissions):
                    incremental=call('DISCOVER_INCREMENTAL',Discovery,{'previous':discovery.model_dump(),'feedback':[f.model_dump() for f in omissions],'facts':compact,'sources':source_pack(),'requirements':target.model_dump()},discovery_instruction+'仅修复反馈所指缺失连接或一次遗漏发现。新增或纠正使用新ID；纠正claim使用supersedes_claim_id，拆分候选使用supersedes_candidate_ids。未替代旧项必须保留。同一机制不重复建主题。')
                    discovery_history.append(discovery_transition(discovery,incremental,evidence))
                    discovery=accept_discovery(incremental,'DISCOVER_INCREMENTAL');candidates={c.candidate_id:c for c in discovery.candidates}
                claims=verify(discovery,'CLAIM_VERIFY_RESELECT');choice=select('RESELECT')
                emit('RESELECT_RESULT','completed',{'selected_ids':choice.selected_ids,'reasons':[f.issue for f in omissions]});issues.append('根据补证后的重选重写')
            elif omissions:issues.extend('重选已达一次上限：'+f.issue for f in omissions)
            if not issues:break
        status='passed' if not issues else 'needs_review'
        if any(not p['approved'] and not p['feedback'] for r in reviews for p in r['perspectives']):status='needs_review'
        if any(f['category']=='needs_evidence' for r in reviews for p in r['perspectives'] for f in p['feedback']):status='needs_review'
        if any(v=='模型未提供舍弃依据，待人工复核' for v in choice.omitted.values()):status='needs_review'
        if ctx.output_mode=='personal_resume' and not draft.bullets:status='needs_review'
        # Unsafe mapped paragraphs are removed even if bounded review failed; safe parts survive.
        rejected=[]
        for b in list(draft.bullets):
            one=ResumeDraft(output_mode=draft.output_mode,project_intro=Prose(text=''),bullets=[b])
            bad=check_draft(one,prose_facts,candidates,choice,metrics,contributions)
            if bad or b.id in blocking_parts:draft.bullets.remove(b);rejected.append({'id':b.id,'issues':bad or ['语义评审阻断']})
        for field in ('project_intro','outcome'):
            p=getattr(draft,field)
            if p and p.text and (('intro' if field=='project_intro' else 'outcome') in blocking_parts or check_draft(ResumeDraft(output_mode=draft.output_mode,project_intro=p,bullets=[]),prose_facts,candidates,choice,metrics,contributions)):
                setattr(draft,field,Prose(text='') if field=='project_intro' else None);rejected.append({'part':field})
        if rejected:status='needs_review'
        if not draft.project_intro.text.strip() or not draft.bullets:status='needs_review'
        if ctx.output_mode=='personal_resume' and not draft.bullets and not draft.questions:
            draft.questions=['你实际修改或实现了哪个模块？','该改动解决了什么问题，与原项目基线有何不同？','是否有测试样本或报告可说明结果？']
        selected=[{'id':c.candidate_id,'title':c.title,'jd_relation':choice.reasons.get(c.candidate_id,''),'hr_value':c.reason,'interview_focus':'；'.join(s['text'] for s in writing_pack({c.candidate_id:c},claims,Choice(selected_ids=[c.candidate_id],reasons={}))[0][0]['mechanism_steps']) or '支持事实尚不足以说明关键机制，需复核','reason':choice.reasons.get(c.candidate_id,''),'source_refs':list(dict.fromkeys(i for cid in c.claim_ids for i in claims[cid].evidence_ids)),'state':'upstream_and_contribution_claims_separate','card':writing_pack({c.candidate_id:c},claims,Choice(selected_ids=[c.candidate_id],reasons={}))[0][0]} for c in candidates.values() if c.candidate_id in choice.selected_ids]
        prose_map=[{'part':getattr(p,'id','intro' if p is draft.project_intro else 'outcome'),'text':p.text,'claim_ids':p.claim_ids,'contribution_ids':p.contribution_ids,'metric_ids':p.metric_ids,'evidence_ids':list(dict.fromkeys(i for cid in p.claim_ids if cid in claims for i in claims[cid].evidence_ids))} for p in [draft.project_intro,*draft.bullets,*([draft.outcome] if draft.outcome else [])]]
        audit={'kind':'writing_review','mode':'skill_model','schema_version':VERSION,'generation_context':ctx.model_dump(),'status':status,'iterations':iteration+1,'final_model_reviewed':iteration==0,'writing_strategy':'single_writer_distinct_reviews','reviews':reviews,'trace':trace,'structured_draft':draft.model_dump(),'selection':{'selected':selected,'omitted':list(choice.omitted.values()),'outline':choice.outline,'project_value':product.model_dump()},'candidates':[c.model_dump() for c in candidates.values()],'choice':choice.model_dump(),'generated_claims':[c.model_dump() for c in claims.values()],'metrics':[m.model_dump() for m in metrics.values()],'source_evidence':[e.model_dump() for i,e in evidence.items() if e.kind!='wiki' or any(i in c.evidence_ids for c in claims.values())],'source_reads':source_trace,'project_spine_claim_ids':list(spine),'requirements':target.model_dump(),'requirement_coverage':[c.model_dump() for c in choice.coverage],'job_evidence':retrieval,'project_map':mapped,'mapping_inventory':inventory,'material_index':[{k:v for k,v in row.items() if k!='content'} for row in section_index(material)],'reselected':reselected,'rejected_prose':rejected,'questions':draft.questions[:3],'limits':draft.limitations,'harness':{'trace_id':h.trace_id,'calls':h.records,'usage':provider.usage if provider else [],'max_generation_calls':max_downstream},'skill_sha256':sha256(skill),'note':'源码存在、测试定义、用户贡献、运行效果分别记录；语义核验和同源双审不是人工认证。历史Wiki版本未知，不追认当前源码。'}
        audit['prose_claim_map']=prose_map
        audit['discovery_history']=discovery_history
        audit['theme_trace']=[{'candidate_id':cid,'title':card.title,
            'claim_ids':card.claim_ids,'evidence_ids':list(dict.fromkeys(ref for ident in card.claim_ids for ref in claims[ident].evidence_ids)),
            'selected':cid in choice.selected_ids,'selection_reason':choice.reasons.get(cid,choice.omitted.get(cid,'')),
            'final_bullet_ids':[b.id for b in draft.bullets if cid in b.candidate_ids],
            'review_feedback':[f for r in reviews for p in r['perspectives'] for f in p['feedback'] if cid in f.get('candidate_ids',[]) or set(card.claim_ids)&set(f.get('claim_ids',[]))]
            } for cid,card in candidates.items()]
        audit['fact_gate']=fact_gate(issues,rejected,reviews,iteration==0)
        audit['content_score']=reviewed_score(reviews,iteration==0)
        emit('RENDER','completed',{'status':status,'selected_ids':choice.selected_ids,'claim_ids':[c.id for c in claims.values()]})
        if status=='passed':h.save_stages(stage_cache)
        return render(draft),audit
    except ValueError as exc:
        emit('CONTRACT','failed',error=str(exc)[:200])
        error=ProviderError('事实/选题契约校验失败：'+str(exc)[:200],'resume_contract')
        error.trace_id=h.trace_id;error.stage_trace=trace;error.stage_calls=h.records
        raise error from exc
    except ProviderError as exc:
        emit('PIPELINE','failed',error=exc.code)
        exc.trace_id=h.trace_id;exc.stage_trace=trace;exc.stage_calls=h.records
        raise
    finally:
        if owned:reader.close()
        if provider:provider.close()
