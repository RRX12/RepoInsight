import json
import re
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from .db import *
from .schemas import *
from .memory import *
from .providers import GitHub, ModelProvider, ProviderError, demo_fixture, repo_name
from .analysis import recover_runs, submit, still_executing
from .agent import chat, SKILLS, load_skill
from .repository_upload import import_zip, MAX_ARCHIVE

@asynccontextmanager
async def lifespan(app):
    migrate(); recover_runs(); yield
app = FastAPI(title='RepoCareer', lifespan=lifespan)
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
    'max_archive_bytes':MAX_ARCHIVE,'product_flow':'github_architecture_review'}
@app.get('/api/workspaces')
def workspaces(s=Depends(session)): return [asdict(w) for w in s.scalars(select(Workspace).order_by(Workspace.created_at.desc()))]
@app.post('/api/workspaces')
def new_workspace(body: WorkspaceInput, s=Depends(session)):
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
    if previous and previous[-1].metadata_json.get('github_url')==url:return asdict(previous[-1])
    snap=Snapshot(workspace_id=wid,owner=owner,repo=repo,commit_sha='unresolved:deepwiki-default-branch',
        metadata_json={'mode':'github','source_kind':'github_link','github_url':url,'description':'GitHub链接，由DeepWiki-Open获取仓库'},
        coverage={'read_files':[],'omitted':[],'note':'仅保存链接，尚未获取源码；DeepWiki分析版本及引用需核对，不声称固定提交。'})
    s.add(snap);s.flush()
    for i in scoped(s,Improvement,wid):i.status='stale'
    for f in scoped(s,Finding,wid):f.status='stale'
    invalidate(s,wid)
    return asdict(snap)

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
    if not w.role.strip() or w.role=='待填写' or not jd or not jd.raw_text.strip():raise HTTPException(422,'请先填写岗位名称和JD')
    if snap.metadata_json.get('source_kind') not in ('archive','github_link'):raise HTTPException(422,'请先保存GitHub仓库链接')
    req={**body.model_dump(),'architecture':True,'role':w.role,'jd_version_id':jd.id,'jd_text':jd.raw_text}
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
    terms=list(dict.fromkeys(re.findall(r'[A-Za-z][A-Za-z0-9+#._-]{1,30}|[\u4e00-\u9fff]{2,8}',body.content)))[:30]
    jd=JD(workspace_id=wid,raw_text=body.content,requirements=terms,version=(old.version+1 if old else 1),supersedes_id=old.id if old else None)
    s.add(jd); s.flush(); invalidate(s,wid)
    s.add(MemoryEvent(workspace_id=wid,entity_type='jd',entity_id=jd.id,operation='new_version',before=asdict(old) if old else {},after=asdict(jd)))
    return {**asdict(jd),'diff':{'added':list(set(terms)-set(old.requirements if old else [])),'removed':list(set(old.requirements if old else [])-set(terms))},'note':'只影响新候选/新方案排序与新稿选材；旧计划保留，贡献事实不变。'}
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
    if r.status in ('queued','running'): r.status='cancelled'
    return asdict(r)
@app.post('/api/runs/{rid}/retry')
def retry(rid:str,workspace_id:str,s=Depends(session)):
    r=require(s,Run,rid,workspace_id)
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
    for other in scoped(s,Improvement,workspace_id):
        if other.status=='selected': other.status='proposed'
    i.status='selected'; s.get(Workspace,workspace_id).stage='practice'; invalidate(s,workspace_id); return asdict(i)
@app.post('/api/workspaces/{wid}/artifacts')
def new_artifact(wid:str,body:ArtifactInput,s=Depends(session)):
    require(s,Workspace,wid)
    old=s.scalar(select(Artifact).where(Artifact.workspace_id==wid,Artifact.idempotency_key==body.idempotency_key))
    if old:
        if old.type != body.type: raise HTTPException(409,'幂等键已用于其他产物类型')
        if body.type=='resume' and (body.writing_mode=='model')!=any(c.get('kind')=='writing_review' for c in old.claims):raise HTTPException(409,'幂等键已用于不同简历生成方式')
        return asdict(old)
    load_skill('resume_composition' if body.type != 'task_pack' else 'improvement_planning'); load_skill('claim_review')
    content,deps,claims,jd=compose(s,wid,body.type)
    review_status='current'
    if body.type=='resume' and body.writing_mode=='model':
        from .resume_writer import collect,write
        snap,material,fingerprint=collect(s,wid)
        jd_id=jd.id if jd else None
        s.commit()  # Do not hold a SQLite snapshot throughout slow model calls.
        content,audit=write(snap,material)
        s.expire_all()
        _,_,current_fingerprint=collect(s,wid)
        if current_fingerprint!=fingerprint:raise HTTPException(409,'写作期间项目/JD/优化材料已更正，请根据最新材料重新生成')
        old=s.scalar(select(Artifact).where(Artifact.workspace_id==wid,Artifact.idempotency_key==body.idempotency_key))
        if old:
            if not any(c.get('kind')=='writing_review' for c in old.claims):raise HTTPException(409,'幂等键已用于规则参考稿，请使用新的生成标识')
            return asdict(old)
        jd=s.get(JD,jd_id) if jd_id else None
        for claim in claims:claim['usage']='source_ledger_not_generated_text'
        deps=list(dict.fromkeys(deps+[material['run_id']]+[e['id'] for e in material['user_materials']]+[e['id'] for e in material['experiments']]))
        audit['material_sha256']=fingerprint
        claims.append(audit)
        review_status='current' if audit['status']=='passed' else 'needs_review'
    version=sum(a.type==body.type for a in scoped(s,Artifact,wid))+1
    a=Artifact(workspace_id=wid,type=body.type,version=version,content=content,dependency_ids=deps,claims=claims,jd_version_id=jd.id if jd else None,idempotency_key=body.idempotency_key,review_status=review_status)
    s.add(a); s.flush(); return asdict(a)
@app.get('/api/artifacts/{aid}')
def artifact(aid:str,workspace_id:str,s=Depends(session)): return asdict(require(s,Artifact,aid,workspace_id))
@app.get('/api/artifacts/{aid}/export')
def export(aid:str,workspace_id:str,s=Depends(session)):
    a=require(s,Artifact,aid,workspace_id)
    text=('> 此旧版本需重新检查；贡献、JD 或快照已更新。\n\n' if a.review_status=='needs_review' else '')+a.content
    return Response(text,media_type='text/markdown',headers={'Content-Disposition':f'attachment; filename="{a.type}-v{a.version}.md"'})
@app.post('/api/workspaces/{wid}/messages')
def message(wid:str,body:TextInput,s=Depends(session)):
    require(s,Workspace,wid)
    m=Message(workspace_id=wid,role='user',content=body.content); s.add(m); s.commit()
    state=chat(wid,body.content,m.id); output=state['output']
    # Only validated candidate fields are shown. No LLM write privileges.
    proposal=output.get('proposal',{})
    if proposal:
        try: proposal=ContributionInput.model_validate(proposal).model_dump()
        except Exception: proposal={'needs_clarification':True,'note':'模型候选缺字段或状态无效，请手工确认后录入'}
    reply=Message(workspace_id=wid,role='assistant',content=output['reply'],proposal={'candidate':proposal,'mode':output['mode'],'usage':output.get('usage'),'tool_steps':state['tool_steps']}); s.add(reply); s.flush(); return asdict(reply)
@app.get('/api/workspaces/{wid}/messages')
def messages(wid:str,s=Depends(session)):
    require(s,Workspace,wid); return [asdict(m) for m in scoped(s,Message,wid)]
DIST=Path(__file__).resolve().parents[2]/'frontend'/'dist'
if DIST.exists(): app.mount('/',StaticFiles(directory=DIST,html=True),name='web')

