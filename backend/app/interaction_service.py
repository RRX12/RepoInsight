"""Versioned project forms; discussion cannot invoke business mutations."""
import copy
import hashlib
import json
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select,update
from .db import Workspace,InteractionState,JD,Contribution,Improvement,Artifact,Message,MemoryEvent,Finding,Evidence,Snapshot,Run,asdict,uid,now
from .memory import require,scoped,latest_jd,save_target,save_contribution,invalidate,check_evidence
from .schemas import ContributionInput
from .interaction_contract import ImprovementData,MetricData

def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def state(s,wid):
    w=require(s,Workspace,wid);row=s.get(InteractionState,wid);data=copy.deepcopy(row.data) if row else {}
    jd=latest_jd(s,wid)
    parts={name:[asdict(x) for x in scoped(s,cls,wid)] for name,cls in [('contributions',Contribution),('improvements',Improvement),('evidence',Evidence),('findings',Finding),('snapshots',Snapshot)]}
    version=digest({'workspace':asdict(w),'jd':asdict(jd) if jd else None,'parts':parts,'revision':row.revision if row else 0,'data':data})
    return {'version':version,'role':w.role,'jd':jd.raw_text if jd else '', 'jd_version_id':jd.id if jd else None,**parts,'metrics':data.get('metrics',[])}

def receipt(s,wid,mutation_id,payload):
    key='interaction:'+mutation_id
    event=s.scalar(select(MemoryEvent).where(MemoryEvent.workspace_id==wid,MemoryEvent.entity_type=='interaction_receipt',MemoryEvent.entity_id==key))
    if event:
        if event.before.get('fingerprint')!=digest(payload):raise HTTPException(409,'同一mutation_id已用于不同请求')
        return event.after

def record_receipt(s,wid,mutation_id,payload,response):
    s.add(MemoryEvent(workspace_id=wid,entity_type='interaction_receipt',entity_id='interaction:'+mutation_id,operation='commit',before={'fingerprint':digest(payload)},after=response))

def lock_state(s,wid,expected):
    if state(s,wid)['version']!=expected:raise HTTPException(409,'项目信息已变化，未覆盖新内容，请刷新后重试')
    row=s.get(InteractionState,wid)
    if row:
        previous=row.revision
        result=s.execute(update(InteractionState).where(InteractionState.workspace_id==wid,InteractionState.revision==previous).values(revision=previous+1))
        if result.rowcount!=1:raise HTTPException(409,'并发修改冲突，未保存')
        s.refresh(row)
    else:
        row=InteractionState(workspace_id=wid,revision=1,data={});s.add(row);s.flush()
    return row,copy.deepcopy(row.data)

def validate(model,data):
    try:return model.model_validate(data).model_dump()
    except ValidationError as exc:raise HTTPException(422,'操作字段无效：'+'；'.join('.'.join(map(str,e['loc'])) for e in exc.errors())) from exc

def mutation(s,wid,body,source_message=None):
    payload=body.model_dump();old=receipt(s,wid,body.mutation_id,payload)
    if old:return old
    row,data=lock_state(s,wid,body.expected_version);changes=[];actions=[]
    for op in body.operations:
        before={};after={};ident=op.target_id;kind=op.op
        if kind=='update_jd':
            if set(op.data)-{'jd','role'} or 'jd' not in op.data:raise HTTPException(422,'JD操作字段无效')
            w=require(s,Workspace,wid);before={'role':w.role,'jd':latest_jd(s,wid).raw_text if latest_jd(s,wid) else ''}
            if not isinstance(op.data['jd'],str) or len(op.data['jd'])>20000:raise HTTPException(422,'JD格式无效')
            role=op.data.get('role',w.role)
            if not isinstance(role,str) or len(role)>1000:raise HTTPException(422,'岗位格式无效')
            jd=save_target(s,wid,role,op.data['jd']);after={'role':role,'jd':jd.raw_text if jd else ''};ident=jd.id if jd else wid
        elif kind=='update_contribution':
            existing=require(s,Contribution,ident,wid) if ident else None
            allowed=set(ContributionInput.model_fields)
            previous={k:v for k,v in asdict(existing).items() if k in allowed} if existing else {}
            d=validate(ContributionInput,{**previous,**op.data})
            if d['state']=='validated':raise HTTPException(422,'本入口仅记录用户报告完成，不提供自动验证状态')
            before=asdict(existing) if existing else {}
            saved=save_contribution(s,wid,d,ident,existing.version if existing else None,source_message);ident=saved.id;after=asdict(saved)
        elif kind=='create_improvement':
            d=validate(ImprovementData,op.data);check_evidence(s,wid,d['evidence_ids'])
            for fid in d['finding_ids']:require(s,Finding,fid,wid)
            if d['supersedes_id']:require(s,Improvement,d['supersedes_id'],wid)
            d.update(decision='exploring',implementation='not_started',version=1)
            jd=latest_jd(s,wid);saved=Improvement(workspace_id=wid,jd_version_id=jd.id if jd else None,details=d,status='proposed');s.add(saved);s.flush();ident=saved.id;after=asdict(saved)
        elif kind in ('edit_improvement','delete_improvement'):
            saved=require(s,Improvement,ident,wid);before=asdict(saved);d=copy.deepcopy(saved.details)
            if d.get('deleted'):raise HTTPException(409,'该方向已删除')
            if kind=='delete_improvement':
                if op.data:raise HTTPException(422,'删除方向不接收额外字段')
                d.update(deleted=True,decision='rejected');saved.status='abandoned'
            else:
                if set(op.data)-{'title','problem','proposal'}:raise HTTPException(422,'方向编辑字段无效')
                checked=validate(ImprovementData,{**{k:v for k,v in d.items() if k in ImprovementData.model_fields},**op.data})
                if not checked['title'].strip() or not checked['proposal'].strip():raise HTTPException(422,'请填写方向标题和具体内容')
                for key in ('title','problem','proposal'):d[key]=checked[key]
                # Edited proposals require a fresh completion declaration.
                d['implementation']='not_started'
            d['version']=d.get('version',1)+1;saved.details=d;after=asdict(saved)
        elif kind in ('update_improvement_decision','report_improvement_completed'):
            saved=require(s,Improvement,ident,wid);before=asdict(saved);d=copy.deepcopy(saved.details)
            if d.get('deleted'):raise HTTPException(409,'该方向已删除')
            if kind=='update_improvement_decision':
                if set(op.data)-{'decision','implementation'} or op.data.get('decision') not in ('exploring','selected','deferred','rejected'):raise HTTPException(422,'决策状态无效')
                if saved.status=='stale' and op.data['decision']=='selected':raise HTTPException(409,'方案基于旧快照，请先重新评估')
                if 'implementation' in op.data:
                    if op.data['implementation'] not in ('not_started','in_progress') or op.data['decision']!='selected':raise HTTPException(422,'实施状态只能在已采用方案上标记开始；完成须单独报告')
                    d['implementation']=op.data['implementation']
                d['decision']=op.data['decision'];saved.status={'exploring':'proposed','selected':'selected','deferred':'proposed','rejected':'abandoned'}[d['decision']]
            else:
                if op.data:raise HTTPException(422,'报告完成不接收认证字段')
                if d.get('decision',saved.status) not in ('selected',):raise HTTPException(422,'请先选择该方案，再报告完成')
                d['implementation']='user_reported_done';d['completion_source']='用户报告，未核查源码'
            d['version']=d.get('version',1)+1;saved.details=d;after=asdict(saved)
        elif kind in ('create_metric','update_metric'):
            metrics=data.setdefault('metrics',[])
            if kind=='update_metric':
                previous=next((m for m in metrics if m['id']==ident),None)
                if previous is None:raise HTTPException(404,'指标不属于当前项目')
                before=copy.deepcopy(previous);allowed=set(MetricData.model_fields)
                if set(op.data)-allowed:raise HTTPException(422,'指标包含非法字段')
                d=validate(MetricData,{**{k:v for k,v in previous.items() if k in allowed},**op.data})
            else:d=validate(MetricData,op.data);ident=uid()
            if d['improvement_id']:require(s,Improvement,d['improvement_id'],wid)
            if d['contribution_id']:require(s,Contribution,d['contribution_id'],wid)
            after={**d,'id':ident,'version':before.get('version',0)+1,'source':'user_reported','source_message_id':source_message}
            data['metrics']=[m for m in metrics if m['id']!=ident]+[after]
        else:raise HTTPException(422,'不支持的项目操作')
        changes.append({'op':kind,'id':ident})
        s.add(MemoryEvent(workspace_id=wid,entity_type='interaction_change',entity_id=ident or wid,operation=kind,before=before,after=after,source_message_id=source_message))
    if changes:
        invalidate(s,wid)
        data['stale_reasons']=list(dict.fromkeys(data.get('stale_reasons',[])+[x['op'] for x in changes]))
    data['actions']=actions;row.data=data;s.flush()
    response={'changes':changes,'actions':actions,'state':state(s,wid)}
    record_receipt(s,wid,body.mutation_id,payload,response);return response
