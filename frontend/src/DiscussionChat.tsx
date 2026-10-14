import React,{useEffect,useRef,useState} from 'react';
import Markdown from 'react-markdown';
type Row=Record<string,any>;
export default function DiscussionChat({wid,surface,runId,pageId,disabled=false}:{wid:string,surface:'wiki'|'discussion',runId?:string,pageId?:string,disabled?:boolean}){
 const [session,setSession]=useState<Row|null>(null),[question,setQuestion]=useState(''),[partial,setPartial]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [edit,setEdit]=useState<Row|null>(null),[note,setNote]=useState(''),[offset,setOffset]=useState(0);
 const current=useRef<Row|null>(null),abort=useRef<AbortController|null>(null),request=useRef(''),alive=useRef(true);
 const base='/api/workspaces/'+wid+'/conversations';
 async function api(url:string,method='GET',body?:Row){const r=await fetch(url,{method,headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined,cache:'no-store'});const d=await r.json();if(!r.ok)throw Error(d.error?.message||'请求失败');return d;}
 async function reload(cid:string,start=offset){const s=await api(base+'/'+cid+'?offset='+start);if(alive.current){current.current=s;setSession(s);}return s;}
 async function open(){const s=await api(base,'POST',{surface});if(!alive.current)return;const first=await reload(s.id,0);const start=Math.max(0,first.message_count-50);setOffset(start);if(start)await reload(s.id,start);}
 useEffect(()=>{alive.current=true;open().catch(e=>setError(e.message));return()=>{alive.current=false;abort.current?.abort();};},[wid,surface]);
 const pending=session?.pending_requests?.[0];
 async function stop(){const s=current.current;if(!s)return;const id=request.current||pending;abort.current?.abort();if(id)await api(base+'/'+s.id+'/cancel','POST',{request_id:id});await reload(s.id);}
 async function send(){const s=current.current;if(!s||busy||!question.trim())return;setBusy(true);setError('');setPartial('');const ctl=new AbortController();abort.current=ctl;request.current=crypto.randomUUID();let full='',done=false;
  try{const r=await fetch(base+'/'+s.id+'/turns',{method:'POST',headers:{'Content-Type':'application/json'},signal:ctl.signal,body:JSON.stringify({request_id:request.current,expected_revision:s.revision,content:question,run_id:runId||null,page_id:pageId||null})});if(!r.ok){const d=await r.json();throw Error(d.error?.message||'发送失败');}
   const reader=r.body!.getReader(),decoder=new TextDecoder();let buffer='';
   const consume=(line:string)=>{if(!line.trim())return;const e=JSON.parse(line);if(e.error)throw Error(e.error);if(e.delta){full+=e.delta;if(alive.current)setPartial(full);}if(e.done)done=true;};
   while(true){const p=await reader.read();buffer+=decoder.decode(p.value,{stream:!p.done});const lines=buffer.split('\n');buffer=lines.pop()||'';lines.forEach(consume);if(p.done)break;}consume(buffer);if(!done)throw Error('回答未完成，部分内容不会进入后续上下文');if(alive.current)setQuestion('');
  }catch(e){ctl.abort();if(alive.current)setError((e as Error).name==='AbortError'?'已停止；部分回答不保存，上游停止计费无法保证':(e as Error).message);}
  finally{if(alive.current){setBusy(false);setPartial('');try{const latest=await reload(s.id,0);const start=Math.max(0,latest.message_count-50);setOffset(start);if(start)await reload(s.id,start);}catch{} }abort.current=null;request.current='';}
 }
 async function change(m:Row,action:string,content:string){try{setError('');await api(base+'/'+session!.id+'/memory','POST',{request_id:crypto.randomUUID(),expected_revision:session!.revision,kind:m.kind,scope:m.scope,subject_key:m.subject_key,content,target_id:m.id,action});setEdit(null);await reload(session!.id);}catch(e){setError((e as Error).message);}}
 async function clear(project=false){if(!window.confirm(project?'删除本项目所有讨论、约束和笔记？业务数据不会删除。':'删除当前会话及派生记忆？此操作不能恢复。'))return;try{abort.current?.abort();await api(project?'/api/workspaces/'+wid+'/discussion-memory':base+'/'+session!.id,'DELETE');setPartial('');setEdit(null);await open();}catch(e){setError((e as Error).message);}}
 return <div className="discussion-chat"><p>对话保存在本地，刷新后可恢复。只讨论项目，不自动修改 JD、贡献或简历。默认保留原文，可随时删除。</p>
 {error&&<p role="alert">{error}</p>}{!session&&<p>正在恢复会话…</p>}
 {session&&<><small>当前主题：{session.data.topics?.find((t:Row)=>t.id===session.data.active_topic_id)?.title||'尚未确定'} · 最近最多10轮，受预算限制</small>
 <div className="messages">{session.messages.filter((m:Row)=>m.proposal?.discussion?.status!=='memory_edit').map((m:Row)=><article key={m.id}><strong>{m.role==='user'?'你':'项目助手'}</strong><Markdown>{m.content}</Markdown>{['pending','failed','cancelled','legacy'].includes(m.proposal?.discussion?.status)&&<small>{({pending:'等待回答，可停止后重试',failed:'回答失败；已保存输入',cancelled:'已取消',legacy:'旧入口记录，仅供查看'} as Row)[m.proposal.discussion.status]}</small>}{m.proposal?.discussion?.load_log&&<details><summary>本轮加载记录</summary><pre>{JSON.stringify(m.proposal.discussion.load_log,null,2)}</pre></details>}</article>)}</div>
 {offset>0&&<button onClick={()=>{const n=Math.max(0,offset-50);setOffset(n);reload(session.id,n).catch(e=>setError(e.message));}}>上一页消息</button>}{offset+50<session.message_count&&<button onClick={()=>{const n=offset+50;setOffset(n);reload(session.id,n).catch(e=>setError(e.message));}}>下一页消息</button>}
 {partial&&<div aria-live="polite"><strong>正在回答（未保存）</strong><Markdown>{partial}</Markdown></div>}
 <label>{surface==='wiki'?'向项目提问':'项目讨论'}<textarea aria-label={surface==='wiki'?'向项目提问':'项目讨论'} value={question} maxLength={20000} disabled={busy||disabled} onChange={e=>setQuestion(e.target.value)} placeholder="例如：那失败以后呢？持续要求可用“约束：只考虑本地方案”明确记录。"/></label>
 <button disabled={busy||!!pending||disabled||!question.trim()} onClick={send}>{surface==='wiki'?'发送问题':'发送讨论'}</button>{(busy||pending)&&<button onClick={()=>stop().catch(e=>setError(e.message))}>停止回答</button>}
 <details><summary>已保存约束与讨论笔记</summary><p>记录讨论态度，不代表已采用或已实现。工作区约束可在同项目其他会话使用。</p>{session.memories.filter((m:Row)=>['active','needs_recheck'].includes(m.status)).map((m:Row)=><article key={m.id}><p>{m.content}</p><small>{m.kind} · {m.scope} · {m.status} · v{m.version}</small>{m.conversation_id===session.id&&<>{m.kind!=='code_observation'&&<button onClick={()=>{setEdit(m);setNote(m.content);}}>更正笔记</button>}<button onClick={()=>change(m,'RETRACT',m.content)}>撤回笔记</button>{m.kind==='open_question'&&<button onClick={()=>change(m,'RESOLVE',m.content)}>标为已解决</button>}</>}</article>)}{edit&&<div><textarea aria-label="更正讨论笔记" value={note} onChange={e=>setNote(e.target.value)}/><button disabled={!note.trim()} onClick={()=>change(edit,'SUPERSEDE',note)}>保存更正</button><button onClick={()=>setEdit(null)}>取消更正</button></div>}</details>
 <button onClick={()=>clear()}>删除会话</button><button onClick={()=>clear(true)}>清理项目讨论记忆</button></>}
 </div>;
}
