import json
import re
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from .db import *
from .schemas import *
from .memory import *
from .providers import GitHub, ModelProvider, ProviderError, demo_fixture, repo_name
from .analysis import recover_runs, submit, still_executing
from .agent import SKILLS, load_skill
from .repository_upload import import_zip, MAX_ARCHIVE

@asynccontextmanager
async def lifespan(app):
    migrate(); recover_runs(); discussion_store.recover(); yield
app = FastAPI(title='RepoInsight', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['http://127.0.0.1:5173','http://localhost:5173'], allow_methods=['*'], allow_headers=['*'])
def session():
    with Session() as s:
        try: yield s; s.commit()
        except Exception: s.rollback(); raise
@app.middleware('http')
async def trace(request, call_next):
    request.state.trace_id=uid()
    upload=request.url.path.endswith('/repository-upload') and request.method=='POST'
    limit=MAX_ARCHIVE if upload else 300000
    if int(request.headers.get('content-length','0') or 0)>limit:
        return JSONResponse(status_code=413,content={'error':{'code':'too_large','message':'仓库ZIP超过20 MB' if upload else '材料请求超过300 KB','trace_id':request.state.trace_id}})
    response=await call_next(request); response.headers['X-Request-ID']=request.state.trace_id
    return response
@app.exception_handler(HTTPException)
async def error(request, exc):
    return JSONResponse(status_code=exc.status_code,content={'error':{'code':str(exc.status_code),'message':str(exc.detail),'trace_id':request.state.trace_id}})
@app.exception_handler(ProviderError)
async def provider_error(request, exc):
    return JSONResponse(status_code=502,content={'error':{'code':exc.code,'message':str(exc),'trace_id':request.state.trace_id}})
@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    details=[{'field':'.'.join(map(str,e['loc'])),'message':e['msg']} for e in exc.errors()]
    return JSONResponse(status_code=422,content={'error':{'code':'invalid_input','message':'输入校验失败','details':details,'trace_id':request.state.trace_id}})
@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    return JSONResponse(status_code=409,content={'error':{'code':'conflict','message':'并发写入或关系约束冲突，请刷新后使用原幂等键安全重试','trace_id':request.state.trace_id}})
@app.exception_handler(OperationalError)
async def operational_error(request, exc):
    return JSONResponse(status_code=409,content={'error':{'code':'storage_busy','message':'存储暂时忙或不可写；请确认数据目录权限后刷新重试','trace_id':request.state.trace_id}})
@app.get('/api/config')
def config(): return {'model_mode':'demo' if ModelProvider().demo else 'real','skills':SKILLS,'github':'public REST / optional token','max_material_chars':200000,
    'deepwiki_configured':bool(os.getenv('DEEPWIKI_BASE_URL')),'deepwiki_provider':os.getenv('DEEPWIKI_PROVIDER','google'),'deepwiki_model':os.getenv('DEEPWIKI_MODEL','服务默认'),
    'deepwiki_web_url':os.getenv('DEEPWIKI_WEB_URL',''), 'max_archive_bytes':MAX_ARCHIVE,'product_flow':'github_project_exploration'}
@app.get('/api/workspaces')
def workspaces(s=Depends(session)): return [asdict(w) for w in s.scalars(select(Workspace).order_by(Workspace.created_at.desc()))]
@app.post('/api/workspaces')
def new_workspace(body: WorkspaceInput, s=Depends(session,scope='function')):
    w=Workspace(**body.model_dump()); s.add(w); s.flush(); return asdict(w)
@app.get('/api/workspaces/{wid}')
def workspace(wid:str,summary:bool=False,s=Depends(session)):
    w=require(s,Workspace,wid)
    data={**asdict(w),**{name:[asdict(r) for r in scoped(s,cls,wid)] for name,cls in [('jd_versions',JD),('snapshots',Snapshot),('evidence',Evidence),('findings',Finding),('improvements',Improvement),('contributions',Contribution),('attempts',Attempt),('experiments',Experiment),('events',MemoryEvent),('messages',Message),('artifacts',Artifact),('runs',Run)]}}
    if summary:
        for evidence in data['evidence']:evidence['excerpt']=evidence['excerpt'][:300]
    return data
@app.post('/api/workspaces/{wid}/repository-link')
def save_repository_link(wid:str,body:RepositoryLinkInput,s=Depends(session)):
    require(s,Workspace,wid)
    owner,repo=repo_name(body.url)
    if not repo:raise HTTPException(422,'仓库名称无效')
    if any(r.status in ('queued','running') for r in scoped(s,Run,wid)):raise HTTPException(409,'请先等待或停止当前分析')
    url=f'https://github.com/{owner}/{repo}'
    previous=scoped(s,Snapshot,wid)
    from .source_reader import SourceReader
    reader=SourceReader(wid)
    try:revision=reader.resolve_revision(owner+'/'+repo)
    finally:reader.close()
    from .source_reader import resolved
    if not resolved(revision.get('commit_sha')):
        raise HTTPException(422,'无法解析 GitHub 仓库版本，未保存或替换现有仓库。'+revision.get('error','请检查访问权限')+'；恢复访问后请重新保存仓库链接。')
    if previous and previous[-1].metadata_json.get('github_url')==url and previous[-1].commit_sha==revision['commit_sha']:return asdict(previous[-1])
    snap=Snapshot(workspace_id=wid,owner=owner,repo=repo,commit_sha=revision['commit_sha'],
        metadata_json={'mode':'github','source_kind':'github_link','github_url':url,'revision':revision,'description':'GitHub链接；Wiki版本与独立源码证据分别核对'},
        coverage={'read_files':[],'omitted':[],'note':'仅保存链接，尚未获取源码；DeepWiki分析版本及引用需核对，不声称固定提交。'})
    s.add(snap);s.flush()
    for i in scoped(s,Improvement,wid):i.status='stale'
    for f in scoped(s,Finding,wid):f.status='stale'
    invalidate(s,wid)
    # The browser immediately refreshes after this response; make the snapshot visible first.
    result=asdict(snap);s.commit()
    return result

@app.post('/api/workspaces/{wid}/repository-upload')
async def upload_repository(wid:str,request:Request,s=Depends(session)):
    require(s,Workspace,wid)
    if any(r.status in ('queued','running') for r in scoped(s,Run,wid)):raise HTTPException(409,'分析进行中，请先等待或取消后再上传新快照')
    if request.headers.get('content-type','').split(';')[0]!='application/zip':raise HTTPException(415,'请上传ZIP文件（application/zip）')
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>MAX_ARCHIVE:raise HTTPException(413,'仓库ZIP超过20 MB')
    from urllib.parse import unquote
    filename=unquote(request.headers.get('X-Filename','repository.zip'))
    filename=Path(filename.replace('\\','/')).name[:150]
    return asdict(import_zip(s,wid,bytes(raw),filename))
@app.post('/api/workspaces/{wid}/architecture-runs')
def architecture_run(wid:str,body:ArchitectureRunInput,s=Depends(session)):
    w=require(s,Workspace,wid);snap=require(s,Snapshot,body.snapshot_id,wid);jd=latest_jd(s,wid)
    if snap.metadata_json.get('source_kind') not in ('archive','github_link'):raise HTTPException(422,'请先保存GitHub仓库链接')
    req={**body.model_dump(),'architecture':True,'role':w.role if w.role.strip() and w.role!='待填写' else '项目工程优化','jd_version_id':jd.id if jd else None,'jd_text':jd.raw_text if jd else '', 'target_origin':'jd' if jd and jd.raw_text.strip() else 'role_inferred'}
    old=s.scalar(select(Run).where(Run.workspace_id==wid,Run.idempotency_key==body.idempotency_key))
    if old:
        if old.request!=req:raise HTTPException(409,'幂等键对应的快照或岗位JD已变化')
        return asdict(old)
    if any(r.status in ('queued','running') for r in scoped(s,Run,wid)):raise HTTPException(409,'当前工作区已有运行中的分析')
    r=Run(workspace_id=wid,request=req,idempotency_key=body.idempotency_key,result={'snapshot_id':snap.id});s.add(r);s.commit();submit(r.id);return asdict(r)
@app.patch('/api/workspaces/{wid}')
def update_workspace(wid:str,body:WorkspaceInput,s=Depends(session)):
    w=require(s,Workspace,wid)
    for k,v in body.model_dump().items(): setattr(w,k,v)
    invalidate(s,wid); return asdict(w)
@app.post('/api/workspaces/{wid}/jd-versions')
def add_jd(wid:str,body:TextInput,s=Depends(session)):
    require(s,Workspace,wid); old=latest_jd(s,wid)
    if old and old.raw_text==body.content:return asdict(old)
    jd=save_jd_version(s,wid,body.content);terms=jd.requirements
    return {**asdict(jd),'diff':{'added':list(set(terms)-set(old.requirements if old else [])),'removed':list(set(old.requirements if old else [])-set(terms))},'note':'只影响新候选/新方案排序与新稿选材；旧计划保留，贡献事实不变。'}

@app.post('/api/workspaces/{wid}/target')
def update_target(wid:str,body:TargetInput,s=Depends(session,scope='function')):
    jd=save_target(s,wid,body.role,body.jd)
    return {'role':body.role,'jd_version_id':jd.id if jd else None,'target_origin':'jd' if body.jd else 'role_inferred'}
@app.post('/api/workspaces/{wid}/repo-search')
def search_repos(wid:str,demo:bool=True,s=Depends(session)):
    w=require(s,Workspace,wid); load_skill('repo_discovery')
    if not demo: return {'mode':'real','candidates':GitHub().search(w,latest_jd(s,wid))}
    f=demo_fixture()
    return {'mode':'demo','candidates':[{'url':f'https://github.com/{f["owner"]}/{f["repo"]}','name':f'{f["owner"]}/{f["repo"]}','description':f['description'],'mode':'demo','match':f'练习兴趣 {w.interest}；技能 {w.skills}；岗位 {w.role}。演示 fixture，不是真实匹配搜索。','constraints':f'时间 {w.time_budget}；环境 {w.environment}。仅演示业务链路。','cost_basis':'三个示例文件，未执行或估计开发工时。'}]}
@app.post('/api/workspaces/{wid}/analysis-runs')
@app.post('/api/workspaces/{wid}/repo-snapshots')
def new_run(wid:str,body:RunInput,s=Depends(session)):
    require(s,Workspace,wid); repo_name(body.url)
    old=s.scalar(select(Run).where(Run.workspace_id==wid,Run.idempotency_key==body.idempotency_key))
    if old:
        if old.request != body.model_dump(): raise HTTPException(409,'幂等键已用于不同请求')
        return asdict(old)
    if any(r.status in ('queued','running') for r in scoped(s,Run,wid)): raise HTTPException(409,'该工作区已有运行中的任务')
    r=Run(workspace_id=wid,request=body.model_dump(),idempotency_key=body.idempotency_key); s.add(r); s.commit(); submit(r.id); return asdict(r)
@app.get('/api/runs/{rid}')
def run(rid:str,workspace_id:str,s=Depends(session)): return asdict(require(s,Run,rid,workspace_id))
@app.post('/api/runs/{rid}/cancel')
def cancel(rid:str,workspace_id:str,s=Depends(session)):
    r=require(s,Run,rid,workspace_id)
    s.execute(update(Run).where(Run.id==rid,Run.workspace_id==workspace_id,Run.status.in_(('queued','running'))).values(status='cancelled'))
    s.refresh(r)
    return asdict(r)
@app.post('/api/runs/{rid}/retry')
def retry(rid:str,workspace_id:str,s=Depends(session)):
    r=require(s,Run,rid,workspace_id)
    if r.request.get('resume_generation'):
        raise HTTPException(409,'历史简历任务已退役，不能重新生成')
    if r.status not in ('failed','interrupted','cancelled'): raise HTTPException(409,'只有失败、中断或取消的任务可重试')
    if still_executing(rid): raise HTTPException(409,'上一次任务正在停止，请稍后重试；已避免同一任务并发执行')
    if any(x.id != r.id and x.status in ('queued','running') for x in scoped(s,Run,workspace_id)): raise HTTPException(409,'工作区已有进行中的任务')
    r.status='queued'; r.error=None; s.commit(); submit(r.id); return asdict(r)
@app.post('/api/workspaces/{wid}/evidence')
def new_evidence(wid:str,body:EvidenceInput,s=Depends(session)):
    require(s,Workspace,wid)
    e=attach(s,wid,body.type,body.excerpt,body.source_ref); invalidate(s,wid)
    return asdict(e)
@app.get('/api/workspaces/{wid}/evidence/{eid}')
def read_evidence(wid:str,eid:str,s=Depends(session)): return asdict(require(s,Evidence,eid,wid))
@app.post('/api/workspaces/{wid}/contributions')
def new_contribution(wid:str,body:ContributionInput,s=Depends(session)):
    require(s,Workspace,wid); return asdict(save_contribution(s,wid,body.model_dump()))
@app.get('/api/workspaces/{wid}/contributions')
def contributions(wid:str,s=Depends(session)):
    require(s,Workspace,wid); return [asdict(c) for c in scoped(s,Contribution,wid)]
@app.patch('/api/contributions/{cid}')
def correct_contribution(cid:str,body:ContributionPatch,s=Depends(session)):
    d=body.model_dump(); expected=d.pop('expected_version'); wid=d.pop('workspace_id')
    return asdict(save_contribution(s,wid,d,cid,expected))
@app.post('/api/workspaces/{wid}/attempts')
def new_attempt(wid:str,body:AttemptInput,s=Depends(session)):
    c=require(s,Contribution,body.contribution_id,wid)
    check_evidence(s,wid,body.evidence_ids)
    a=Attempt(workspace_id=wid,contribution_id=c.id,details=body.model_dump()); s.add(a); s.flush()
    s.add(MemoryEvent(workspace_id=wid,entity_type='attempt',entity_id=a.id,operation='append',after=asdict(a))); invalidate(s,wid,[c.id]); return asdict(a)
@app.post('/api/workspaces/{wid}/experiments')
def new_experiment(wid:str,body:ExperimentInput,s=Depends(session)):
    c=require(s,Contribution,body.contribution_id,wid); evs=check_evidence(s,wid,body.source_evidence_ids)
    if not any(e.type=='test_report' for e in evs): raise HTTPException(422,'对照实验需关联用户提交的测试报告')
    d=body.model_dump(); exp=Experiment(workspace_id=wid,contribution_id=c.id,details=d); s.add(exp); s.flush()
    s.add(MemoryEvent(workspace_id=wid,entity_type='experiment',entity_id=exp.id,operation='append',after=asdict(exp))); invalidate(s,wid,[c.id]); return asdict(exp)
@app.post('/api/improvements/{iid}/select')
def choose_improvement(iid:str,workspace_id:str,s=Depends(session)):
    i=require(s,Improvement,iid,workspace_id)
    if i.status=='stale': raise HTTPException(409,'方案引用旧快照，请重新分析后选择')
    # Legacy single-choice endpoint keeps its contract, sharing atomic state updates.
    operations=[{'op':'update_improvement_decision','target_id':other.id,'data':{'decision':'exploring'}} for other in scoped(s,Improvement,workspace_id) if other.status=='selected' and other.id!=iid]
    operations.append({'op':'update_improvement_decision','target_id':iid,'data':{'decision':'selected'}})
    interaction.mutation(s,workspace_id,Mutation(expected_version=interaction.state(s,workspace_id)['version'],mutation_id=uid(),operations=operations))
    s.get(Workspace,workspace_id).stage='practice';return asdict(i)
@app.get('/api/artifacts/{aid}')
def artifact(aid:str,workspace_id:str,s=Depends(session)): return asdict(require(s,Artifact,aid,workspace_id))
@app.get('/api/artifacts/{aid}/export')
def export(aid:str,workspace_id:str,s=Depends(session)):
    a=require(s,Artifact,aid,workspace_id)
    text=('> 此旧版本需重新检查；贡献、JD 或快照已更新。\n\n' if a.review_status=='needs_review' else '')+a.content
    audit=next((c for c in a.claims if c.get('kind')=='writing_review'),{})
    if audit:
        if not audit.get('structured_draft'):text='> 历史稿没有逐句证据映射，未回填核验状态。\n\n'+text
        elif audit.get('generation_context',{}).get('output_mode')=='project_reference':text='> 项目能力参考稿，上游能力不代表个人贡献；源码与Wiki核验范围请查看审查记录。\n\n'+text
    return Response(text,media_type='text/markdown',headers={'Content-Disposition':f'attachment; filename="{a.type}-v{a.version}.md"'})
@app.post('/api/workspaces/{wid}/messages')
def message(wid:str,body:TextInput):
    raise HTTPException(410,'旧聊天入口已停用，请使用 conversations 会话接口；显式贡献表单保留')
@app.get('/api/workspaces/{wid}/messages')
def messages(wid:str,s=Depends(session)):
    require(s,Workspace,wid); return [asdict(m) for m in scoped(s,Message,wid)]

from . import interaction_service as interaction
from .interaction_contract import Mutation,DiscussionInput
@app.get('/api/workspaces/{wid}/interaction')
def interaction_state(wid:str,s=Depends(session)):return interaction.state(s,wid)
@app.post('/api/workspaces/{wid}/interaction/mutations')
def interaction_mutation(wid:str,body:Mutation,s=Depends(session,scope='function')):return interaction.mutation(s,wid,body)
@app.post('/api/workspaces/{wid}/interaction/chat')
def interaction_chat(wid:str,body:DiscussionInput):
    raise HTTPException(410,'聊天不再执行业务写入，请使用 conversations 讨论接口；业务修改请使用独立表单')
from . import wiki_chat
@app.post('/api/workspaces/{wid}/wiki-chat')
def wiki_question(wid:str,body:wiki_chat.WikiQuestion):
    raise HTTPException(410,'请刷新前端，使用 conversations 接口；客户端 history 不再作为历史记录')

from . import discussion_memory as discussion_store
from .discussion_contract import OpenConversation, Question, MemoryChange, CancelTurn
from .discussion_service import answer_stream
@app.post('/api/workspaces/{wid}/conversations')
def conversation_open(wid:str,body:OpenConversation):return discussion_store.open_conversation(wid,body.surface)
@app.get('/api/workspaces/{wid}/conversations/{cid}')
def conversation_read(wid:str,cid:str,offset:int=0,limit:int=50):
    if offset<0 or limit<1 or limit>100:raise HTTPException(422,'分页范围无效')
    return discussion_store.view(wid,cid,offset,limit)
@app.post('/api/workspaces/{wid}/conversations/{cid}/turns')
def conversation_send(wid:str,cid:str,body:Question):
    ticket=discussion_store.begin(wid,cid,body)
    return StreamingResponse(answer_stream(wid,cid,body,ticket),media_type='application/x-ndjson',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})
@app.post('/api/workspaces/{wid}/conversations/{cid}/cancel')
def conversation_cancel(wid:str,cid:str,body:CancelTurn):return discussion_store.cancel(wid,cid,body.request_id)
@app.post('/api/workspaces/{wid}/conversations/{cid}/memory')
def conversation_memory(wid:str,cid:str,body:MemoryChange):return discussion_store.change_memory(wid,cid,body)
@app.delete('/api/workspaces/{wid}/conversations/{cid}')
def conversation_delete(wid:str,cid:str):
    discussion_store.delete_conversation(wid,cid);return {'deleted':True}
@app.delete('/api/workspaces/{wid}/discussion-memory')
def discussion_purge(wid:str):
    discussion_store.purge(wid);return {'deleted':True}

DIST=Path(__file__).resolve().parents[2]/'frontend'/'dist'
if DIST.exists(): app.mount('/',StaticFiles(directory=DIST,html=True),name='web')

