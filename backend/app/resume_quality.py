"""Production quality pipeline: bounded investigation, source verification and mapped prose."""
import json
import os
import re
import time
from pathlib import Path
from .providers import ProviderError
from .source_reader import SourceReader, SourceEvidence, resolved, sha256, related_source_paths
from .resume_harness import Harness, GUARD, parse_json, digest
from .resume_contract import *
from .resume_prompts import compose, task_for_stage, validate_configuration

from .resume_revision import discovery_transition, fact_gate, reviewed_score, restore_verification_identity, discard_unlinked_card_details, apply_reference_patches

def material_evidence(material):
    ev={};repo=material.get('repo','');sha=material.get('commit','unresolved')
    def add(ident,kind,text,**kw):
        ev[ident]=SourceEvidence(id=ident,kind=kind,repo=repo,commit_sha='unknown' if kind=='wiki' else sha,content_hash=sha256(text),excerpt=text,revision_status='unknown' if kind=='wiki' else 'user_submitted',**kw)
    for c in material.get('user_optimizations',[]):add('optimization:'+c['id'],'user_statement',json.dumps(c,ensure_ascii=False))
    for e in material.get('user_materials',[]):add('user-material:'+e['id'],e.get('type','user_statement'),e['excerpt'])
    for e in material.get('experiments',[]):add('experiment:'+e['id'],'experiment',json.dumps(e['details'],ensure_ascii=False))
    for m in material.get('reported_metrics',[]):add('reported-metric:'+m['id'],'user_statement',json.dumps(m,ensure_ascii=False))
    for i in material.get('improvement_states',[]):add('improvement-state:'+i['id'],'user_statement',json.dumps(i,ensure_ascii=False))
    return ev

def metric_records(material):
    records={e['id']:Metric(id=e['id'],name=e['details']['metric'],value=e['details']['modified_value'],unit=e['details']['unit'],baseline=e['details']['baseline_value'],sample_scope=e['details']['dataset_description'],environment=e['details']['conditions'],measurement_method='用户提交的对照实验',state='user_reported',experiment_id=e['id'],contribution_id=e['contribution_id']) for e in material.get('experiments',[])}
    for m in material.get('reported_metrics',[]):
        records[m['id']]=Metric(id=m['id'],name=m['name'],value=m['value'],unit=m['unit'],baseline=m.get('baseline'),sample_scope=m.get('sample_size') or '样本未提供',environment='用户提供，未独立核验',measurement_method=m.get('method') or '方法未提供',state='user_reported',user_statement_id='reported-metric:'+m['id'],contribution_id=m.get('contribution_id'),change_type=m['change_type'])
    return records

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
    max_downstream=min(24,max(8,int(os.getenv('RESUME_GENERATION_CALLS','20'))))
    h=Harness(chat,model=provider.base+'|'+provider.model if provider else 'injected',cache_dir=cache_directory() if provider else None,max_calls=max_downstream,check_active=material.get('_check_active'),structured_output=True)
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
            reserve=0 if stage in ('WRITE','REVIEW_HR','REVIEW_TECHNICAL') else 3
            if downstream>=max_downstream-reserve:raise ProviderError('本次生成请求次数达到上限，不是模型账户余额不足','resume_budget')
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
                if issubclass(schema,Discovery) and isinstance(parsed,dict):
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
                if downstream>max_downstream-reserve:raise ProviderError('保留写作和双审预算，停止修复','resume_budget')
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
        from .shared_analysis import get_or_build_analysis
        pack=get_or_build_analysis(snapshot,material,ctx,reader,call,emit,model=h.model,check_active=material.get('_check_active'),retriever=material.get('_code_retriever'))
        product=pack.product;target=pack.target;discovery=pack.discovery.model_copy(deep=True)
        evidence={e.id:e for e in pack.evidence};evidence.update(material_evidence(material))
        contributions={c['id']:c for c in material.get('user_optimizations',[]) if c['state']!='abandoned'}
        retrieval=pack.retrieval;source_trace=pack.reads
        if contributions:
            originals={c.id:(c.statement,c.evidence_ids,c.attribution) for c in discovery.claims}
            discovery=call('CONTRIBUTION_BIND',Discovery,{'project':discovery.model_dump(),'contributions':list(contributions.values()),'sources':[e.model_dump() for e in evidence.values()],'requirements':target.model_dump()},'仅关联当前用户贡献或添加有用户材料支持的个人动作Claim；原项目能力不可归为个人。保持原claim集合和陈述；新增个人claim用独立ID，保留每个候选与原JD关联。未实现方向不能作为已实现动作。')
            current={c.id:(c.statement,c.evidence_ids,c.attribution) for c in discovery.claims}
            if any(current.get(i)!=v for i,v in originals.items()):raise ProviderError('贡献关联改变了原项目事实；个人改动必须使用独立Claim','resume_contract')
            for c in discovery.claims:bound_attribution(c,contributions,evidence)
            validate_discovery(discovery,evidence,target.requirements,ctx,contributions)
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
        claims=verify(discovery,'CLAIM_VERIFY_CONTRIBUTION') if contributions else {c.id:c for c in discovery.claims};candidates={c.candidate_id:c for c in discovery.candidates}
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
        reviews=[];issues=[];reselected=False;draft=None;blocking_parts=set();score_actions=[];score_history=[];final_model_reviewed=False
        completed_iterations=0
        for iteration in range(2):
            if max_downstream-downstream<3:
                if draft is None:raise ProviderError('剩余预算不足以完成写作和双审','resume_budget')
                issues.append('修订预算不足，保留已审稿');break
            cards,writable=writing_pack(candidates,claims,choice)
            spine=project_spine(claims)
            prose_facts={**spine,**writable}
            if not writable:raise ProviderError('选中主题没有可写事实，已停止空稿生成','resume_no_candidates')
            try:
                draft=call('WRITE',ResumeDraft,{'original_jd':material.get('jd',''),'sources':[evidence[i].model_dump() for i in dict.fromkeys(ref for c in prose_facts.values() for ref in c.evidence_ids) if i in evidence],'context':ctx.model_dump(),'project_spine':{'usage':'项目简介可引用；亮点禁止扩展未选主题','claim_ids':list(spine)},'job_focus':[{'requirement_id':r.requirement_id,'description':r.description,'priority':r.priority,'origin':r.origin} for r in target.requirements if any(r.requirement_id in c['requirement_ids'] for c in cards)],'choice':choice.model_dump(),'selected_optimizations':material.get('improvement_states',[]),'previous_saved_resume':material.get('previous_resume',''),'score_actions':score_actions,'writing_constraints':{'max_bullets':min(4,len(choice.selected_ids)),'each_candidate_once':True,'intro_target_chars':[60,130],'bullet_target_chars':[60,140]},'candidates':cards,'claims':[c.model_dump() for c in prose_facts.values()],'metrics':[m.model_dump() for m in metrics.values() if m.contribution_id in {c.contribution_id for c in writable.values() if c.contribution_id}],'previous':draft.model_dump() if draft else None,'fix':list(dict.fromkeys(issues)),'review_actions':{category:[{'issue':f['issue'],'part_ids':f.get('part_ids',[]),'claim_ids':f.get('claim_ids',[])} for review in reviews for perspective in review['perspectives'] for f in perspective['feedback'] if f['category']==category] for category in ('expression','fact_attribution','mechanism_missing','candidate_omission','needs_evidence')}},skill+'\n已选优化方向是用户补充依据，结合原项目和已保存简历重写；未选择方向不作为新增优化。原简历不是事实来源，仍需当前证据支持。选中不等于实现，not_started/in_progress仅放questions或limitations中作为计划；user_reported_done也不是测试认证或个人贡献证明。首轮根据HR选题和已核验机制卡片统一写作，按同一业务链路去重，保留互补机制。第二轮只根据上一版正文与独立双视角意见修订一次。简介可以使用project_spine中的已核验项目主线事实，技术亮点和成果只消费已选机制卡片和支持claim，job_focus仅指导表达重点，不作为项目实现证据；problem/reason是选题解释，不是作者动机证据。按业务约束—关键机制—边界处理组织简洁正文，不能把模块存在写成已接通链路。无已映射步骤时只写原子事实，不补因果。返回结构化中文草稿，不输出Markdown。简介及每条核心断言绑定claim_ids，不新增解释；条目绑定候选/贡献/指标。成果可null，不强制数字。计划、缺证据、未来方向放questions/limitations。参考稿只说明项目能力，不能本人主导；个人稿亮点必须有确认贡献，无贡献可空。正文数字只用正确指标含义/单位/样本/环境及用户来源，不把配置阈值写性能效果。通常每条1–2句，保留有价值的边界条件。')
            except ProviderError as exc:
                if iteration==0 or exc.code!='resume_budget':raise
                issues.append('修订预算已耗尽，保留首稿和待复核意见，未完成最终修订')
                emit('REVISION_STOP','budget_exhausted',{'reason':str(exc),'retained':'reviewed_first_draft'})
                iteration=0
                break
            completed_iterations=iteration+1
            if draft.output_mode!=ctx.output_mode:raise ProviderError('输出类型与输入不一致','resume_contract')
            issues=check_draft(draft,prose_facts,candidates,choice,metrics,contributions)
            final_model_reviewed=False
            score_actions=[]
            perspectives=[];omissions=[];blocking_parts=set();fact_repairs=set()
            review_facts={i:c for i,c in claims.items() if c.support=='supported' and c.implementation_state=='implemented'}
            review_cards=[writing_pack({cid:c},claims,Choice(selected_ids=[cid],reasons={}))[0][0] for cid,c in candidates.items()]
            review_draft=draft.model_dump();review_hash=digest(review_draft)
            for role in ('HR','TECHNICAL'):
                review_refs={i for c in review_facts.values() for i in c.evidence_ids}
                try:
                    result=call('REVIEW_'+role,QualityReview,{'output_mode':ctx.output_mode,'review_policy':{'missing_personal_contribution_blocks':ctx.output_mode=='personal_resume','missing_metrics_blocks':False},'draft':review_draft,'claims':[c.model_dump() for c in review_facts.values()],'claim_limits':[{'id':i,'support':c.support,'implementation_state':c.implementation_state,'attribution':c.attribution} for i,c in claims.items() if i not in review_facts],'candidates':review_cards,'choice':{'selected_ids':choice.selected_ids,'coverage':[c.model_dump() for c in choice.coverage]},'requirements':target.model_dump(),'evidence':[evidence[i].model_dump() for i in review_refs if i in evidence] if role=='TECHNICAL' else []},'只做'+role+'独立评审，不读取其他意见。参考稿归属为项目上游能力，仓库地址不能证明个人贡献；没有个人经历不能否定上游事实。unknown/proposed/in_progress和用户提议不能作为已实现架构或候选遗漏证据。候选机制描述是待核验线索，只有supported且implemented的claim可支持正文。按当前角色模板的职责独立评审。无证据用mechanism_missing或fact_attribution提出，不自动补写。分类：contribution_gap专指缺少用户个人贡献材料；project_reference下只能作为非阻断提醒，不能要求把上游写成个人负责。fact_attribution必须是正文实际包含错误事实或虚假归属，不能用来表示没有个人经历。不要因为底层claim包含额外内容就否定正文中已收窄且有依据的陈述。expression只改表达；candidate_omission只在已提供材料证明重要主题未发现时提出，不创造事实；mechanism_missing指出候选哪条关键连接缺失；fact_attribution指事实或归属错误，若claim本身有误同时列claim_ids供局部重核，blocking=true列part_ids（intro/outcome/条目id）；needs_evidence为无法内部解决的用户材料缺口。important_omission是历史兼容分类，只引用已知候选。路径只能用已提供线索。风格问题不blocking，没有成果不是失败。supported不是认证。')
                except ProviderError as exc:
                    if exc.code != "resume_budget":raise
                    issues.append("双视角评审预算不足，当前稿待复核")
                    emit("REVISION_STOP","review_budget_exhausted",{"iteration":iteration+1})
                    break
                owned=('role_fit','project_spine','readability') if role=='HR' else ('engineering_depth','important_coverage')
                valid_parts={'intro','outcome'}|{b.id for b in draft.bullets}
                for dimension,rating in result.scores.items():
                    if dimension not in owned or rating.score>=3:continue
                    if rating.suggested_action.strip() and set(rating.part_ids)<=valid_parts:
                        action={'dimension':dimension,'reason':rating.reason,'action':rating.suggested_action,'part_ids':rating.part_ids,
                                'constraint':'仅据已有事实调整表达；缺失实现或证据只能保留缺口，不能补造'}
                        existing=next((a for a in score_actions if a['action']==action['action'] and a['part_ids']==action['part_ids']),None)
                        if existing:existing['dimensions'].append(dimension)
                        else:score_actions.append({**action,'dimensions':[dimension]})
                        issues.append('评分改进：'+rating.suggested_action)
                for f in result.feedback:
                    f.part_ids=list(dict.fromkeys('intro' if p=='project_intro' else p for p in f.part_ids))
                    if f.category=='contribution_gap' and ctx.output_mode=='project_reference':
                        f.blocking=False
                        emit('REVIEW_POLICY','advisory_only',{'perspective':role,'issue':f.issue,'reason':'项目参考稿允许上游能力；缺个人贡献仅为后续个人简历提醒'})
                        continue
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
                if not result.approved and not score_actions and not any(f.category in ('expression','important_omission','candidate_omission','mechanism_missing','fact_attribution') for f in result.feedback):
                    emit('REVISION_STOP','no_actionable_feedback',{'perspective':role,'reason':'无可执行意见，不仅因低分或未通过标记重复写作'})
            reviews.append({'iteration':iteration+1,'issues':list(dict.fromkeys(issues)),'perspectives':perspectives})
            final_model_reviewed=len(perspectives)==2
            current_score=reviewed_score([reviews[-1]],final_model_reviewed)
            current_score['draft_hash']=review_hash
            score_history.append({'iteration':iteration+1,'draft_hash':review_hash,'score':current_score,'actions':list(score_actions)})
            if iteration==1 or not final_model_reviewed:
                issues.extend("修订后仍缺机制或主题："+f.issue for f in omissions)
                break
            # Optional refinement must not discard an already written, reviewed draft.
            previous_claims={k:v.model_copy(deep=True) for k,v in claims.items()}
            previous_candidates={k:v.model_copy(deep=True) for k,v in candidates.items()}
            previous_choice=choice.model_copy(deep=True)
            try:
                if fact_repairs and iteration==0:
                    claims.update(verify(Discovery(claims=[claims[i] for i in sorted(fact_repairs)],candidates=[]),'CLAIM_VERIFY_FEEDBACK'))
                    if not omissions:choice=select('RESELECT_FACT')
                    issues.append('按事实/归属反馈局部核验后重写')
                if omissions and iteration==0:
                    if not contributions and pack.supplemental_rounds==0 and max_downstream-downstream>=6 and any(f.category in ('mechanism_missing','candidate_omission') for f in omissions):
                        from .shared_analysis import extend_analysis
                        pack=extend_analysis(pack,omissions,material,ctx,reader,call,emit,material.get('_check_active'),material.get('_code_retriever'))
                        discovery=pack.discovery.model_copy(deep=True);claims={c.id:c for c in discovery.claims};candidates={c.candidate_id:c for c in discovery.candidates}
                        evidence.update({e.id:e for e in pack.evidence});source_trace=pack.reads
                    reselected=True
                    choice=select('RESELECT')
                    issues.extend('重选或保留机制缺口：'+f.issue for f in omissions)
                    emit('RESELECT_RESULT','completed',{'selected_ids':choice.selected_ids,'analysis_pack_id':pack.analysis_pack_id,'remaining_gaps':[f.issue for f in omissions]})
            except (ProviderError,ValueError) as error:
                if isinstance(error,ProviderError) and error.code not in ('resume_contract','resume_budget','resume_model_truncated','resume_model_error'):
                    raise
                claims=previous_claims;candidates=previous_candidates;choice=previous_choice
                # Unresolved factual objections also block any other paragraph citing that claim.
                for part_id,part in [('intro',draft.project_intro),('outcome',draft.outcome)]+[(b.id,b) for b in draft.bullets]:
                    if part and set(part.claim_ids)&fact_repairs:blocking_parts.add(part_id)
                message='局部核验或修订未完成，保留未受影响正文；相关事实段落待补证：'+str(error)[:240]
                issues.append(message)
                if len(draft.questions)<3:draft.questions.append(message)
                final_model_reviewed=False
                emit('REFINEMENT_STOP','needs_review',{'reason':message,'blocked_parts':sorted(blocking_parts)})
                break
            if not issues:break
        iteration=completed_iterations-1
        status='passed' if not issues and not pack.gaps else 'needs_review'
        if any(not p['approved'] for r in reviews[-1:] for p in r['perspectives']):status='needs_review'
        if any(f['category']=='needs_evidence' for r in reviews[-1:] for p in r['perspectives'] for f in p['feedback']):status='needs_review'
        if not final_model_reviewed or (score_history and score_history[-1]['score'].get('threshold_met') is False):status='needs_review'
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
        audit={'kind':'writing_review','mode':'skill_model','schema_version':VERSION,'generation_context':ctx.model_dump(),'status':status,'iterations':iteration+1,'final_model_reviewed':final_model_reviewed,'writing_strategy':'single_writer_distinct_reviews','reviews':reviews,'trace':trace,'structured_draft':draft.model_dump(),'selection':{'selected':selected,'omitted':list(choice.omitted.values()),'outline':choice.outline,'project_value':product.model_dump()},'candidates':[c.model_dump() for c in candidates.values()],'choice':choice.model_dump(),'generated_claims':[c.model_dump() for c in claims.values()],'metrics':[m.model_dump() for m in metrics.values()],'source_evidence':[e.model_dump() for i,e in evidence.items() if e.kind!='wiki' or any(i in c.evidence_ids for c in claims.values())],'source_reads':source_trace,'project_spine_claim_ids':list(spine),'requirements':target.model_dump(),'requirement_coverage':[c.model_dump() for c in choice.coverage],'job_evidence':retrieval,'analysis_pack_id':pack.analysis_pack_id,'analysis_identity':pack.identity,'analysis_gaps':pack.gaps,'reselected':reselected,'rejected_prose':rejected,'questions':draft.questions[:3],'limits':draft.limitations,'harness':{'trace_id':h.trace_id,'calls':h.records,'usage':provider.usage if provider else [],'max_generation_calls':max_downstream,'embedding_usage':[r for t in trace if t['stage']=='SHARED_ANALYSIS' for r in t['output_structure'].get('retrieval_usage',[])]},'skill_sha256':sha256(skill),'note':'源码存在、测试定义、用户贡献、运行效果分别记录；语义核验和同源双审不是人工认证。历史Wiki版本未知，不追认当前源码。'}
        audit['prose_claim_map']=prose_map
        audit['discovery_history']=discovery_history
        audit['theme_trace']=[{'candidate_id':cid,'title':card.title,
            'claim_ids':card.claim_ids,'evidence_ids':list(dict.fromkeys(ref for ident in card.claim_ids for ref in claims[ident].evidence_ids)),
            'selected':cid in choice.selected_ids,'selection_reason':choice.reasons.get(cid,choice.omitted.get(cid,'')),
            'final_bullet_ids':[b.id for b in draft.bullets if cid in b.candidate_ids],
            'review_feedback':[f for r in reviews for p in r['perspectives'] for f in p['feedback'] if cid in f.get('candidate_ids',[]) or set(card.claim_ids)&set(f.get('claim_ids',[]))]
            } for cid,card in candidates.items()]
        final_model_reviewed=final_model_reviewed and bool(score_history) and score_history[-1]['draft_hash']==digest(draft.model_dump())
        if not final_model_reviewed:status='needs_review';audit['status']=status
        audit['fact_gate']=fact_gate(issues,rejected,reviews[-1:],final_model_reviewed and not rejected)
        audit['content_score']=reviewed_score(reviews[-1:],final_model_reviewed and not rejected)
        audit['final_draft_hash']=digest(draft.model_dump())
        audit['content_score']['draft_hash']=score_history[-1]['draft_hash'] if score_history else None
        audit['content_score']['applies_to']='reviewed_revision' if iteration==1 else 'first_draft'
        if rejected:audit['content_score']['applies_to']='before_safety_filtering'
        audit['final_model_reviewed']=final_model_reviewed and not rejected
        audit['score_history']=score_history
        audit['score_comparison']={'before':score_history[0]['score'] if score_history else None,'after':score_history[-1]['score'] if iteration==1 and final_model_reviewed else None}
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
