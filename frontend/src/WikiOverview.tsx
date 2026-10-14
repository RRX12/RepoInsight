import React,{useEffect,useState} from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
type Row=Record<string,any>;
import DiscussionChat from './DiscussionChat';
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
 const page=pages.find(([id])=>id===selected)?.[1];
 const demo=run.result?.mode==='demo'||run.request?.demo;
 return <section className="card"><h2>{view==='overview'?'项目全貌':'向项目提问'}</h2><p>DeepWiki 原始分析 · {demo?'演示材料，不是实际仓库分析':'项目能力不等于个人贡献或实测结果'}</p>{stale&&<p className="warning">这是旧分析版本，请核对当前仓库与岗位。</p>}
 {view==='overview'&&run.result?.report?.overview&&<div><h3>项目定位与架构</h3><Material content={run.result.report.overview.summary+'\n\n'+run.result.report.overview.current_architecture}/></div>}
 <div className={view==='overview'?'wiki-layout':'wiki-question-page'}><div hidden={view!=='overview'} className="wiki-reading"><nav aria-label="Wiki章节">{pages.map(([id,p])=><button key={id} aria-current={selected===id?'page':undefined} onClick={()=>setSelected(id)}>{p.title||id}</button>)}</nav>
 <article><h3>{page?.title||'暂无章节'}</h3>{page&&<Material content={page.content||''}/>}</article></div>
 <aside hidden={view!=='ask'} className="wiki-chat"><h3>项目问答</h3><label>辅助章节<select aria-label="辅助章节" value={selected} onChange={e=>setSelected(e.target.value)}><option value="">整个项目（不附加章节）</option>{pages.map(([id,p])=><option key={id} value={id}>{p.title||id}</option>)}</select></label><p>检索整个仓库，当前章节辅助定位。使用已配置的 DeepWiki 模型，发送会调用模型。源码索引不保证与此历史 Wiki 同版本。</p><DiscussionChat key={wid} wid={wid} surface="wiki" runId={run.id} pageId={selected} disabled={!!demo||!pages.length}/>
 {demo&&<p>演示材料不能发送真实仓库问题。</p>}<p>需要用于简历时，请核对后到“优化大方向”明确保存。</p></aside></div></section>;
}
