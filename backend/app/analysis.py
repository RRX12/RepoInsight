import ast
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select
from .db import *
from .memory import require, scoped, attach, invalidate, latest_jd
from .providers import GitHub, demo_fixture, ProviderError, safe_path
from .agent import load_skill

worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix='repocareer-worker')
futures = {}
def still_executing(rid):
    future = futures.get(rid)
    return future is not None and not future.done()
def recover_runs():
    with Session.begin() as s:
        for r in s.scalars(select(Run).where(Run.status.in_(['queued','running']))):
            r.status='interrupted'; r.error='服务重启中断。已落库步骤保留；请显式安全重试，未自动恢复内存任务。'
def cancelled(rid):
    with Session() as s: return s.get(Run,rid).status == 'cancelled'

def finish_timing(r,elapsed=None):
    if r.result.get('analysis_finished_at'):return
    finished=now()
    if elapsed is None:
        started=r.result.get('analysis_started_at') or r.result.get('queued_at') or r.created_at
        elapsed=(datetime.fromisoformat(finished)-datetime.fromisoformat(started)).total_seconds()
    r.result={**r.result,'analysis_finished_at':finished,'elapsed_seconds':max(0,elapsed)}
def step(rid, tool, detail):
    with Session.begin() as s:
        r=s.get(Run,rid); r.steps = r.steps+[{'tool':tool,'summary':detail,'created_at':now(),'status':'completed'}]
def analyze_snapshot(s, snapshot):
    evs = [e for e in scoped(s, Evidence, snapshot.workspace_id) if e.snapshot_id == snapshot.id]
    python = [e for e in evs if e.path.endswith('.py') and 'test' not in e.path.lower()]
    readme = [e for e in evs if e.type == 'readme']
    findings=[]; functions=[]; symbols=[]
    for e in python:
        try:
            tree = ast.parse(e.excerpt)
            for n in ast.walk(tree):
                if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
                    calls = []
                    for child in ast.walk(n):
                        if isinstance(child,ast.Call):
                            try: calls.append(ast.unparse(child.func))
                            except Exception: pass
                    functions.append({'name':n.name,'path':e.path,'line':n.lineno,'end_line':getattr(n,'end_lineno',n.lineno),'evidence_id':e.id,'calls':list(dict.fromkeys(calls))[:12]})
                    symbols += [x.id for x in ast.walk(n) if isinstance(x,ast.Name)]
            if re_cache(e.excerpt):
                findings.append(Finding(workspace_id=snapshot.workspace_id,snapshot_id=snapshot.id,kind='upstream_capability',claim=f'{e.path} 出现缓存相关实现/调用；原项目已有缓存线索，不能声称新增缓存缺口。具体覆盖语义仍需核验。',status='supported',evidence_ids=[e.id],coverage_note='源码文本/AST 检查，未执行；只支持存在缓存线索'))
        except SyntaxError: pass
    if readme:
        e=readme[0]; findings.append(Finding(workspace_id=snapshot.workspace_id,snapshot_id=snapshot.id,kind='upstream_capability',claim='README 中的项目描述属于上游能力说明，未经本系统运行验证。',status='supported',evidence_ids=[e.id],coverage_note='只确认文档内容存在，不能等同于功能测试'))
    for f in findings: s.add(f)
    s.flush()
    main = functions[:8]
    # This is a deliberately bounded candidate chain, not an invented call graph.
    w=s.get(Workspace,snapshot.workspace_id)
    interest_words = set(__import__('re').findall(r'[a-zA-Z]{3,}',w.interest.lower()))
    ranked = sorted(functions,key=lambda f:sum(word in (f['name']+' '+f['path']).lower() for word in interest_words),reverse=True)
    entry = ranked[0] if ranked else None
    direct = []
    if entry:
        direct = [f for f in functions if f['name'] in entry['calls'] and f['path']==entry['path']][:3]
    chain = {'entry_candidates':([entry]+direct if entry else []),'description':('入口候选 '+entry['name']+' → 函数体中直接调用 '+(', '.join(entry['calls']) or '未发现调用')+' → 返回/异常边界') if entry else '当前读取范围未找到可分析 Python 函数',
        'status':'unverified','note':'AST 从实际源码提取位置与函数体调用（可能包含嵌套函数）；只展示一条入口候选。动态分派、外部调用和是否为业务入口待人工核验。'}
    templates = [
      ('输入边界的可预测错误', '核查空输入、编码、超大输入的异常契约，必要时补充显式校验与错误返回', '只在读取函数边界后确认缺口；可能已有上层校验', '保持现有异常；在调用层转换；在当前函数校验', '新增校验可能改变兼容性，应优先保持旧 API', '选定一条入口，记录旧行为；增加有效/无效边界测试，确认兼容性'),
      ('重复请求与失效边界', '核查现有缓存键、内容变更失效和资源上限；仅对已证实的边界问题改进', '已有缓存时不推荐新增缓存；未发现也不能宣称不存在', '不缓存；现有缓存加边界；有实测瓶颈后再评估外部缓存', '缓存复杂度、内存和一致性成本；无瓶颈不引入 Redis', '对同内容/变更内容/错误输入设计可比实验，明确样本与资源约束'),
      ('关键链路的验证缺口', '核查业务链路测试是否覆盖失败条件，必要时补充回归用例与可复现说明', '读取范围不足以判断全仓库测试缺失', '沿用已有用例；参数化边界用例；手工验证说明', '维护成本和测试环境依赖；不自动执行导入代码', '提供修改前后测试记录、命令、环境与失败回归条件')]
    w=s.get(Workspace,snapshot.workspace_id); jd=latest_jd(s,w.id)
    terms=jd.requirements if jd else []
    # JD ranks only hypotheses that have a bounded source investigation path.
    templates.sort(key=lambda t: sum(x.lower() in ' '.join(t).lower() for x in terms),reverse=True)
    improvements=[]
    for problem,proposal,uncertainty,alternatives,tradeoffs,acceptance in templates if main else []:
        details={'problem':problem,'proposal':proposal,'status_note':'待验证假设，未证实必要性','source_evidence_ids':list(dict.fromkeys(f['evidence_id'] for f in main)),
            'paths':', '.join(dict.fromkeys(f['path'] for f in main)), 'coverage':snapshot.coverage,'hypothesis':uncertainty,
            'alternatives':alternatives,'tradeoffs':tradeoffs,'acceptance_criteria':acceptance,
            'jd_relation':('按当前 JD 相关词排序：'+', '.join(terms)) if jd else '无 JD，以岗位 '+w.role+' 为临时目标',
            'constraint_check':f'技能 {w.skills}；时间 {w.time_budget}；环境 {w.environment}。实际实施成本待确认。'}
        item=Improvement(workspace_id=w.id,snapshot_id=snapshot.id,jd_version_id=jd.id if jd else None,details=details)
        s.add(item); s.flush(); improvements.append(item.id)
    return {'chain':chain,'finding_ids':[f.id for f in findings],'improvement_ids':improvements,
        'mode':snapshot.metadata_json['mode'],'usage':{'status':'unavailable','reason':'规则/AST 检查，无模型调用'},'limitations':'未执行源码，不宣称全面理解。建议均为调查起点，用户应先确认业务问题和现有解法。'}
def re_cache(text):
    import re
    return bool(re.search(r'\bcache\b|lru_cache|cached_property',text))
def execute(rid):
    start=time.monotonic()
    started=False
    try:
        with Session.begin() as s:
            r=s.get(Run,rid)
            if r.status != 'queued': return
            r.status='running';r.result={**r.result,'analysis_started_at':now()};started=True; req=r.request; wid=r.workspace_id
        if req.get('architecture'):
            execute_architecture(rid,req,wid,start)
            return
        step(rid,'load_skill','repo_understanding'); load_skill('repo_understanding')
        with Session() as s:
            r=s.get(Run,rid); saved=r.result.get('snapshot_id')
        if not saved:
            if req['demo']:
                data=demo_fixture(); data['coverage']={'read_files':list(data['files']),'omitted':[],'tree_truncated':False,'note':'演示 fixture，未访问真实仓库、未执行代码'}
            else: data=GitHub().snapshot(req['url'],lambda p:step(rid,'read_file',p),lambda:cancelled(rid))
            if cancelled(rid): return
            with Session.begin() as s:
                r=s.get(Run,rid)
                if r.status == 'cancelled': return
                old=scoped(s,Snapshot,wid)
                snap=Snapshot(workspace_id=wid,owner=data['owner'],repo=data['repo'],commit_sha=data['commit_sha'],metadata_json={'description':data['description'],'mode':'demo' if req['demo'] else 'real'},coverage=data['coverage'])
                s.add(snap); s.flush()
                for path,text in data['files'].items():
                    if not safe_path(path): raise ProviderError('快照含非法路径')
                    source=f'https://github.com/{snap.owner}/{snap.repo}/blob/{snap.commit_sha}/{path}' if not req['demo'] else 'fixture://demo_repo/'+path
                    attach(s,wid,'readme' if path.lower().startswith('readme') else 'source_code',text,source,snapshot_id=snap.id,path=path,line_start=1,line_end=max(1,len(text.splitlines())))
                if old:
                    prev=old[-1]
                    previous={e.path:e.content_hash for e in scoped(s,Evidence,wid) if e.snapshot_id==prev.id}
                    current={e.path:e.content_hash for e in scoped(s,Evidence,wid) if e.snapshot_id==snap.id}
                    changed={p for p in previous.keys()|current.keys() if previous.get(p)!=current.get(p)}
                    for f in scoped(s,Finding,wid):
                        if f.snapshot_id==prev.id and (changed or prev.commit_sha!=snap.commit_sha): f.status='stale'
                    for i in scoped(s,Improvement,wid):
                        if i.snapshot_id==prev.id: i.status='stale'
                    invalidate(s,wid,[prev.id]+[i.id for i in scoped(s,Improvement,wid) if i.snapshot_id==prev.id])
                r.result={'snapshot_id':snap.id}; saved=snap.id
            step(rid,'resolve_commit',data['commit_sha'])
        if cancelled(rid): return
        load_skill('improvement_planning')
        with Session.begin() as s:
            r=s.get(Run,rid)
            if r.status=='cancelled': return
            snapshot=s.get(Snapshot,saved)
            # Atomic transaction: analysis records and completion cannot be duplicated on retry.
            result=analyze_snapshot(s,snapshot)
            r.result={**r.result,**result,'elapsed_seconds':time.monotonic()-start}; r.status='completed'; r.error=None
            r.steps=r.steps+[{'tool':'analyze_snapshot','status':'completed','summary':'AST/文本证据与三项待验证假设','created_at':now()}]
    except Exception as exc:
        with Session.begin() as s:
            r=s.get(Run,rid)
            if r.status != 'cancelled':
                r.result={**r.result,'failure_trace':getattr(exc,'stage_trace',[]),'failure_calls':getattr(exc,'stage_calls',[]),'failure_usage':getattr(exc,'stage_usage',None)}
                r.status='failed'; r.error=str(exc) if isinstance(exc,ProviderError) else '内部分析失败，已完成步骤保留；查看服务端错误并安全重试。'
        if not isinstance(exc,ProviderError):
            import traceback; traceback.print_exc()
    finally:
        if started:
            with Session.begin() as s:
                r=s.get(Run,rid)
                if r is not None and r.status not in ('queued','running'):finish_timing(r,time.monotonic()-start)
def submit(rid): futures[rid] = worker.submit(execute,rid)

def execute_architecture(rid,req,wid,start):
    from .deepwiki import DeepWikiOpen
    from .architecture_schema import ArchitectureReport, validate_paths
    import json
    from pathlib import Path
    with Session() as s:
        snap=require(s,Snapshot,req['snapshot_id'],wid)
        saved=dict(s.get(Run,rid).result)
    def persist_task(task_id):
        with Session.begin() as s:
            r=s.get(Run,rid);r.result={**r.result,'deepwiki_task_id':task_id}
    provider=None
    try:
        if req['demo']:
            # Explicit isolated fixture, never an analysis of the user's uploaded code.
            demo_path=Path(__file__).resolve().parents[2]/'fixtures'/'architecture_demo.json'
            fixture=json.loads(demo_path.read_text(encoding='utf-8'))
            report=ArchitectureReport.model_validate(fixture['report']).model_dump();wiki=fixture['wiki'];coverage={'note':'演示报告只展示示例项目，不是对上传仓库或用户JD的分析','wiki_pages':len(wiki['generated_pages']),'usable_pages':len(wiki['generated_pages']),'failed_pages':[],'omitted_pages':[],'unmatched_paths':[],'truncated_pages':[]}
            step(rid,'demo_fixture','演示示例，不分析上传源码，不调用DeepWiki-Open')
        else:
            provider=DeepWikiOpen()
            provider.wiki_config=req.get('wiki_retrieval',{'mode':'legacy'})
            provider.provider=provider.wiki_config.get('provider',getattr(provider,'provider',None))
            provider.model=provider.wiki_config.get('model',getattr(provider,'model',None))
            from .project_inputs import collect_project
            with Session() as initial:
                active_snapshot,initial_material,wiki_input_fingerprint=collect_project(initial,wid)
                if active_snapshot.id!=snap.id or initial_material['role']!=req['role'] or initial_material['jd_version_id']!=req['jd_version_id']:raise ProviderError('Wiki生成输入已更正，请重新分析','source_revision')
            def check_wiki_inputs():
                if cancelled(rid):raise ProviderError('已取消Wiki','cancelled')
                with Session() as latest:
                    _,_,fingerprint=collect_project(latest,wid)
                    if fingerprint!=wiki_input_fingerprint:raise ProviderError('Wiki生成输入已更正','source_revision')
            provider.check_inputs=check_wiki_inputs
            wiki=saved.get('wiki')
            if wiki and provider.wiki_config.get('mode')=='enhanced':
                provenance=wiki.get('provenance') or {}
                if provenance.get('mode')!='enhanced' or provenance.get('revision')!=snap.commit_sha or provenance.get('workspace_id')!=wid or provenance.get('snapshot_id')!=snap.id:raise ProviderError('旧Wiki不能冒充增强结果','source_revision')
            if not wiki:
                wiki=provider.wiki(snap,lambda t,d:step(rid,t,d),persist_task,lambda:cancelled(rid),saved.get('deepwiki_task_id'))
                check_wiki_inputs()
                if cancelled(rid):return
                if len(json.dumps(wiki,ensure_ascii=False))>2_000_000:raise ProviderError('Wiki输出超过2MB保存预算，请调整DeepWiki-Open覆盖后重试','deepwiki_output_budget')
                with Session.begin() as s:
                    r=s.get(Run,rid)
                    if r.status=='cancelled':return
                    _,_,save_fingerprint=collect_project(s,wid)
                    if save_fingerprint!=wiki_input_fingerprint:raise ProviderError('Wiki生成输入已更正，未保存晚到结果','source_revision')
                    r.result={**r.result,'wiki':wiki}
            from .project_inputs import collect_project
            from .optimization_review import generate as review_optimization
            with Session() as context_session:
                frozen,material,source_fingerprint=collect_project(context_session,wid)
                if frozen.id!=snap.id:raise ProviderError('调查期间项目快照已改变','source_revision')
            if req.get('constraints',material.get('constraints'))!=material.get('constraints'):raise ProviderError('用户约束已变更，请重新分析','source_revision')
            if material['role']!=req['role'] or material['jd_version_id']!=req['jd_version_id']:raise ProviderError('岗位已变更，请重新分析','source_revision')
            def check_active():
                if cancelled(rid):raise ProviderError('任务已取消','cancelled')
                with Session() as active_session:
                    _,_,active_fingerprint=collect_project(active_session,wid)
                    if active_fingerprint!=source_fingerprint:raise ProviderError('调查输入已更正','source_revision')
            if req.get('optimization_config'):material={**material,'advisor_config':req['optimization_config']}
            report,coverage=review_optimization(snap,material,lambda t,d:step(rid,t,d),check_active)
        if cancelled(rid):return
        with Session.begin() as s:
            r=s.get(Run,rid)
            if r.status=='cancelled':return
            if not req['demo']:
                _,_,current_fingerprint=collect_project(s,wid)
                if current_fingerprint!=source_fingerprint:raise ProviderError('调查期间输入已更正，未保存旧报告','source_revision')
            evidences=scoped(s,Evidence,wid)
            source_map={e.path:e.id for e in evidences if e.snapshot_id==snap.id and e.type in ('source_code','readme')}
            for source in coverage.get('source_evidence',[]):
                if source.get('path') and source['kind'] in ('code','documentation','test_source'):
                    record=attach(s,wid,'source_code',source['excerpt'],'shared-code://'+source['id'],snapshot_id=snap.id,path=source['path'],line_start=source.get('start_line'),line_end=source.get('end_line'))
                    source_map[source['path']]=record.id
            mode='demo' if req['demo'] else 'deepwiki_open'
            external=attach(s,wid,'external_analysis',json.dumps(wiki,ensure_ascii=False),f'{mode}://wiki/{snap.id}',snapshot_id=snap.id)
            for old in scoped(s,Improvement,wid):
                if old.snapshot_id==snap.id and old.details.get('analysis_kind')=='architecture':old.status='stale'
            invalidate(s,wid)
            improvement_ids=[]
            from .architecture_schema import legacy_direction
            for direction in report['directions']:
                d=legacy_direction(direction,report)
                if d['necessity']=='not_recommended':continue
                refs=[source_map[p] for p in d['source_paths'] if p in source_map] if not req['demo'] else []
                details={**d,'run_id':rid,'report_schema':report.get('schema_version','architecture-v1'),'analysis_kind':'architecture','problem':d['business_problem'],'paths':', '.join(d['source_paths']),
                    'source_evidence_ids':refs,'analysis_pack_ref':coverage.get('analysis_pack_id'),'external_analysis_evidence_id':external.id,'coverage':snap.coverage,
                    'status_note':'优化规划，尚未实施，预期价值需验证；不是个人贡献','acceptance_criteria':d['validation_plan'],'hypothesis':'；'.join(d['assumptions'])}
                i=Improvement(workspace_id=wid,snapshot_id=snap.id,jd_version_id=req['jd_version_id'],details=details);s.add(i);s.flush();improvement_ids.append(i.id)
            r.result={**r.result,'report':report,'review_coverage':coverage,'mode':mode,'analysis_kind':'architecture','improvement_ids':improvement_ids,
                'external_analysis_evidence_id':external.id,'analysis_pack_ref':coverage.get('analysis_pack_id'),'source_evidence_ids':list(dict.fromkeys(source_map.values())),'usage':{'preparation_model':[c for c in coverage.get('calls',[]) if not c['stage'].startswith('OPTIMIZATION_')],'optimization_model':[c for c in coverage.get('calls',[]) if c['stage'].startswith('OPTIMIZATION_')],'web_tools':coverage.get('web_tools',[]),'upstream_wiki':{'status':'unknown','usage':None},'wiki':{'status':'unknown','reason':'上游未返回汇总用量'},'shared_analysis':[c for c in coverage.get('calls',[]) if not c['stage'].startswith('OPTIMIZATION_')],'optimization':[c for c in coverage.get('calls',[]) if c['stage'].startswith('OPTIMIZATION_')],'embedding':coverage.get('embedding_usage',[])},
                'elapsed_seconds':time.monotonic()-start,'limitations':'全面Wiki不等于全覆盖或运行认证；建议来自项目架构必要性评审。'}
            r.status='completed';r.error=None
    finally:
        if provider:provider.close()

