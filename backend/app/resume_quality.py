"""Production quality pipeline: bounded investigation, source verification and mapped prose."""
import json
import os
import re
import time
from pathlib import Path
from .db import DATA
from .providers import ProviderError
from .source_reader import SourceReader, SourceEvidence, resolved, sha256
from .resume_harness import Harness, GUARD, chunks, spans, parse_json, digest
from .resume_contract import *

ALIASES={'agent':['智能体','orchestrator','编排','runtime'], 'memory':['记忆','上下文','context','召回','history'], '多轮':['session','历史','history','dialogue'], '恢复':['checkpoint','重试','retry','version','版本'], 'tool':['工具','capability','调用'], '记忆':['memory','context','history','compaction'], '编排':['agent','orchestrator','runtime','director'], '边界':['boundary','consent','permission'], '评测':['eval','test','monitor','log']}
def retrieve(material,requirements,budget=18000):
    """Sections/paragraphs with neighbors, title weighting and source diversity."""
    pages=material.get('_full_wiki_pages',material.get('wiki_pages',[]));results=[]
    per=budget//max(1,len(requirements));total=0
    for q in requirements:
        terms=set(t.lower() for t in q.search_terms if t.strip())
        for key,aliases in ALIASES.items():
            if any(key in t for t in terms):terms.update(aliases)
        ranked=[]
        for i,page in enumerate(pages):
            paragraphs=[p.strip() for p in re.split(r'\n\s*\n',page['content']) if p.strip()]
            section=page.get('title','')
            for j,p in enumerate(paragraphs):
                if p.startswith('#'):section=p.split('\n',1)[0]
                score=sum(2*(t in section.lower())+(t in p.lower()) for t in terms)
                if not score:continue
                # Long paragraphs use overlapping full-line windows, not half sentences.
                windows=[p] if len(p)<=2400 else ['\n'.join(p.splitlines()[k:k+16]) for k in range(0,len(p.splitlines()),12)]
                for window in windows:
                    if not window or len(window)>per:continue
                    neighbors='\n\n'.join(paragraphs[max(0,j-1):min(len(paragraphs),j+2)])
                    content=neighbors if len(neighbors)<=min(per,3000) else window
                    ranked.append((score,i,j,{'source_ref':f'wiki:{i}:paragraph:{j}','page_ref':f'wiki:{i}','section':section,'content':content,'paragraph':j,'file_paths':page.get('filePaths',[])}))
        ranked.sort(key=lambda r:(-r[0],r[1],r[2]));used=set();counts={};evidence=[];spent=0
        for _,i,j,item in ranked:
            if (i,j) in used or counts.get(i,0)>=2 or spent+len(item['content'])>per or total+len(item['content'])>budget:continue
            used.add((i,j));counts[i]=counts.get(i,0)+1;evidence.append(item);spent+=len(item['content']);total+=len(item['content'])
            if len(evidence)>=6:break
        results.append({'requirement_id':q.requirement_id,'question':q.question,'candidate_evidence':evidence,'status':'candidates_need_verification' if evidence else 'unknown'})
    return results

def material_evidence(material):
    ev={};repo=material.get('repo','');sha=material.get('commit','unresolved')
    def add(ident,kind,text,**kw):
        ev[ident]=SourceEvidence(id=ident,kind=kind,repo=repo,commit_sha='unknown' if kind=='wiki' else sha,content_hash=sha256(text),excerpt=text,revision_status='unknown' if kind=='wiki' else 'user_submitted',**kw)
    for i,p in enumerate(material.get('_full_wiki_pages',material.get('wiki_pages',[]))):
        add(f'wiki:{i}','wiki',p['content'],wiki_page_id=p.get('page_id',str(i)))
    for c in chunks(material):
        add(c['id'],'wiki',c['content'])
        for s in spans(c):add(s['id'],'wiki',s['content'])
    if material.get('overview'):add('overview','wiki',json.dumps(material['overview'],ensure_ascii=False))
    for c in material.get('user_optimizations',[]):add('optimization:'+c['id'],'user_statement',json.dumps(c,ensure_ascii=False))
    for e in material.get('user_materials',[]):add('user-material:'+e['id'],e.get('type','user_statement'),e['excerpt'])
    for e in material.get('experiments',[]):add('experiment:'+e['id'],'experiment',json.dumps(e['details'],ensure_ascii=False))
    return ev

def metric_records(material):
    return {e['id']:Metric(id=e['id'],name=e['details']['metric'],value=e['details']['modified_value'],unit=e['details']['unit'],baseline=e['details']['baseline_value'],sample_scope=e['details']['dataset_description'],environment=e['details']['conditions'],measurement_method='用户提交的对照实验',state='user_reported',experiment_id=e['id'],contribution_id=e['contribution_id']) for e in material.get('experiments',[])}

def source_investigation(reader,material,evidence,requirements,extra_paths=()):
    records=[];repo=material['repo'];sha=material['commit']
    if not resolved(sha) and not sha.startswith('archive-sha256:'):
        return [{'status':'unresolved','reason':'历史快照没有真实SHA，只使用Wiki线索，不追认源码核验'}]
    try:tree=reader.list_tree(repo,sha)
    except ProviderError as exc:return [{'status':'failed','error':exc.code,'reason':str(exc)}]
    paths=set(tree['paths']);terms=list({t for q in requirements for t in q.search_terms}|{a for key,values in ALIASES.items() if any(key in t.lower() for q in requirements for t in q.search_terms) for a in values})
    hints={p for page in material.get('_full_wiki_pages',[]) for p in page.get('filePaths',[]) if isinstance(p,str)}
    scored=[]
    for p in paths:
        if Path(p).suffix.lower() not in ('.py','.ts','.tsx','.js','.jsx','.go','.rs','.java','.md','.mjs','.cjs'):continue
        score=4*sum(t.lower() in p.lower() for t in terms)+2*(p in hints)+40*(p in extra_paths)
        if Path(p).suffix.lower()=='.md':score-=4
        if any(x in p.lower() for x in ('agent','memory','runtime','orchestr','boundary','context')):score+=3
        if score or p.lower().startswith('readme'):scored.append((score,p))
    scored.sort(key=lambda row:(-row[0],row[1]));chars=0
    max_files=min(16,max(1,int(os.getenv('RESUME_SOURCE_FILES','12'))))
    for _,path in scored[:max_files]:
        try:
            items=reader.search_ranges(repo,sha,path,terms)
            for item in items:
                if chars+len(item.excerpt)>30000:
                    records.append({'path':path,'status':'budget','reason':'源码上下文预算30000字符，未将未读范围标为已核验'});continue
                evidence[item.id]=item;chars+=len(item.excerpt)
            accepted=[i.id for i in items if i.id in evidence]
            records.append({'path':path,'status':'read' if accepted else 'budget','evidence_ids':accepted})
        except (ProviderError,OSError) as exc:records.append({'path':path,'status':'failed','error':getattr(exc,'code','source_io'),'reason':str(exc)[:200]})
    if tree['truncated']:records.append({'status':'partial','reason':'GitHub文件树截断，不能声明全仓覆盖'})
    if len(scored)>max_files:records.append({'status':'budget','reason':f'仅定向读取{max_files}文件，剩余候选路径未核验'})
    return records

def validate_discovery(discovery,evidence,requirements,context,contributions):
    check_claims(discovery.claims,evidence,context,contributions)
    cs={c.id for c in discovery.claims};rs={r.requirement_id for r in requirements}
    ids=[c.candidate_id for c in discovery.candidates]
    if len(set(ids))!=len(ids):raise ValueError('候选ID重复')
    for c in discovery.candidates:
        if not set(c.claim_ids)<=cs or not set(c.requirement_ids)<=rs:raise ValueError('候选引用未知claim/职责')
    return discovery

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

def generate(snapshot,material,chat=None,source_reader=None):
    from .resume_writer import WritingModel, ProjectValue, ROOT, validate_product
    provider=WritingModel() if chat is None else None;chat=provider or chat
    owned=source_reader is None;reader=source_reader or SourceReader(material.get('workspace_id','offline'),snapshot)
    max_downstream=min(20,max(8,int(os.getenv('RESUME_GENERATION_CALLS','16'))))
    h=Harness(chat,model=provider.base+'|'+provider.model if provider else 'injected',cache_dir=DATA/'resume-analysis-cache' if provider else None,max_calls=128+max_downstream)
    ctx=GenerationContext(**material.get('_generation_context',dict(workspace_id=material.get('workspace_id','offline'),snapshot_id=material.get('snapshot_id','offline'),commit_sha=material.get('commit','unresolved'),revision_status='resolved' if resolved(material.get('commit')) else 'unresolved',role=material.get('role',''),jd_version_id=material.get('jd_version_id'),target_origin='jd' if material.get('jd') else 'role_inferred',material_fingerprint=digest({k:v for k,v in material.items() if not k.startswith('_')}),output_mode=material.get('_output_mode','project_reference'),target_dimensions=material.get('_target_dimensions',[]))))
    ctx.model=provider.model if provider else 'injected';trace=[];progress=material.get('_progress');downstream=0
    def emit(stage,status,structure=None,error=None):
        record={'stage':stage,'status':status,'output_structure':structure or {},'input_refs':{'snapshot_id':ctx.snapshot_id,'commit_sha':ctx.commit_sha,'jd_version_id':ctx.jd_version_id},'error':error,'retry_count':int(stage.endswith('_RESELECT'))}
        trace.append(record)
        if progress:progress(record,{'context':ctx.model_dump(),'calls':h.records,'trace':trace})
    def call(stage,schema,data,instruction):
        nonlocal downstream
        if downstream>=max_downstream:raise ProviderError('生成阶段模型预算用完','resume_budget')
        downstream+=1;start=time.monotonic();emit(stage,'running')
        try:
            prompt=stage+'\n'+GUARD+'\n'+instruction+'\n'+json.dumps(data,ensure_ascii=False)+'\nJSON schema:'+json.dumps(schema.model_json_schema(),ensure_ascii=False)
            raw=h.call(prompt)
            try:
                result=schema.model_validate(parse_json(raw))
            except (ValueError, TypeError) as validation:
                details=[{'loc':list(e['loc']),'type':e['type']} for e in validation.errors()] if hasattr(validation,'errors') else [{'type':type(validation).__name__}]
                emit(stage,'schema_repair',{'errors':details[:20]})
                if downstream>=max_downstream:raise ProviderError('结构修复预算用完','resume_budget')
                downstream+=1
                repair=stage+'_SCHEMA_REPAIR\n'+GUARD+'\n仅修复下列JSON结构错误，保留原断言、ID、证据和事实状态，不增加事实。\n'+json.dumps({'errors':details[:20],'previous':raw},ensure_ascii=False)+'\nJSON schema:'+json.dumps(schema.model_json_schema(),ensure_ascii=False)
                result=schema.model_validate(parse_json(h.call(repair)))
            emit(stage,'completed',{'output':result.model_dump(),'elapsed_seconds':round(time.monotonic()-start,3)});return result
        except Exception as exc:
            details=[{'loc':list(e['loc']),'type':e['type']} for e in exc.errors()] if hasattr(exc,'errors') else []
            emit(stage,'failed',{'validation_errors':details[:20]},error=getattr(exc,'code',type(exc).__name__))
            if isinstance(exc,ProviderError):raise
            raise ProviderError(stage+'返回结构不合格；阶段记录已保留','resume_contract') from exc
    try:
        emit('MAPPING','running');mapped=h.map_wiki(material);emit('MAPPING','completed',{'batches':mapped['batches'],'cache_hits':mapped['cache_hits']})
        evidence=material_evidence(material);contributions={c['id']:c for c in material.get('user_optimizations',[]) if c['state']!='abandoned'}
        compact=[{k:v for k,v in f.items() if k!='quote'} for f in mapped['facts']]
        product=call('PRODUCT',ProjectValue,{'facts':compact,'uncertainties':mapped['uncertainties']},'独立于JD提炼产品全貌、用户闭环、整体架构和关键机制连接。引用有效Wiki编号；不从模块存在推断已集成或运行效果，作者背景须有来源，缺失连接列limitations。')
        product_refs={i:'project_existing' for i,e in evidence.items() if e.kind=='wiki'}
        try:validate_product(product,product_refs)
        except ValueError:
            invalid=list({ref for item in product.claims+product.architecture+product.key_chains for ref in item.source_refs if ref not in product_refs})
            emit('PRODUCT','reference_repair',{'invalid_refs':invalid})
            product=call('PRODUCT_REFERENCE_REPAIR',ProjectValue,{'previous':product.model_dump(),'invalid_refs':invalid,'facts':compact},'修复引用：只能引用facts中实际出现的source_ref。不得推断编号拼写或生成证据；断言找不到原文支持时删除该断言/链路，记录uncertainties。保持项目能力与个人贡献分开。')
            validate_product(product,product_refs)
        target=call('JD_PLAN',Investigation,{'role':ctx.role,'jd':material.get('jd',''),'editable_dimensions':material.get('_target_dimensions',[])},'有JD按原文职责规划最多6个关于当前项目机制的中性调查问题，不问候选人经历，不预设个人实现；search_terms必须含简短英文技术名/代码标识别名而非长句；无JD按岗位名称推断临时维度，origin=role_inferred，不冒充招聘JD。每项稳定requirement_id和优先级；中英文别名检索词，不预设RAG等方案。')
        if len({r.requirement_id for r in target.requirements})!=len(target.requirements) or any(r.origin!=ctx.target_origin for r in target.requirements):raise ProviderError('职责ID或推断来源不一致','resume_contract')
        retrieval=retrieve(material,target.requirements,int(os.getenv('RESUME_RETRIEVAL_CHARS','18000')))
        for q in retrieval:
            for item in q['candidate_evidence']:
                evidence[item['source_ref']]=SourceEvidence(id=item['source_ref'],kind='wiki',repo=material['repo'],commit_sha='unknown',content_hash=sha256(item['content']),excerpt=item['content'],wiki_page_id=item['page_ref'],revision_status='unknown')
        emit('RETRIEVE','completed',{'requirement_ids':[r.requirement_id for r in target.requirements],'candidate_segments':sum(len(q['candidate_evidence']) for q in retrieval)})
        source_trace=source_investigation(reader,material,evidence,target.requirements);emit('SOURCE','completed',{'reads':source_trace,'calls':reader.calls})
        def source_pack():return [e.model_dump() for e in evidence.values() if e.kind!='wiki']
        discovery=call('DISCOVER',Discovery,{'product':product.model_dump(),'facts':compact,'job_evidence':retrieval,'requirements':target.model_dump(),'sources':source_pack()},'建立通常6–10个互补候选，小项目可少，不凑数。最多32条claim：同一主题上游能力、用户贡献、计划分开claim；先列准确statement和evidence_ids，默认support=insufficient，后续独立核验。源码存在不等于个人实现，测试源码仅test_defined；没有作者依据不猜动机。候选关联claim/requirement ID，保留缺口。')
        validate_discovery(discovery,evidence,target.requirements,ctx,contributions)
        def verify(discovery,stage):
            used={i for c in discovery.claims for i in c.evidence_ids}
            # Only cited Wiki plus all bounded code evidence; no whole Wiki duplication.
            pack=[e.model_dump() for i,e in evidence.items() if i in used or e.kind!='wiki']
            checked=call(stage,Verification,{'claims':[{k:v for k,v in c.model_dump().items() if k in ('id','statement','evidence_ids','contribution_id')} for c in discovery.claims],'sources':pack,'contributions':list(contributions.values()),'context':ctx.model_dump()},'独立核对每个原claim的实际语义是否被原文支持，不沿用发现阶段的默认不足状态。只判断所写陈述，不要求陈述以外的参数、并发或测试证明：supported/partial/insufficient/contradicted并给reason。保持id和statement，允许修正证据关联及独立状态；没有调用连接不能标integrated，旧Wiki与源码冲突标contradicted。测试定义不等于通过，计划不等于实现。support只判断statement是否被原文支持，与个人贡献、测试报告和版本未知独立；原文明确描述项目能力可supported+upstream+validation_level=unknown，缺个人贡献/测试不能单独判insufficient，不提升源码核验级别。源码冲突仍contradicted。只能引用提供的证据，不能新建claim；用户口述已完成可user_confirmed，有独立diff/报告可user_evidenced。')
            original={c.id:c.statement for c in discovery.claims}
            if {c.id:c.statement for c in checked.claims}!=original:raise ProviderError('语义核验篡改claim集合或原陈述','resume_contract')
            check_claims(checked.claims,evidence,ctx,contributions);return {c.id:c for c in checked.claims}
        claims=verify(discovery,'CLAIM_VERIFY');candidates={c.candidate_id:c for c in discovery.candidates}
        def select(stage):
            eligible=[c.candidate_id for c in candidates.values() if any(claims[i].support=='supported' and claims[i].implementation_state=='implemented' and (ctx.output_mode!='personal_resume' or claims[i].attribution in ('user_confirmed','user_evidenced')) for i in c.claim_ids)]
            def fill_unknown(choice):
                missing=[r.requirement_id for r in target.requirements if r.requirement_id not in {c.requirement_id for c in choice.coverage}]
                if missing:
                    choice.coverage.extend(Coverage(requirement_id=i,status='unknown',reason='模型未提供该职责覆盖判断，系统明确记录未知') for i in missing)
                    emit(stage,'coverage_unknown',{'requirement_ids':missing})
                return choice
            choice=call(stage,Choice,{'candidates':[c.model_dump() for c in candidates.values()],'claims':[c.model_dump() for c in claims.values()],'requirements':target.model_dump(),'output_mode':ctx.output_mode},'独立于候选发现进行选题，选1–4条有支持的已实现claim；个人模式需确认个人贡献，可零条并提出缺口。不按关键词数量排序，综合岗位、工程深度、归属、证据、互补性。同链路合并，上游与优化状态不混。记录每个候选采纳/舍弃理由、每项职责覆盖direct/partial/unknown/not_applicable及下一调查问题。未找到不是不存在。outline保证整项目主线。')
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
            allowed={cid for i in choice.selected_ids for cid in candidates[i].claim_ids}
            # Intro may cite supported project facts outside selected personal bullet themes.
            writable={i:c for i,c in claims.items() if c.support=='supported' and c.implementation_state=='implemented'}
            draft=call('WRITE',ResumeDraft,{'context':ctx.model_dump(),'product':product.model_dump(),'choice':choice.model_dump(),'candidates':[c.model_dump() for c in candidates.values() if c.candidate_id in choice.selected_ids],'claims':[c.model_dump() for c in writable.values()],'metrics':[m.model_dump() for m in metrics.values()],'previous':draft.model_dump() if draft else None,'fix':issues},skill+'\n返回结构化中文草稿，不输出Markdown。简介及每条核心断言绑定claim_ids，不新增解释；条目绑定候选/贡献/指标。项目成果可null，禁止重复背景充数。计划、缺证据、未来方向放questions/limitations，不进正文。参考稿只说明项目能力，不能本人主导。个人稿亮点必须有确认贡献，无贡献可空条目，背景只能上游描述并questions追问1–3项。正文数字只用正确指标含义/单位/样本/环境及用户来源，不把配置阈值写性能效果。通常每条1–2句，保持整体框架和岗位重要机制。')
            if draft.output_mode!=ctx.output_mode:raise ProviderError('输出类型与输入不一致','resume_contract')
            issues=check_draft(draft,claims,candidates,choice,metrics,contributions)
            perspectives=[];omissions=[];blocking_parts=set()
            for role in ('HR','TECHNICAL'):
                review_refs={i for c in writable.values() for i in c.evidence_ids}
                result=call('REVIEW_'+role,QualityReview,{'draft':draft.model_dump(),'claims':[c.model_dump() for c in claims.values()],'candidates':[c.model_dump() for c in candidates.values()],'choice':choice.model_dump(),'requirements':target.model_dump(),'evidence':[evidence[i].model_dump() for i in review_refs if i in evidence] if role=='TECHNICAL' else []},'只做'+role+'独立评审，不读取其他意见。逐段检查新增断言与claim的蕴含关系及贡献归属；HR重点岗位、重复、可读性，技术重点真实机制及状态。category expression为据现有事实改写，needs_evidence为正文外追问，important_omission只引用真实候选ID及提供过的源码路径，不能直接创造主题。有新增断言无支持或归属错误时blocking=true并列part_ids（intro/outcome/条目id）；风格问题不blocking，补材料不足不冒充事实通过。没有成果不算格式失败。supported是模型辅助判断不是认证。')
                perspectives.append({'perspective':role.lower(),**result.model_dump()})
                for f in result.feedback:
                    if f.blocking:
                        available_parts={'intro','outcome'}|{b.id for b in draft.bullets}
                        if not set(f.part_ids)<=available_parts:issues.append('评审引用未知正文段落')
                        blocking_parts.update(set(f.part_ids)&available_parts)
                        issues.append(f.issue)
                    if f.category=='expression':issues.append(f.issue)
                    elif f.category=='important_omission':
                        if any(i not in candidates for i in f.candidate_ids):issues.append('评审引用未知候选')
                        elif any(i not in choice.selected_ids for i in f.candidate_ids):omissions.append(f)
                        elif f.candidate_ids:issues.append(f.issue)
                        elif len(draft.questions)<3:draft.questions.append(f.issue)
                    elif len(draft.questions)<3:draft.questions.append(f.issue)
                if not result.approved and not any(f.category in ('expression','important_omission') for f in result.feedback):issues.append(role+'评审未通过，缺证据意见仍需人工核对')
            reviews.append({'iteration':iteration+1,'issues':list(dict.fromkeys(issues)),'perspectives':perspectives})
            if omissions and iteration==0:
                reselected=True;paths=[p for f in omissions for p in f.paths]
                extra=source_investigation(reader,material,evidence,target.requirements,paths);source_trace.extend(extra)
                claims=verify(discovery,'CLAIM_VERIFY_RESELECT');choice=select('RESELECT')
                emit('RESELECT_RESULT','completed',{'selected_ids':choice.selected_ids,'reasons':[f.issue for f in omissions]});issues.append('根据补证后的重选重写')
            elif omissions:issues.extend('重选已达一次上限：'+f.issue for f in omissions)
            if not issues:break
        status='passed' if not issues else 'needs_review'
        if ctx.output_mode=='personal_resume' and not draft.bullets:status='needs_review'
        # Unsafe mapped paragraphs are removed even if bounded review failed; safe parts survive.
        rejected=[]
        for b in list(draft.bullets):
            one=ResumeDraft(output_mode=draft.output_mode,project_intro=Prose(text=''),bullets=[b])
            bad=check_draft(one,claims,candidates,choice,metrics,contributions)
            if bad or b.id in blocking_parts:draft.bullets.remove(b);rejected.append({'id':b.id,'issues':bad or ['语义评审阻断']})
        for field in ('project_intro','outcome'):
            p=getattr(draft,field)
            if p and p.text and (('intro' if field=='project_intro' else 'outcome') in blocking_parts or check_draft(ResumeDraft(output_mode=draft.output_mode,project_intro=p,bullets=[]),claims,candidates,choice,metrics,contributions)):
                setattr(draft,field,Prose(text='') if field=='project_intro' else None);rejected.append({'part':field})
        if rejected:status='needs_review'
        if not draft.project_intro.text.strip() or not draft.bullets:status='needs_review'
        if ctx.output_mode=='personal_resume' and not draft.bullets and not draft.questions:
            draft.questions=['你实际修改或实现了哪个模块？','该改动解决了什么问题，与原项目基线有何不同？','是否有测试样本或报告可说明结果？']
        selected=[{'id':c.candidate_id,'title':c.title,'jd_relation':choice.reasons.get(c.candidate_id,''),'hr_value':c.reason,'interview_focus':c.mechanism,'reason':choice.reasons.get(c.candidate_id,''),'source_refs':list(dict.fromkeys(i for cid in c.claim_ids for i in claims[cid].evidence_ids)),'state':'upstream_and_contribution_claims_separate','card':{'problem':c.problem,'mechanism':c.mechanism,'tradeoff':c.tradeoff,'missing':c.gaps}} for c in candidates.values() if c.candidate_id in choice.selected_ids]
        prose_map=[{'part':getattr(p,'id','intro' if p is draft.project_intro else 'outcome'),'text':p.text,'claim_ids':p.claim_ids,'contribution_ids':p.contribution_ids,'metric_ids':p.metric_ids,'evidence_ids':list(dict.fromkeys(i for cid in p.claim_ids if cid in claims for i in claims[cid].evidence_ids))} for p in [draft.project_intro,*draft.bullets,*([draft.outcome] if draft.outcome else [])]]
        audit={'kind':'writing_review','mode':'skill_model','schema_version':VERSION,'generation_context':ctx.model_dump(),'status':status,'iterations':len(reviews),'reviews':reviews,'trace':trace,'structured_draft':draft.model_dump(),'selection':{'selected':selected,'omitted':list(choice.omitted.values()),'outline':choice.outline,'project_value':product.model_dump()},'candidates':[c.model_dump() for c in candidates.values()],'choice':choice.model_dump(),'generated_claims':[c.model_dump() for c in claims.values()],'metrics':[m.model_dump() for m in metrics.values()],'source_evidence':[e.model_dump() for i,e in evidence.items() if e.kind!='wiki' or any(i in c.evidence_ids for c in claims.values())],'source_reads':source_trace,'requirements':target.model_dump(),'requirement_coverage':[c.model_dump() for c in choice.coverage],'job_evidence':retrieval,'project_map':mapped,'reselected':reselected,'rejected_prose':rejected,'questions':draft.questions[:3],'limits':draft.limitations,'harness':{'trace_id':h.trace_id,'calls':h.records,'usage':provider.usage if provider else [],'max_generation_calls':max_downstream},'skill_sha256':sha256(skill),'note':'源码存在、测试定义、用户贡献、运行效果分别记录；语义核验和同源双审不是人工认证。历史Wiki版本未知，不追认当前源码。'}
        audit['prose_claim_map']=prose_map
        emit('RENDER','completed',{'status':status,'selected_ids':choice.selected_ids,'claim_ids':[c.id for c in claims.values()]})
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
