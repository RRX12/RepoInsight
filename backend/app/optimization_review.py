"""Batch advisor: shared preparation, discover, research, synthesize, optional refine."""
import json
import time
from pathlib import Path
from .analysis_contract import GenerationContext
from .analysis_harness import Harness,GUARD,parse_json,digest
from .model_support import ProjectModel,cache_directory
from .source_reader import SourceReader
from .shared_analysis import get_or_build_analysis
from .architecture_schema import OptimizationDiscovery,OptimizationReportV2,Overview,validate_paths
from .analysis_prompts import compose,task_for_stage,validate_configuration
from .optimization_research import Research,AdvisorConfig
from .web_research import WebResearch
from .code_retrieval import CodeRetrieval
from .providers import ProviderError,safe_path


def validate_report(report,discovery,sources,config,*,final=False,all_paths=None):
    candidates={c.candidate_id:c for c in discovery.candidates};assess={a.candidate_id:a for a in report.candidate_assessments}
    if len(assess)!=len(report.candidate_assessments) or set(assess)!=set(candidates):raise ValueError('candidate_coverage')
    if len(report.directions)>config.max_detailed_directions:raise ValueError('detailed_direction_budget')
    if len({d.candidate_id for d in report.directions})!=len(report.directions):raise ValueError('duplicate_direction')
    known={s.source_id:s for s in sources};paths={s.path for s in sources if s.kind!='external_source' and s.path}
    def refs(value):
        if isinstance(value,dict):
            for k,v in value.items():
                if k=='source_refs' and set(v)-set(known):raise ValueError('unknown_source_id')
                refs(v)
        elif isinstance(value,list):
            for v in value:refs(v)
    refs(report.model_dump())
    for item in report.overview.modules+report.overview.existing_capabilities+report.overview.core_flows:
        if set(item.paths)-paths:raise ValueError('unread_overview_path:'+json.dumps({'section':item.name,'unread_paths':sorted(set(item.paths)-paths),'allowed_paths':sorted(paths)},ensure_ascii=False))
    def code_statement(statement):
        if any(known[r].kind=='external_source' for r in statement.source_refs):raise ValueError('external_as_repository_fact')
    for a in report.candidate_assessments:
        if a.kind!=candidates[a.candidate_id].kind:raise ValueError('candidate_kind_changed')
        if a.merged_into and (a.merged_into not in candidates or a.merged_into==a.candidate_id):raise ValueError('invalid_merge')
        if a.decision=='conditional' and not a.assumptions:
            a.decision='validate_first';a.rationale+='；未提供明确触发条件，先验证后再决定。'
            report.unresolved_questions.append(a.title+'：需明确采用条件及其验证方式。')
        if a.decision=='prioritize' and (a.evidence_sufficiency!='sufficient' or a.assumptions):
            a.decision='validate_first';a.rationale+='；关键假设或证据尚待验证。'
    check_dag([(a.candidate_id,[a.merged_into] if a.merged_into else []) for a in report.candidate_assessments])
    for d in report.directions:
        if d.candidate_id not in assess or assess[d.candidate_id].decision=='not_recommended':raise ValueError('direction_not_actionable')
        code_statement(d.current_design)
        if not d.current_design.source_refs:raise ValueError('current_design_requires_source')
        if d.recommended_design.chosen_option not in {o.name for o in d.technical_options}:raise ValueError('chosen_option_missing')
        if len(d.technical_options)==1 and not d.assumptions:raise ValueError('single_option_requires_limit_explanation')
        for practice in d.reference_practices:
            invalid=[r for r in practice.source_refs if known[r].kind!='external_source' or known[r].read_status=='snippet_only']
            if invalid:raise ValueError('practice_requires_read_external_source:'+json.dumps({'invalid_refs':invalid,'reason':'参考实践只能引用已读取的外部正文；无外部资料时reference_practices=[]'},ensure_ascii=False))
        for change in d.code_changes:
            if not safe_path(change.path):raise ValueError('unsafe_change_path')
            if change.change_type=='modify' and (change.path not in paths or not any(known[r].path==change.path for r in change.source_refs)):
                raise ValueError('modify_requires_read_source:'+json.dumps({'path':change.path,'source_refs':change.source_refs,'path_read':change.path in paths,'matching_refs':[r for r,s in known.items() if s.path==change.path],'reason':'修改已有文件必须引用该文件的已读源码；未读文件先code_read补查'},ensure_ascii=False))
            if change.change_type=='add' and change.path in (all_paths or paths):raise ValueError('add_is_existing_path')
        check_dag([(s.step_id,s.dependencies) for s in d.implementation_steps])
        if any(v.measurement_status!='not_measured' for v in d.validation_plan):raise ValueError('unverified_measurement')
    if report.sources and [s.model_dump() for s in report.sources]!=[s.model_dump() for s in sources]:raise ValueError('model_modified_sources')
    if any(a.candidate_id not in candidates for a in report.validation_actions):raise ValueError('unknown_validation_candidate')
    check_dag([(r.candidate_id,r.dependencies) for r in report.roadmap],set(candidates))
    by={r.candidate_id:r for r in report.roadmap}
    for r in report.roadmap:
        if any(dep in by and by[dep].order>=r.order for dep in r.dependencies):raise ValueError('roadmap_order')
    if final and report.follow_up_requests:
        pending={r.candidate_id for r in report.follow_up_requests}
        report.unresolved_questions+=['最终调用不再补查：'+r.purpose for r in report.follow_up_requests]
        for a in report.candidate_assessments:
            if a.candidate_id in pending and a.decision=='prioritize':a.decision='validate_first'
        report.follow_up_requests=[]
    if not report.directions:
        if any(a.decision=='prioritize' and not a.merged_into for a in report.candidate_assessments):
            raise ValueError('prioritized_candidate_requires_detailed_direction')
        if not report.no_change_reason.strip():
            if not report.candidate_assessments or any(not a.rationale.strip() for a in report.candidate_assessments):
                raise ValueError('empty_report_reason:需要候选取舍理由或明确的空报告说明')
            labels={'conditional':'条件满足后考虑','validate_first':'先验证','not_recommended':'暂不建议'}
            report.no_change_reason='未展开完整实施方案；依据候选结论：\n'+'\n'.join(a.title+'（'+labels.get(a.decision,a.decision)+'）：'+a.rationale for a in report.candidate_assessments)

    return report

def check_dag(rows,allowed=None):
    graph=dict(rows)
    if len(graph)!=len(rows):raise ValueError('duplicate_dependency_id')
    if any(set(v)-(allowed or set(graph)) for v in graph.values()):raise ValueError('unknown_dependency')
    visiting=set();done=set()
    def visit(n):
        if n in visiting:raise ValueError('dependency_cycle')
        if n in done:return
        visiting.add(n)
        for dep in graph.get(n,[]):visit(dep)
        visiting.remove(n);done.add(n)
    for n in graph:visit(n)


def prepared_overview(pack,sources):
    """ProjectValue was generated during preparation; project it, do not invent facts."""
    read_paths={s.path for s in sources if s.path}
    original={e.id:e.path for e in pack.evidence}
    def paths(refs):return sorted({original[r] for r in refs if r in original and original[r] in read_paths})
    product=pack.product
    modules=[{'name':c.name,'responsibility':' → '.join(c.steps),'paths':paths(c.source_refs)} for c in product.architecture]
    flows=[{'name':c.name,'description':' → '.join(c.steps),'paths':paths(c.source_refs)} for c in product.key_chains]
    summary=product.value_summary or product.background or '准备材料未形成完整项目概况。'
    return Overview(summary=summary,current_architecture='；'.join(c['responsibility'] for c in modules) or '准备材料未确认完整架构关系。',modules=modules or [{'name':'项目概况','responsibility':summary,'paths':[]}],core_flows=flows or [{'name':'项目流程','description':' → '.join(product.product_flow) or '准备材料未确认完整执行流程。','paths':[]}],coverage_notes=list(dict.fromkeys(['复用准备阶段概况；路径仅来自已读证据，不表示运行验证。']+product.uncertainties+pack.gaps))[:30])


def generate(snapshot,material,progress,check_active,chat=None,source_reader=None,retriever=None,web=None):
    config=AdvisorConfig.model_validate(material['advisor_config']) if material.get('advisor_config') else AdvisorConfig.environment();provider=ProjectModel() if chat is None else None;chat=provider or chat
    reader=source_reader or SourceReader(material['workspace_id'],snapshot)
    retrieval=retriever or CodeRetrieval(check_active=check_active)
    h=Harness(chat,model=provider.base+'|'+provider.model if provider else 'injected',max_calls=12,check_active=check_active,structured_output=True)
    trace=[];repair_used=False;semantic=0;optimization_attempts=0
    web=web or WebResearch(enabled=config.web_enabled,cache_dir=cache_directory()/'advisor-web',check=check_active,refresh=config.web_refresh)
    def emit(stage,status,data=None,error=None):
        trace.append({'stage':stage,'status':status,'output_structure':data or {},'error':error})
        label={'OPTIMIZATION_DISCOVER':'批量规划候选','OPTIMIZATION_SYNTHESIZE':'综合优化方案','OPTIMIZATION_REFINE':'补查后修订'}.get(stage,'准备项目分析')
        state={'running':'进行中','completed':'完成','reused_analysis':'复用匹配材料','cache_miss':'无匹配缓存，准备固定版本材料','published':'已保存核验材料'}.get(status,status)
        progress(stage,label+'：'+state)
    def invoke(stage,schema,data,instruction,validator=None):
        nonlocal repair_used,semantic,optimization_attempts
        optimization=stage.startswith('OPTIMIZATION_')
        if optimization:
            if semantic>=config.max_semantic_calls:raise ProviderError('优化语义预算耗尽','optimization_budget')
            semantic+=1
        elif stage.endswith('_REPAIR'):
            if repair_used:raise ProviderError('格式修复预算耗尽','optimization_contract')
            repair_used=True
        emit(stage,'running')
        task=task_for_stage(stage)
        if task:prompt,_=compose(task,stage,schema,data,instruction)
        else:prompt=stage+'\n'+GUARD+'\n'+instruction+'\n'+json.dumps(data,ensure_ascii=False)+'\nJSON schema:'+json.dumps(schema.model_json_schema(),ensure_ascii=False)
        wire_schema=schema.model_json_schema()
        if optimization:
            source_rows=data.get('research',{}).get('sources',[])
            allowed_paths=sorted({row['path'] for row in source_rows if row.get('path') and row['kind']!='external_source'})
            allowed_refs=[row['source_id'] for row in source_rows]
            def bind_sources(node):
                if isinstance(node,dict):
                    for key,value in node.get('properties',{}).items():
                        if key in ('paths','source_refs') and value.get('type')=='array':
                            value['items']={'type':'string','enum':allowed_paths if key=='paths' else allowed_refs}
                    for value in node.values():bind_sources(value)
                elif isinstance(node,list):
                    for value in node:bind_sources(value)
            bind_sources(wire_schema)
            external_refs=[row['source_id'] for row in source_rows if row['kind']=='external_source' and row['read_status']!='snippet_only']
            definitions=wire_schema.get('$defs',{})
            if 'ReferencePractice' in definitions:
                definitions['ReferencePractice']['properties']['source_refs']['items']={'type':'string','enum':external_refs}
            if not external_refs and 'DetailedDirection' in definitions:
                definitions['DetailedDirection']['properties']['reference_practices']['maxItems']=0
            if 'CodeChange' in definitions:
                change_schema=definitions['CodeChange']
                change_schema['allOf']=[{'if':{'properties':{'change_type':{'const':'modify'}},'required':['change_type']},'then':{'properties':{'path':{'enum':allowed_paths},'source_refs':{'minItems':1}},'required':['source_refs']}}]
                for path in allowed_paths:
                    same_path=[row['source_id'] for row in source_rows if row.get('path')==path and row['kind']!='external_source']
                    change_schema['allOf'].append({'if':{'properties':{'change_type':{'const':'modify'},'path':{'const':path}},'required':['change_type','path']},'then':{'properties':{'source_refs':{'contains':{'enum':same_path},'minContains':1}}}})
            if schema is OptimizationReportV2:
                wire_schema['properties'].pop('overview',None)
                wire_schema['required']=[key for key in wire_schema.get('required',[]) if key!='overview']
            prompt=prompt.rsplit('\nJSON schema:',1)[0]+'\nJSON schema:'+json.dumps(wire_schema,ensure_ascii=False)
        raw=None
        for attempt in range(2):
            if optimization:
                if optimization_attempts>=config.max_request_attempts:raise ProviderError('优化请求尝试预算耗尽','optimization_budget')
                optimization_attempts+=1
            try:
                raw=h.call(prompt,stage=stage if not attempt else stage+'_SCHEMA_REPAIR',output_budget=(config.plan_output_tokens if stage=='OPTIMIZATION_DISCOVER' else config.report_output_tokens) if optimization else None);check_active()
                value=parse_json(raw)
                if schema is OptimizationReportV2 and isinstance(value,dict):value['overview']=data['prepared_overview']
                out=schema.model_validate(value)
                if validator:validator(out)
                emit(stage,'completed');return out
            except ValueError as error:
                check_active()
                diagnostic=cache_directory()/'advisor-errors'/material['workspace_id']/(h.trace_id+'.json')
                diagnostic.parent.mkdir(parents=True,exist_ok=True)
                entries=json.loads(diagnostic.read_text(encoding='utf-8')) if diagnostic.exists() else []
                entries.append({'stage':stage,'validation_error':str(error),'model_output':raw,'sources':[{'source_id':row['source_id'],'path':row.get('path'),'kind':row['kind']} for row in data.get('research',{}).get('sources',[])]})
                temp=diagnostic.with_suffix('.tmp');temp.write_text(json.dumps(entries,ensure_ascii=False),encoding='utf-8');check_active();temp.replace(diagnostic)
                if attempt or repair_used:raise ProviderError('优化输出校验失败：'+str(error)[:1000],'optimization_contract') from error
                repair_used=True
                prompt=stage+'_SCHEMA_REPAIR\n'+GUARD+'\n仅修复格式及引用，保持事实集合。错误：'+str(error)[:2000]+'\n原始输入：'+json.dumps(data,ensure_ascii=False)+'\n原输出：'+str(raw)+'\nJSON schema:'+json.dumps(wire_schema,ensure_ascii=False)
    try:
        validate_configuration();check_active()
        ctx=GenerationContext(workspace_id=material['workspace_id'],snapshot_id=snapshot.id,commit_sha=snapshot.commit_sha,revision_status='resolved',role=material['role'],jd_version_id=material['jd_version_id'],target_origin='jd' if material['jd'] else 'role_inferred',material_fingerprint=digest(material))
        pack=get_or_build_analysis(snapshot,material,ctx,reader,invoke,emit,model=h.model,check_active=check_active,retriever=retrieval)
        research=Research(pack,material,reader,retrieval,web,config,check_active)
        base={'constraints':material.get('constraints',{}),'jd':material['jd'],'role_origin':'explicit_jd' if material['jd'] else 'not_provided','project':pack.product.model_dump(),'requirements':pack.target.model_dump() if material['jd'] else None,'analysis':pack.discovery.model_dump(),'research':research.payload(),'corrections':material.get('project_corrections',[]),'prepared_overview':prepared_overview(pack,list(research.sources.values())).model_dump()}
        templates=[p.read_text(encoding='utf-8') for p in sorted((Path(__file__).resolve().parents[1]/'prompts/analysis').glob('optimization_*.md'))]
        ident=digest([material,pack.analysis_pack_id,pack.content_hash,config.model_dump(),h.model,templates,web.enabled,bool(web.key),'optimization-v2'])
        cache=cache_directory()/'advisor'/material['workspace_id']/(ident+'.json')
        if cache.exists() and not web.refresh:
            saved=json.loads(cache.read_text(encoding='utf-8'))
            if time.time()-saved['time']<86400 and saved['hash']==digest(saved['report']):
                check_active();report=OptimizationReportV2.model_validate(saved['report'])
                report.coverage['cached']=True
                report.coverage['semantic_verification']='not_independently_verified'
                report.coverage['usage']={'preparation_model':h.records,'optimization_model':[],'web_tools':[],'embedding':retrieval.trace,'upstream_wiki':None}
                return report.model_dump(),{**saved['coverage'],'calls':h.records,'cached':True,'current_usage':None,'web_tools':[],'embedding_usage':retrieval.trace,'semantic_calls':0,'optimization_attempts':0,'format_repair_used':False,'trace':trace}
        plan_file=cache.with_suffix('.plan.json')
        known=set(research.sources)
        def validate_plan(plan):
            if len(plan.candidates)>config.max_candidates or len({c.candidate_id for c in plan.candidates})!=len(plan.candidates):raise ValueError('candidate_budget_or_duplicate')
            if not plan.candidates and not plan.no_change_reason:raise ValueError('empty_plan_reason')
            for c in plan.candidates:
                if not c.current_state.source_refs or set(c.current_state.source_refs)-known:raise ValueError('candidate_source_refs')
                if any(a.candidate_id!=c.candidate_id for a in c.research_actions):raise ValueError('research_action_identity')
        if plan_file.exists():
            discovery=OptimizationDiscovery.model_validate_json(plan_file.read_text(encoding='utf-8'));validate_plan(discovery)
        else:
            discovery=invoke('OPTIMIZATION_DISCOVER',OptimizationDiscovery,base,'',validate_plan)
            plan_file.parent.mkdir(parents=True,exist_ok=True);check_active();temp_plan=plan_file.with_suffix('.tmp');temp_plan.write_text(discovery.model_dump_json(),encoding='utf-8');check_active();temp_plan.replace(plan_file)
        ids=[c.candidate_id for c in discovery.candidates]
        if discovery.candidates:
            # Three candidate groups share one budget; uninvestigated candidates remain visible.
            chosen=[c for c in discovery.candidates if c.research_actions][:3]
            payload=research.run([a for c in chosen for a in c.research_actions],ids)
            data={**base,'discovery':discovery.model_dump(),'research':payload,'final_call':False}
            check_active();all_paths=set(reader.list_tree(material['repo'],ctx.commit_sha)['paths']);check_active()
            report=invoke('OPTIMIZATION_SYNTHESIZE',OptimizationReportV2,data,'',lambda r:validate_report(r,discovery,list(research.sources.values()),config,all_paths=all_paths))
            follow=report.follow_up_requests
            if follow and config.followup_rounds and semantic<config.max_semantic_calls and optimization_attempts<config.max_request_attempts:
                before=digest({key:s.content_hash for key,s in research.sources.items()});payload=research.run(follow,ids);check_active()
                if before!=digest({key:s.content_hash for key,s in research.sources.items()}):
                    report=invoke('OPTIMIZATION_REFINE',OptimizationReportV2,{**data,'research':payload,'previous':report.model_dump(),'final_call':True},'',lambda r:validate_report(r,discovery,list(research.sources.values()),config,final=True,all_paths=all_paths))
            if report.follow_up_requests:
                report.unresolved_questions+=['补查结束或预算不足，仍待验证：'+a.purpose for a in report.follow_up_requests]
                for a in report.candidate_assessments:
                    if a.candidate_id in {f.candidate_id for f in report.follow_up_requests} and a.decision=='prioritize':a.decision='validate_first'
                report.follow_up_requests=[]
        else:
            overview=Overview(summary=pack.product.value_summary or '暂无有依据的优化候选',current_architecture='维持现状，详见固定版本源码材料',modules=[{'name':'项目','responsibility':'未形成优化候选','paths':[]}],core_flows=[{'name':'现状','description':'没有额外推荐','paths':[]}],coverage_notes=discovery.coverage_notes or ['候选规划未发现有依据的方向'])
            report=OptimizationReportV2(overview=overview,no_change_reason=discovery.no_change_reason)
        pending={r['candidate_id'] for r in research.results if r.get('unresolved_reason')}
        for assessment in report.candidate_assessments:
            if assessment.candidate_id in pending and assessment.decision=='prioritize':
                assessment.decision='validate_first';assessment.rationale+='；工具调查未完成，先验证。'
        report.sources=list(research.sources.values());report.coverage=research.payload()['coverage']
        report.coverage['semantic_verification']='not_independently_verified'
        report.coverage['usage']={'preparation_model':[c for c in h.records if not c['stage'].startswith('OPTIMIZATION_')],'optimization_model':[c for c in h.records if c['stage'].startswith('OPTIMIZATION_')],'embedding':retrieval.trace,'web_tools':web.trace,'upstream_wiki':None}
        report.coverage['uninvestigated_candidates']=[c.candidate_id for c in discovery.candidates if c.research_actions and c not in chosen] if discovery.candidates else []
        check_active()
        coverage={'analysis_pack_id':pack.analysis_pack_id,'schema_version':'optimization-v2','trace':trace,'calls':h.records,'source_evidence':[e.model_dump() for e in research.code_evidence.values()], 'embedding_usage':retrieval.trace,'analysis_gaps':pack.gaps,'web_tools':web.trace,'semantic_calls':semantic,'optimization_attempts':optimization_attempts,'format_repair_used':repair_used,'cached':False,'research_sources':[s.model_dump() for s in research.sources.values()]}
        cache.parent.mkdir(parents=True,exist_ok=True);temp=cache.with_suffix('.tmp');temp.write_text(json.dumps({'time':time.time(),'research_identity':digest([discovery.model_dump(),[s.model_dump() for s in research.sources.values()],research.results]),'report':report.model_dump(),'hash':digest(report.model_dump()),'coverage':coverage},ensure_ascii=False),encoding='utf-8');check_active();temp.replace(cache)
        return report.model_dump(),coverage
    except (ValueError,ProviderError) as error:
        exc=error if isinstance(error,ProviderError) else ProviderError('优化输出契约失败：'+str(error)[:1000],'optimization_contract')
        exc.stage_trace=trace;exc.stage_calls=h.records;exc.trace_id=h.trace_id
        exc.stage_usage={'preparation_model':[c for c in h.records if not c['stage'].startswith('OPTIMIZATION_')],'optimization_model':[c for c in h.records if c['stage'].startswith('OPTIMIZATION_')],'web_tools':web.trace,'embedding':retrieval.trace,'upstream_wiki':None}
        raise exc
    finally:
        if source_reader is None:reader.close()
        if retriever is None:retrieval.close()
        web.close()
        if provider:provider.close()
