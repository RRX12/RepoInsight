import React,{useState,useEffect} from 'react';
type Row=Record<string,any>;
export default function OptimizationDirections({w,refresh}:{w:Row,refresh:()=>Promise<void>}){
 const [title,setTitle]=useState(''),[content,setContent]=useState(''),[editing,setEditing]=useState<string|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [version,setVersion]=useState('');
 const base='/api/workspaces/'+w.id+'/interaction';
 useEffect(()=>{let live=true;fetch(base,{cache:'no-store'}).then(async r=>{if(!r.ok)throw Error('读取版本失败');return r.json();}).then(v=>{if(live)setVersion(v.version);}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[w]);
 const editableIds=new Set((w.events||[]).filter((e:Row)=>e.operation==='create_improvement').map((e:Row)=>e.entity_id));
 const rows=(w.improvements||[]).filter((i:Row)=>!i.details.deleted);
 async function mutate(op:string,data:Row={},target_id?:string){
  setBusy(true);setError('');
  try{if(!version)throw Error('正在读取版本，请稍后重试');
   const response=await fetch(base+'/mutations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_version:version,mutation_id:crypto.randomUUID(),operations:[{op,data,target_id}]})});
   const result=await response.json();if(!response.ok)throw Error(result.error?.message||'保存失败');setVersion(result.state.version);await refresh();return true;
  }catch(e){setError((e as Error).message);return false;}finally{setBusy(false);}
 }
 return <section className="card"><h2>优化大方向</h2><p>系统建议仅供思考。请在下方填写并保存自己的优化方向；每次保存的完整内容作为一个可多选条目，选中后用于简历补充，选择不代表已经实现。</p>
 {error&&<p role="alert">{error}</p>}
 {rows.map((i:Row)=><article key={i.id} className="direction" data-testid="direction-option"><label className="check">{editableIds.has(i.id)&&<input type="checkbox" aria-label={'选择方向：'+i.details.title} checked={i.status==='selected'} disabled={busy||i.status==='stale'} onChange={e=>mutate('update_improvement_decision',{decision:e.target.checked?'selected':'deferred'},i.id)}/> }<strong>{i.details.title||i.details.direction||'优化方向'}</strong></label><small>{editableIds.has(i.id)?'用户保存的完整方向':'系统提供的思路（仅供参考）'}</small><p className="pre">{i.details.proposal||i.details.description}</p><small>{i.status==='stale'?'旧项目建议，请重新评估':i.details.implementation==='user_reported_done'?'用户报告已完成，未独立验证':'设计方向，未确认完成'}</small><div className="row">{editableIds.has(i.id)&&<><button disabled={busy} onClick={()=>{setEditing(i.id);setTitle(i.details.title||'');setContent(i.details.proposal||'');}}>编辑方向</button><button disabled={busy} onClick={()=>mutate('delete_improvement',{},i.id)}>删除方向</button></>}{editableIds.has(i.id)&&i.status==='selected'&&i.details.implementation!=='user_reported_done'&&<button disabled={busy} onClick={()=>mutate('report_improvement_completed',{},i.id)}>报告此方向已完成</button>}</div></article>)}
 <h3>{editing?'修改优化方向':'添加自己的优化方向'}</h3><label>方向名称<input aria-label="优化方向名称" maxLength={300} value={title} onChange={e=>setTitle(e.target.value)}/></label><label>优化内容<textarea aria-label="优化方向内容" value={content} onChange={e=>setContent(e.target.value)} placeholder="请说明要解决的问题、具体方案、实施情况、取舍和效果依据。尚未实现请明确标注。"/></label>
 <p className={!content.trim()?'warning':''}>这里的内容将作为后续简历生成的依据，请尽可能具体。未填写时不会补充你的个人优化；已有项目仍可生成参考稿。</p>
 <button disabled={busy} onClick={async()=>{if(!title.trim()||!content.trim()){setError('请填写方向名称和详细优化内容，保存后再选择用于简历。');return;}if(await mutate(editing?'edit_improvement':'create_improvement',{title:title.trim(),proposal:content.trim()},editing||undefined)){setEditing(null);setTitle('');setContent('');}}}>保存优化方向</button>{editing&&<button onClick={()=>{setEditing(null);setTitle('');setContent('');}}>取消编辑</button>}
 </section>;
}
