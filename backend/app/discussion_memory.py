"""SQLite discussion memory; short CAS transactions, no business-state writes."""
import copy,re,sqlite3,threading,json
from functools import wraps
from sqlalchemy import select,update,text,delete
from fastapi import HTTPException
from .db import DATA,Session,Conversation,Message,MemoryEvent,Workspace,Snapshot,uid,now,asdict
from .memory import require
from .resume_harness import digest
from .discussion_contract import Plan,MemoryChange

# Single-process MVP: serialize only short storage transactions, never model I/O.
_lock=threading.RLock()
def serialized(fn):
    @wraps(fn)
    def call(*args,**kwargs):
        with _lock:return fn(*args,**kwargs)
    return call

def messages(s,cid,wid):
    return [m for m in s.scalars(select(Message).where(Message.workspace_id==wid).order_by(Message.created_at,Message.id)) if m.proposal.get('discussion',{}).get('conversation_id')==cid]
def get(s,wid,cid):
    c=require(s,Conversation,cid,wid)
    if c.deleted_at:raise HTTPException(410,'会话已删除')
    return c
def cas(s,c,revision,data):
    changed=s.execute(update(Conversation).where(Conversation.id==c.id,Conversation.revision==revision,Conversation.deleted_at.is_(None)).values(revision=revision+1,data=data,updated_at=now())).rowcount
    if not changed:raise HTTPException(409,'会话已变化，请刷新；旧回答不会写回')
@serialized
def open_conversation(wid,surface):
    with Session.begin() as s:
        require(s,Workspace,wid)
        c=s.scalar(select(Conversation).where(Conversation.workspace_id==wid,Conversation.surface==surface,Conversation.deleted_at.is_(None)).order_by(Conversation.created_at.desc()))
        if c is None:c=Conversation(workspace_id=wid,surface=surface,data={'topics':[],'memories':[]});s.add(c);s.flush()
        return asdict(c)
def version(s,wid):
    snap=s.scalar(select(Snapshot).where(Snapshot.workspace_id==wid).order_by(Snapshot.created_at.desc()))
    return snap.commit_sha if snap else 'unknown'
def identity(s,wid):
    snap=s.scalar(select(Snapshot).where(Snapshot.workspace_id==wid).order_by(Snapshot.created_at.desc()))
    return snap.owner+'/'+snap.repo if snap else 'unknown'

def projection(s,c):
    items=[];revision=version(s,c.workspace_id)
    for other in s.scalars(select(Conversation).where(Conversation.workspace_id==c.workspace_id,Conversation.deleted_at.is_(None))):
        for raw in other.data.get('memories',[]):
            m=copy.deepcopy(raw)
            if other.id!=c.id and m['scope']!='workspace':continue
            if m['kind']=='code_observation' and (m['source_revision']!=revision or m.get('repo_identity')!=identity(s,c.workspace_id)) and m['status']=='active':m['status']='needs_recheck'
            items.append(m)
    return items

def workspace_memory_version(s,c):
    return digest([m for m in projection(s,c) if m['scope']=='workspace'])

def view(wid,cid,offset=0,limit=50):
    with Session() as s:
        c=get(s,wid,cid);rows=messages(s,cid,wid)
        return {**asdict(c),'messages':[asdict(m) for m in rows[offset:offset+limit]],'message_count':len(rows),'pending_requests':[m.proposal['discussion']['request_id'] for m in rows if m.proposal.get('discussion',{}).get('status')=='pending'],'memories':projection(s,c),'retention':'对话默认保留，不自动按天删除；可删除会话和项目讨论记忆。'}

def audit(s,c,operation,before,after,source=None):
    s.add(MemoryEvent(workspace_id=c.workspace_id,entity_type='discussion_memory',entity_id=c.id,operation=operation,before=copy.deepcopy(before),after=copy.deepcopy(after),source_message_id=source))
def apply_memory(s,c,data,candidate,source_ids,refs,revision):
    m=candidate.model_dump() if hasattr(candidate,'model_dump') else dict(candidate)
    if not set(m.get('source_message_ids',[]))<=set(source_ids):raise HTTPException(422,'记忆引用不属于当前会话输入')
    if not set(m.get('evidence_refs',[]))<=set(refs):raise HTTPException(422,'记忆引用未知证据')
    if m['kind']=='code_observation' and m.get('origin')!='source_observation' and m.get('action') not in ('RETRACT','RESOLVE'):raise HTTPException(422,'源码观察必须来自实际读取，不接受用户或助手自称核验')
    if m.get('origin')=='source_observation' and (not m.get('evidence_refs') or m.get('source_revision')!=revision or revision=='unknown'):raise HTTPException(422,'源码观察缺少版本绑定证据')
    items=data.setdefault('memories',[])
    if m['kind']=='code_observation':
        for old in items:
            if old['kind']=='code_observation' and old['status']=='active' and (old['source_revision']!=revision or old.get('repo_identity')!=m.get('repo_identity')):
                before=copy.deepcopy(old);old['status']='needs_recheck';audit(s,c,'VERSION_CHANGED',before,old)
    topic=data.get('active_topic_id') if m['scope']=='topic' else None
    target=next((x for x in items if x['id']==m.get('target_id') and x['status'] in ('active','needs_recheck')),None)
    if m.get('target_id') and target is None:raise HTTPException(409,'记忆目标已失效或不属于会话')
    if target and m['scope']=='topic':topic=target.get('topic_id')
    if target and (target['scope'],target.get('topic_id'),target['kind'],target['subject_key'])!=(m['scope'],topic,m['kind'],m['subject_key']):raise HTTPException(422,'更正不能静默改变范围、对象或类型')
    same=next((x for x in items if x['status']=='active' and (x['scope'],x.get('topic_id'),x['kind'],x['subject_key'],x['content'])==(m['scope'],topic,m['kind'],m['subject_key'],m['content'])),None)
    if same and m.get('action') not in ('RETRACT','RESOLVE'):
        before=copy.deepcopy(same);same['source_message_ids']=list(dict.fromkeys(same['source_message_ids']+m.get('source_message_ids',[])))
        if before!=same:audit(s,c,'NOOP_SOURCE',before,same)
        return same
    if target and target['origin']=='user_explicit' and m.get('origin')!='user_explicit':raise HTTPException(422,'助手意见不能覆盖用户要求')
    if m.get('action') in ('MERGE','SUPERSEDE','RETRACT','RESOLVE') and target is None:raise HTTPException(422,'更新必须指定有效记忆')
    if m.get('action') in ('RETRACT','RESOLVE'):
        before=copy.deepcopy(target);target['status']='retracted' if m['action']=='RETRACT' else 'resolved';audit(s,c,m['action'],before,target);return target
    conflict=any(x['status']=='active' and (x['scope'],x.get('topic_id'),x['kind'],x['subject_key'])==(m['scope'],topic,m['kind'],m['subject_key']) for x in items)
    record={k:m.get(k) for k in ('kind','scope','subject_key','content','origin','evidence_refs','source_revision','source_message_ids','repo_identity')}
    record.update(id=uid(),workspace_id=c.workspace_id,conversation_id=c.id,topic_id=topic,status='needs_recheck' if conflict and not target else 'active',version=target['version']+1 if target else 1,supersedes_id=target['id'] if target else None,created_at=now(),updated_at=now())
    if target:
        if m.get('action')=='MERGE':record['source_message_ids']=list(dict.fromkeys(target['source_message_ids']+record['source_message_ids']))
        before=copy.deepcopy(target);target['status']='superseded';audit(s,c,'SUPERSEDE',before,target)
    items.append(record);audit(s,c,'ADD',{},record,(m.get('source_message_ids') or [None])[0]);return record

@serialized
def change_memory(wid,cid,body):
    with Session.begin() as s:
        c=get(s,wid,cid);data=copy.deepcopy(c.data);receipts=data.setdefault('memory_requests',{})
        fingerprint=digest(body.model_dump(exclude={'expected_revision'}))
        if body.request_id in receipts:
            if receipts[body.request_id]!=fingerprint:raise HTTPException(409,'request_id内容不同')
            return {'revision':c.revision,'reused':True}
        if c.revision!=body.expected_revision:raise HTTPException(409,'会话版本已改变')
        mid=uid();s.add(Message(id=mid,workspace_id=wid,role='user',content=body.content,proposal={'discussion':{'conversation_id':cid,'status':'memory_edit','sequence':0}}));s.flush()
        m=body.model_dump(exclude={'expected_revision','request_id'});m.update(origin='user_explicit',source_message_ids=[mid],evidence_refs=[],source_revision='unknown')
        if body.kind=='code_observation' and body.action not in ('RETRACT','RESOLVE'):raise HTTPException(422,'手动笔记不能宣称源码核验，请用correction或proposal_note')
        result=apply_memory(s,c,data,m,[mid],[],version(s,wid));receipts[body.request_id]=fingerprint;cas(s,c,body.expected_revision,data)
        return {'memory':result,'revision':body.expected_revision+1}

@serialized
def begin(wid,cid,body):
    with Session.begin() as s:
        c=get(s,wid,cid);rows=messages(s,cid,wid);fingerprint=digest(body.model_dump(exclude={'expected_revision'}))
        old=next((m for m in rows if m.role=='user' and m.proposal.get('discussion',{}).get('request_id')==body.request_id),None)
        if old:
            meta=old.proposal['discussion']
            if meta['fingerprint']!=fingerprint:raise HTTPException(409,'request_id已用于不同问题')
            return {'replay':True,'user':asdict(old),'messages':[asdict(m) for m in rows if m.proposal.get('discussion',{}).get('turn_id')==meta['turn_id']]}
        if c.revision!=body.expected_revision:raise HTTPException(409,'会话版本已改变，请刷新')
        if any(m.proposal.get('discussion',{}).get('status')=='pending' for m in rows):raise HTTPException(409,'此会话正在回答，请等待或停止')
        data=copy.deepcopy(c.data);mid=uid();turn=uid();seq=max([m.proposal.get('discussion',{}).get('sequence',0) for m in rows]+[0])+1
        meta={'conversation_id':cid,'turn_id':turn,'sequence':seq,'request_id':body.request_id,'fingerprint':fingerprint,'status':'pending','source_refs':[]}
        user=Message(id=mid,workspace_id=wid,role='user',content=body.content,proposal={'discussion':meta});s.add(user);s.flush()
        # Unambiguous explicit commands are durable even when the answer fails.
        match=re.match(r'^(项目约束|约束|讨论笔记|待解决问题)[：:]\s*(.+)',body.content,re.S)
        if match:
            kind={'讨论笔记':'proposal_note','待解决问题':'open_question'}.get(match[1],'constraint')
            content=match[2].strip()
            if len(content)>2000:raise HTTPException(422,'请将持续约束缩小到2000字以内')
            apply_memory(s,c,data,dict(kind=kind,scope='workspace' if match[1]=='项目约束' else 'conversation',subject_key='explicit:'+digest(content)[:24],content=content,origin='user_explicit',source_message_ids=[mid],evidence_refs=[],source_revision='unknown',action='ADD'),[mid],[],version(s,wid))
        cas(s,c,body.expected_revision,data)
        return {'replay':False,'user':asdict(user),'revision':body.expected_revision+1,'source_revision':version(s,wid),'repo_identity':identity(s,wid),'workspace_memory_version':workspace_memory_version(s,c)}

@serialized
def finish(wid,cid,ticket,status,answer='',plan=None,load_log=None,evidence=None):
    with Session.begin() as s:
        c=s.get(Conversation,cid)
        if not c or c.workspace_id!=wid or c.deleted_at:return False
        user=s.get(Message,ticket['user']['id'])
        if user is None:return False
        meta=dict(user.proposal['discussion'])
        if meta['status']!='pending':return False
        if c.revision!=ticket['revision'] or version(s,wid)!=ticket['source_revision'] or identity(s,wid)!=ticket['repo_identity'] or workspace_memory_version(s,c)!=ticket['workspace_memory_version']:status='cancelled';answer=''
        data=copy.deepcopy(c.data)
        if status=='completed':
            if not answer.strip():raise HTTPException(422,'空回答不能提交')
            plan=plan or Plan();set_focus(data,plan)
            assistant=Message(workspace_id=wid,role='assistant',content=answer,proposal={'discussion':{**meta,'sequence':meta['sequence']+1,'status':'completed','source_refs':list(evidence or {}),'evidence_manifest':[{k:v for k,v in e.items() if k!='excerpt'} for e in (evidence or {}).values()],'source_revision':ticket['source_revision'],'load_log':load_log or {}}});s.add(assistant);s.flush()
            for candidate in plan.memory_candidates:
                # Automated user-explicit entries must quote this user's actual words.
                if candidate.origin=='user_explicit' and candidate.content not in user.content:raise HTTPException(422,'用户记忆必须引用当前原话')
                if candidate.scope=='workspace' and '整个项目' not in user.content and not user.content.startswith('项目约束'):raise HTTPException(422,'没有项目范围授权')
                if candidate.origin=='user_explicit' and candidate.action!='ADD' and not any(w in user.content for w in ('更正','改为','纠正','补充')):raise HTTPException(422,'没有明确记忆更新授权')
                if not set(candidate.source_message_ids)<={user.id}:raise HTTPException(422,'记忆引用不属于当前会话输入')
                if candidate.origin=='assistant_proposal':
                    if candidate.content not in answer:raise HTTPException(422,'派生笔记未出现在成功回答中')
                    candidate=candidate.model_copy(update={'source_message_ids':[assistant.id]})
                record=apply_memory(s,c,data,candidate,[user.id,assistant.id],list(evidence or {}),ticket['source_revision'])
                if candidate.origin=='assistant_proposal':record['supporting_memory_ids']=list((load_log or {}).get('memory_ids',[]))
            verified={k:v for k,v in (evidence or {}).items() if v.get('kind') in ('code','test_source') and v.get('commit_sha')==ticket['source_revision']}
            data['source_cache']={'query':plan.standalone_query,'revision':ticket['source_revision'],'repo_identity':ticket['repo_identity'],'evidence':verified}
            for eid,e in verified.items():
                observation=dict(kind='code_observation',scope='topic',subject_key=f"{e['path']}:{e['start_line']}-{e['end_line']}",content='已读取源码片段（仅此范围，不代表完整调用链）：'+e['excerpt'][:500],origin='source_observation',source_message_ids=[user.id],evidence_refs=[eid],source_revision=ticket['source_revision'],repo_identity=ticket['repo_identity'],action='ADD')
                record=apply_memory(s,c,data,observation,[user.id],list(verified),ticket['source_revision']);record['repo_identity']=ticket['repo_identity']
            for msg in (user,assistant):
                if fts_available(s):s.execute(text('INSERT INTO discussion_fts(message_id,conversation_id,workspace_id,content) VALUES(:m,:c,:w,:t)'),{'m':msg.id,'c':cid,'w':wid,'t':msg.content})
        meta['status']=status;user.proposal={**user.proposal,'discussion':meta}
        if c.revision==ticket['revision']:cas(s,c,c.revision,data)
        return status=='completed'

def fts_available(s):return bool(s.execute(text("SELECT name FROM sqlite_master WHERE name='discussion_fts'")).first())
@serialized
def delete_conversation(wid,cid):
    with Session.begin() as s:
        c=get(s,wid,cid);rows=messages(s,cid,wid)
        # Remove derivative audit content first, including FK references to deleted messages.
        ids=[m.id for m in rows]
        removed_memory_ids={m['id'] for m in c.data.get('memories',[])}
        ids+=remove_derived(s,wid,cid,removed_memory_ids)
        s.execute(delete(MemoryEvent).where(MemoryEvent.workspace_id==wid,MemoryEvent.entity_type=='discussion_memory',MemoryEvent.entity_id==cid))
        # Remove nested legacy receipts too: they may embed a message without a source FK.
        for event in s.scalars(select(MemoryEvent).where(MemoryEvent.workspace_id==wid)):
            serialized_content=json.dumps([event.before,event.after],ensure_ascii=False)
            if any(mid in serialized_content for mid in [*ids,*removed_memory_ids]):
                event.before={'redacted':True};event.after={'redacted':True}
        # Legacy business audit remains; old messages are redacted rather than breaking its FKs.
        for m in rows:
            referenced=s.scalar(select(MemoryEvent.id).where(MemoryEvent.source_message_id==m.id).limit(1))
            if referenced:
                for event in s.scalars(select(MemoryEvent).where(MemoryEvent.source_message_id==m.id)):
                    event.before={'redacted':True};event.after={'redacted':True}
                m.content='[会话已删除]';m.proposal={}
            else:s.delete(m)
        if fts_available(s):s.execute(text('DELETE FROM discussion_fts WHERE conversation_id=:c'),{'c':cid})
        c.data={};c.deleted_at=now();c.revision+=1
        cleanup_checkpoints(wid,ids)

@serialized
def recover():
    with Session.begin() as s:
        for m in s.scalars(select(Message)):
            meta=m.proposal.get('discussion',{})
            if meta.get('status')=='pending':m.proposal={**m.proposal,'discussion':{**meta,'status':'failed','error':'服务重启中断，不自动重试'}}


def cleanup_checkpoints(wid,message_ids=None):
    path=DATA/'agent-checkpoints.db'
    if not path.exists():return
    # Retired graph used workspace:message identity; fixed tables/parameterized values only.
    with sqlite3.connect(path) as db:
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ('checkpoints','writes'):
            if table not in tables:continue
            if message_ids is None:db.execute(f'DELETE FROM {table} WHERE thread_id LIKE ?',(wid+':%',))
            else:db.executemany(f'DELETE FROM {table} WHERE thread_id=?',[(wid+':'+mid,) for mid in message_ids])

@serialized
def cancel(wid,cid,request_id):
    with Session.begin() as s:
        c=get(s,wid,cid)
        for m in messages(s,cid,wid):
            meta=m.proposal.get('discussion',{})
            if m.role=='user' and meta.get('request_id')==request_id and meta.get('status')=='pending':
                m.proposal={**m.proposal,'discussion':{**meta,'status':'cancelled'}}
                cas(s,c,c.revision,copy.deepcopy(c.data))
                return {'cancelled':True}
        return {'cancelled':False}

def active(wid,cid,ticket):
    with Session() as s:
        c=s.get(Conversation,cid);m=s.get(Message,ticket['user']['id'])
        return bool(c and c.workspace_id==wid and not c.deleted_at and c.revision==ticket['revision'] and workspace_memory_version(s,c)==ticket['workspace_memory_version'] and m and m.proposal.get('discussion',{}).get('status')=='pending')

@serialized
def purge(wid):
    with Session() as s:
        require(s,Workspace,wid)
        ids=list(s.scalars(select(Conversation.id).where(Conversation.workspace_id==wid,Conversation.deleted_at.is_(None))))
    for cid in ids:delete_conversation(wid,cid)
    cleanup_checkpoints(wid)


@serialized
def commit_explicit(wid,cid,ticket,plan):
    """User statements survive answer failure; assistant deductions never do."""
    candidates=[m for m in plan.memory_candidates if m.origin=='user_explicit']
    if not candidates:return
    with Session.begin() as s:
        c=get(s,wid,cid)
        if c.revision!=ticket['revision']:raise HTTPException(409,'会话已变化')
        data=copy.deepcopy(c.data);content=ticket['user']['content']
        if any(m.scope=='topic' for m in candidates):set_focus(data,plan)
        for m in candidates:
            if m.content not in content:raise HTTPException(422,'用户记忆必须引用当前原话')
            if m.scope=='workspace' and '整个项目' not in content and not content.startswith('项目约束'):raise HTTPException(422,'缺少项目范围授权')
            if m.action!='ADD' and not any(w in content for w in ('更正','改为','纠正','补充')):raise HTTPException(422,'缺少明确更正授权')
            apply_memory(s,c,data,m,[ticket['user']['id']],[],ticket['source_revision'])
        cas(s,c,ticket['revision'],data);ticket['revision']+=1
        ticket['workspace_memory_version']=workspace_memory_version(s,c)
    plan.memory_candidates=[m for m in plan.memory_candidates if m.origin!='user_explicit']


def set_focus(data,plan):
    topics=data.setdefault('topics',[])
    if plan.topic_title:
        topic=next((t for t in topics if t['title']==plan.topic_title),None)
        if topic is None:
            topic={'id':uid(),'title':plan.topic_title,'aliases':[]};topics.append(topic)
        topic['refs']=plan.focused_refs
        for t in topics:t['active']=t['id']==topic['id']
        data['active_topic_id']=topic['id']
    data['focused_refs']=plan.focused_refs;data['pending_question']=plan.clarification


def remove_derived(s,wid,deleted_cid,removed_memory_ids):
    """Redact dependent answers, keeping independent user statements in other sessions."""
    removed_messages=set();changed=True
    others=list(s.scalars(select(Conversation).where(Conversation.workspace_id==wid,Conversation.id!=deleted_cid,Conversation.deleted_at.is_(None))))
    while changed:
        changed=False
        for c in others:
            data=copy.deepcopy(c.data);modified=False
            for m in messages(s,c.id,wid):
                meta=m.proposal.get('discussion',{})
                if m.role=='assistant' and set(meta.get('load_log',{}).get('memory_ids',[]))&removed_memory_ids:
                    removed_messages.add(m.id);m.content='[依赖的讨论记忆已删除]'
                    m.proposal={'discussion':{k:meta[k] for k in ('conversation_id','turn_id','sequence','request_id') if k in meta}|{'status':'cancelled'}}
                    if fts_available(s):s.execute(text('DELETE FROM discussion_fts WHERE message_id=:m'),{'m':m.id})
                    modified=True
            kept=[]
            for item in data.get('memories',[]):
                if item['origin']!='user_explicit' and (set(item['source_message_ids'])&removed_messages or set(item.get('supporting_memory_ids',[]))&removed_memory_ids):
                    removed_memory_ids.add(item['id']);modified=True
                else:kept.append(item)
            if modified:
                data['memories']=kept;cas(s,c,c.revision,data);changed=True
    return list(removed_messages)
