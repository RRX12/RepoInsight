"""Architecture recommendations consume verified shared facts, never become facts."""
import json
from pydantic import Field
from .resume_contract import Strict,GenerationContext,VERSION,Feedback
from .resume_harness import Harness,GUARD,parse_json,digest
from .resume_support import WritingModel,cache_directory
from .source_reader import SourceReader
from .shared_analysis import get_or_build_analysis
from .architecture_schema import ArchitectureReport,validate_paths
from .providers import ProviderError
from .resume_prompts import compose,task_for_stage,validate_configuration

def report_schema(paths):
    """Expose the actual citation whitelist in every path field of the model schema."""
    allowed=sorted(paths)
    class SourcedReport(ArchitectureReport):
        @classmethod
        def model_json_schema(cls,*args,**kwargs):
            schema=super().model_json_schema(*args,**kwargs)
            def visit(node):
                if isinstance(node,dict):
                    for key,value in node.get('properties',{}).items():
                        if key in ('paths','source_paths') and value.get('type')=='array':
                            value['items']={'type':'string','enum':allowed}
                    for value in node.values():visit(value)
                elif isinstance(node,list):
                    for value in node:visit(value)
            visit(schema)
            return schema
    return SourcedReport

class Assessment(Strict):
    approved:bool
    issues:list[str]=Field(default_factory=list,max_length=8)
    evidence_requests:list[Feedback]=Field(default_factory=list,max_length=4)

def generate(snapshot,material,progress,check_active,chat=None,source_reader=None,retriever=None):
    provider=WritingModel() if chat is None else None;chat=provider or chat
    reader=source_reader or SourceReader(material['workspace_id'],snapshot)
    h=Harness(chat,model=provider.base+'|'+provider.model if provider else 'injected',max_calls=12,check_active=check_active,structured_output=True)
    repair_used=False;trace=[]
    def emit(stage,status,data=None,error=None):
        trace.append({'stage':stage,'status':status,'output_structure':data or {},'error':error});progress(stage,status)
    def call(stage,schema,data,instruction):
        nonlocal repair_used
        if stage.endswith('_REPAIR'):
            if repair_used:raise ProviderError('本次优化修复次数已达一次上限','optimization_contract')
            repair_used=True
        emit(stage,'running')
        prompt=stage+'\n'+GUARD+'\n'+instruction+'\n'+json.dumps(data,ensure_ascii=False)+'\nJSON schema:'+json.dumps(schema.model_json_schema(),ensure_ascii=False)
        task=task_for_stage(stage)
        if task:prompt,metadata=compose(task,stage,schema,data,instruction)
        raw=h.call(prompt,stage=stage)
        try:out=schema.model_validate(parse_json(raw))
        except ValueError as error:
            if repair_used:raise ProviderError('优化请求格式修复预算已耗尽','optimization_contract')
            repair_used=True
            out=schema.model_validate(parse_json(h.call(stage+'_REPAIR\n'+GUARD+'\n仅修复结构，不改变事实；校验错误：'+str(error)[:2000]+'\n原始输入：'+json.dumps(data,ensure_ascii=False)+'\n原输出：'+raw+'\nJSON schema:'+json.dumps(schema.model_json_schema(),ensure_ascii=False),stage=stage+'_REPAIR')))
        emit(stage,'completed');return out
    try:
        validate_configuration()
        ctx=GenerationContext(workspace_id=material['workspace_id'],snapshot_id=snapshot.id,commit_sha=snapshot.commit_sha,revision_status='resolved',role=material['role'],jd_version_id=material['jd_version_id'],target_origin='jd' if material['jd'] else 'role_inferred',material_fingerprint=digest(material))
        pack=get_or_build_analysis(snapshot,material,ctx,reader,call,emit,model=h.model,check_active=check_active,retriever=retriever)
        evidence={e.id:e for e in pack.evidence};paths={e.path for e in evidence.values() if e.path}
        data={'original_jd':material['jd'],'product':pack.product.model_dump(),'requirements':pack.target.model_dump(),'analysis':pack.discovery.model_dump(),'sources':[e.model_dump() for e in evidence.values()],'gaps':pack.gaps,'allowed_paths':sorted(paths)}
        instruction='基于已核验事实评审架构必要性：先问题和已有解法，再比较维持现状/局部改进/架构调整，最后用JD排序。最多3个方向，可0个。无运行测量不得声称慢、成本高或提升数字。没找到不等于没有；只有JD相关不构成必要性。建议均为未实施计划，所有假设写assumptions。所有paths/source_paths只能来自allowed_paths，文档提及但未实际读取的文件不得引用。不能支持的模块描述应缩小范围；无法支持的建议应移除并在no_change_reason解释材料不足，不用其他路径冒充佐证。返回现有ArchitectureReport。'
        report=call('OPTIMIZATION_PLAN',report_schema(paths),data,instruction)
        try:validate_paths(report,paths)
        except ValueError as error:
            if repair_used:raise ProviderError(str(error),'optimization_contract') from error
            report=call('OPTIMIZATION_PATH_REPAIR',report_schema(paths),{**data,'previous':report.model_dump(),'error':str(error)},instruction+'仅修复路径和结构，不编造来源。')
            validate_paths(report,paths)
        check=call('OPTIMIZATION_CHECK',Assessment,{**data,'report':report.model_dump()},'独立检查问题依据、是否遗漏已有方案、过度设计、无依据效果及路径。没有优化建议可以approved；不要求为了JD引入技术。')
        if not check.approved:
            if check.evidence_requests and not pack.supplemental_rounds and h.max_calls-len(h.records)>=3 and not repair_used:
                from .shared_analysis import extend_analysis
                pack=extend_analysis(pack,check.evidence_requests,material,ctx,reader,call,emit,check_active,retriever)
                evidence={e.id:e for e in pack.evidence};paths={e.path for e in pack.evidence if e.path}
                data={**data,'analysis':pack.discovery.model_dump(),'sources':[e.model_dump() for e in pack.evidence],'gaps':pack.gaps,'allowed_paths':sorted(paths)}
            if repair_used:raise ProviderError('优化核查未通过且已用完一次修复','optimization_review')
            report=call('OPTIMIZATION_REPAIR',report_schema(paths),{**data,'previous':report.model_dump(),'issues':check.issues},instruction+'仅修复核查指出的问题，不增加未经核验事实；无法证明必要性则移除建议或标conditional。')
            validate_paths(report,paths)
            for direction in report.directions:
                if direction.necessity=='recommended':direction.necessity='conditional'
        check_active()
        coverage={'note':'固定版本源码调查；静态证据不等于运行认证，优化是建议','analysis_pack_id':pack.analysis_pack_id,'schema_version':VERSION,'review_status':'reviewed' if check.approved else 'repaired_pending_review','assessment':check.model_dump(),'trace':trace,'calls':h.records,'embedding_usage':[r for t in trace if t['stage']=='SHARED_ANALYSIS' for r in t['output_structure'].get('retrieval_usage',[])],'source_evidence':[e.model_dump() for e in evidence.values()],'analysis_gaps':pack.gaps,'failed_pages':[],'omitted_pages':[],'unmatched_paths':[],'truncated_pages':[]}
        return report.model_dump(),coverage
    except (ValueError,ProviderError) as error:
        exc=error if isinstance(error,ProviderError) else ProviderError('优化输出契约失败：'+str(error)[:200],'optimization_contract')
        exc.stage_trace=trace;exc.stage_calls=h.records;exc.trace_id=h.trace_id
        raise exc
    finally:
        if source_reader is None:reader.close()
        if provider:provider.close()
