"""Artifact orchestration: frozen inputs, short transactions, admission and persistence."""
from fastapi import HTTPException
from sqlalchemy import select, update
from .db import Workspace, Artifact, Run, JD, Session, asdict
from .memory import require, latest_jd, scoped, compose, save_target
from .providers import ProviderError
from .agent import load_skill
from .task_lifecycle import artifact_lease, check_generation


def create_artifact(s, wid, body):
    with artifact_lease(wid):
        job={'run_id':None}
        try:
            result = _create_artifact(s, wid, body, job)
            s.commit()  # Persist before releasing admission, including idempotent returns.
            return result
        except Exception as exc:
            s.rollback()
            if job['run_id']:
                with Session.begin() as ps:
                    ps.execute(update(Run).where(Run.id==job['run_id'],Run.workspace_id==wid,Run.status=='running').values(
                        status='failed',error=str(exc)[:1000] if isinstance(exc,ProviderError) else '内部生成错误，阶段记录已保留'))
            raise


def _create_artifact(s, wid, body, job):
    w=require(s,Workspace,wid)
    if body.type=='resume' and body.writing_mode!='model' and body.output_mode=='personal_resume':
        raise HTTPException(422,'规则参考稿仅支持项目参考类型；个人贡献稿请使用模型写作')
    if body.target_role is not None or body.target_jd is not None:
        current=latest_jd(s,wid)
        save_target(s,wid,body.target_role if body.target_role is not None else w.role,body.target_jd if body.target_jd is not None else (current.raw_text if current else ''))
    old=s.scalar(select(Artifact).where(Artifact.workspace_id==wid,Artifact.idempotency_key==body.idempotency_key))
    if old:
        if old.type != body.type: raise HTTPException(409,'幂等键已用于其他产物类型')
        if body.type=='resume' and (body.writing_mode=='model')!=any(c.get('kind')=='writing_review' for c in old.claims):raise HTTPException(409,'幂等键已用于不同简历生成方式')
        audit=next((c for c in old.claims if c.get('kind')=='writing_review'),{})
        ctx=audit.get('generation_context',{})
        jd=latest_jd(s,wid)
        if ctx and (ctx.get('output_mode')!=body.output_mode or ctx.get('target_dimensions',[])!=body.target_dimensions or ctx.get('role')!=w.role or ctx.get('jd_version_id')!=(jd.id if jd else None)):raise HTTPException(409,'幂等键对应的输出类型或目标已变化')
        return asdict(old)
    if any(r.status in ('queued','running') for r in scoped(s,Run,wid)):
        raise HTTPException(409,'当前工作区已有运行中的任务')
    load_skill('resume_composition' if body.type != 'task_pack' else 'improvement_planning'); load_skill('claim_review')
    content='';deps=[];claims=[];jd=latest_jd(s,wid)
    if body.type!='resume' or body.writing_mode!='model':
        content,deps,claims,jd=compose(s,wid,body.type)
    review_status='current'
    if body.type=='resume' and body.writing_mode=='model':
        from .resume_writer import collect,write
        snap,material,fingerprint=collect(s,wid)
        from .resume_support import source_ledger
        deps,claims=source_ledger(snap,material)
        source_run=require(s,Run,material['run_id'],wid) if material.get('run_id') else None
        if source_run and source_run.result.get('external_analysis_evidence_id'):
            deps.append(source_run.result['external_analysis_evidence_id'])
        from .resume_contract import GenerationContext
        from .source_reader import resolved
        context=GenerationContext(workspace_id=wid,snapshot_id=snap.id,commit_sha=snap.commit_sha,revision_status='resolved' if resolved(snap.commit_sha) else 'content_hash_bound' if snap.commit_sha.startswith('archive-sha256:') else 'unresolved',role=material['role'],jd_version_id=material['jd_version_id'],target_origin='jd' if material['jd'] else 'role_inferred',material_fingerprint=fingerprint,output_mode=body.output_mode,target_dimensions=body.target_dimensions)
        run_key='resume:'+body.idempotency_key
        gen=s.scalar(select(Run).where(Run.workspace_id==wid,Run.idempotency_key==run_key))
        if gen and gen.request.get('generation_context')!=context.model_dump():raise HTTPException(409,'重试输入版本已变化，请使用新的生成标识')
        if gen and gen.status=='running':raise HTTPException(409,'该生成正在运行')
        if not gen:gen=Run(workspace_id=wid,request={'resume_generation':True,'generation_context':context.model_dump()},idempotency_key=run_key,result={});s.add(gen);s.flush()
        gen.status='running';gen.error=None;gen_id=gen.id
        job['run_id']=gen_id
        def progress(record,result):
            with Session.begin() as ps:
                r=require(ps,Run,gen_id,wid)
                if r.status!='running':raise HTTPException(409,'生成已停止')
                r.steps=r.steps+[record];r.result={**r.result,**result}
        material['_generation_context']=context.model_dump();material['_target_dimensions']=body.target_dimensions;material['_progress']=progress;material['_check_active']=lambda:check_generation(gen_id,wid)
        jd_id=jd.id if jd else None
        s.commit()  # Do not hold a SQLite snapshot throughout slow model calls.
        content,audit=write(snap,material)
        check_generation(gen_id,wid)
        s.expire_all()
        _,_,current_fingerprint=collect(s,wid)
        if current_fingerprint!=fingerprint:
            gen=require(s,Run,gen_id,wid);gen.status='failed';gen.error='生成期间输入已变更，未保存为当前版本';s.commit()
            raise HTTPException(409,'写作期间项目/JD/优化材料已更正，请根据最新材料重新生成')
        old=s.scalar(select(Artifact).where(Artifact.workspace_id==wid,Artifact.idempotency_key==body.idempotency_key))
        if old:
            if not any(c.get('kind')=='writing_review' for c in old.claims):raise HTTPException(409,'幂等键已用于规则参考稿，请使用新的生成标识')
            return asdict(old)
        jd=s.get(JD,jd_id) if jd_id else None
        for claim in claims:claim['usage']='source_ledger_not_generated_text'
        deps=list(dict.fromkeys(deps+([material['run_id']] if material.get('run_id') else [])+[gen_id]+[e['id'] for e in material['user_materials']]+[e['id'] for e in material['experiments']]))
        audit['material_sha256']=fingerprint
        claims.append(audit)
        gen=require(s,Run,gen_id,wid)
        if gen.status!='running':raise HTTPException(409,'生成已停止，未保存产物')
        result={**gen.result,'status':audit['status'],'generation_context':audit.get('generation_context',context.model_dump())}
        transition=s.execute(update(Run).where(Run.id==gen_id,Run.workspace_id==wid,Run.status=='running').values(status='completed',result=result))
        if transition.rowcount!=1:raise HTTPException(409,'生成已停止，未保存产物')
        audit['generation_run_id']=gen_id
        review_status='current' if audit['status']=='passed' else 'needs_review'
    version=sum(a.type==body.type for a in scoped(s,Artifact,wid))+1
    a=Artifact(workspace_id=wid,type=body.type,version=version,content=content,dependency_ids=deps,claims=claims,jd_version_id=jd.id if jd else None,idempotency_key=body.idempotency_key,review_status=review_status)
    s.add(a); s.flush(); return asdict(a)
