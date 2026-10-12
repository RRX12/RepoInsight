import React,{useEffect,useRef,useState} from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
type Row=Record<string,any>;
type Turn={role:'user'|'assistant',content:string};
function Diagram({source}:{source:string}){
 const [svg,setSvg]=useState('');
 useEffect(()=>{let live=true;import('mermaid').then(async({default:m})=>{m.initialize({startOnLoad:false,securityLevel:'strict'});const result=await m.render('wiki'+crypto.randomUUID().replace(/-/g,''),source);if(live)setSvg(result.svg);}).catch(()=>{});return()=>{live=false;};},[source]);
 return svg?<iframe sandbox="" title="Wiki架构图" srcDoc={svg} style={{width:'100%',height:380,border:0}}/>:<code>{source}</code>;
}
function Material({content}:{content:string}){
 return <div className="wiki-markdown"><Markdown remarkPlugins={[remarkGfm]} components={{img:({alt})=><span>[图片：{alt}]</span>,a:({href,children})=><a href={href} target="_blank" rel="noreferrer">{children}</a>,code:({className,children})=>className==='language-mermaid'?<Diagram source={String(children)}/>:<code className={className}>{children}</code>}}>{content}</Markdown></div>;
}
export default function WikiOverview({wid,run,stale,view}:{wid:string,run:Row,stale:boolean,view:'overview'|'ask'}){
 const pages=Object.entries(run.result?.wiki?.generated_pages||{}) as [string,Row][];
 const [selected,setSelected]=useState(pages[0]?.[0]||'');
 const [history,setHistory]=useState<Turn[]>([]),[question,setQuestion]=useState(''),[answer,setAnswer]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const abort=useRef<AbortController|null>(null);
 const page=pages.find(([id])=>id===selected)?.[1];
 const demo=run.result?.mode==='demo'||run.request?.demo;
 useEffect(()=>()=>abort.current?.abort(),[]);
 async function ask(){
  if(!question.trim()||busy)return;
  setBusy(true);setError('');setAnswer('');const controller=new AbortController();abort.current=controller;let full='',done=false;
  try{
   const r=await fetch('/api/workspaces/'+wid+'/wiki-chat',{method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,body:JSON.stringify({run_id:run.id,page_id:selected||null,question,history:history.slice(-12)})});
   if(!r.ok){const data=await r.json();throw Error(data.error?.message||'问答请求失败');}
   const reader=r.body!.getReader(),decoder=new TextDecoder();let buffer='';
   function consume(line:string){if(!line.trim())return;const event=JSON.parse(line);if(event.error)throw Error(event.error);if(event.delta){full+=event.delta;setAnswer(full);}if(event.done)done=true;}
   while(true){const part=await reader.read();buffer+=decoder.decode(part.value,{stream:!part.done});const lines=buffer.split('\n');buffer=lines.pop()||'';lines.forEach(consume);if(part.done)break;}
   consume(buffer);if(!done)throw Error('连接提前结束，部分回答未加入后续上下文');
   setHistory(old=>[...old,{role:'user',content:question},{role:'assistant',content:full}]);setQuestion('');setAnswer('');
  }catch(e){controller.abort();setError(controller.signal.aborted&&(e as Error).name==='AbortError'?'已停止接收；部分回答不加入上下文，上游请求不保证停止计费':(e as Error).message);}
  finally{setBusy(false);abort.current=null;}
 }
 return <section className="card"><h2>{view==='overview'?'项目全貌':'向项目提问'}</h2><p>DeepWiki 原始分析 · {demo?'演示材料，不是实际仓库分析':'项目能力不等于个人贡献或实测结果'}</p>{stale&&<p className="warning">这是旧分析版本，请核对当前仓库与岗位。</p>}
 {view==='overview'&&run.result?.report?.overview&&<div><h3>项目定位与架构</h3><Material content={run.result.report.overview.summary+'\n\n'+run.result.report.overview.current_architecture}/></div>}
 <div className={view==='overview'?'wiki-layout':'wiki-question-page'}><div hidden={view!=='overview'} className="wiki-reading"><nav aria-label="Wiki章节">{pages.map(([id,p])=><button key={id} aria-current={selected===id?'page':undefined} onClick={()=>setSelected(id)}>{p.title||id}</button>)}</nav>
 <article><h3>{page?.title||'暂无章节'}</h3>{page&&<Material content={page.content||''}/>}</article></div>
 <aside hidden={view!=='ask'} className="wiki-chat"><h3>项目问答</h3><label>辅助章节<select aria-label="辅助章节" value={selected} onChange={e=>setSelected(e.target.value)}><option value="">整个项目（不附加章节）</option>{pages.map(([id,p])=><option key={id} value={id}>{p.title||id}</option>)}</select></label><p>检索整个仓库，当前章节辅助定位。使用已配置的 DeepWiki 模型，发送会调用模型。源码索引不保证与此历史 Wiki 同版本。</p><small>在项目全貌与提问之间切换会保留对话，切换项目、刷新或离开这两个页面后清空；后续问题携带最近6轮。不会自动写入贡献或简历。</small>
 {history.map((t,i)=><div key={i}><strong>{t.role==='user'?'你':'DeepWiki'}</strong><Material content={t.content}/></div>)}
 {answer&&<div><strong>{busy?'正在回答':'未完成回答'}</strong><Material content={answer}/></div>}{error&&<p role="alert">{error}</p>}
 <label>向项目提问<textarea aria-label="向项目提问" value={question} maxLength={4000} disabled={busy||demo} onChange={e=>setQuestion(e.target.value)} placeholder="例如：多个角色如何调度？状态更新失败时如何处理？"/></label>
 <button disabled={busy||demo||!question.trim()||!pages.length} onClick={ask}>发送问题</button>{busy&&<button onClick={()=>abort.current?.abort()}>停止接收</button>}<button disabled={busy} onClick={()=>{setHistory([]);setAnswer('');setError('');}}>清空对话</button>
 {demo&&<p>演示材料不能发送真实仓库问题。</p>}<p>需要用于简历时，请核对后到“优化大方向”明确保存。</p></aside></div></section>;
}
