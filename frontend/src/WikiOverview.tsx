import React,{useEffect,useState} from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
type Row=Record<string,any>;
import FloatingChat from './FloatingChat';
function Diagram({source}:{source:string}){
 const [svg,setSvg]=useState('');
 useEffect(()=>{let live=true;import('mermaid').then(async({default:m})=>{m.initialize({startOnLoad:false,securityLevel:'strict'});const result=await m.render('wiki'+crypto.randomUUID().replace(/-/g,''),source);if(live)setSvg(result.svg);}).catch(()=>{});return()=>{live=false;};},[source]);
 return svg?<iframe sandbox="" title="Wiki架构图" srcDoc={svg} style={{width:'100%',height:380,border:0}}/>:<code>{source}</code>;
}
function Material({content}:{content:string}){
 return <div className="wiki-markdown"><Markdown remarkPlugins={[remarkGfm]} components={{img:({alt})=><span>[图片：{alt}]</span>,a:({href,children})=><a href={href} target="_blank" rel="noreferrer">{children}</a>,code:({className,children})=>className==='language-mermaid'?<Diagram source={String(children)}/>:<code className={className}>{children}</code>}}>{content}</Markdown></div>;
}
export default function WikiOverview({wid,run,stale}:{wid:string,run:Row,stale:boolean}){
 const pages=Object.entries(run.result?.wiki?.generated_pages||{}) as [string,Row][];
 const overview=run.result?.report?.overview;
 const sections:[string,string,string][]=[...(overview?[['overview','项目定位与架构',overview.summary+'\n\n'+overview.current_architecture] as [string,string,string]]:[]),...pages.map(([id,p])=>[id,p.title||id,p.content||''] as [string,string,string])];
 const [selected,setSelected]=useState(sections[0]?.[0]||'');
 const section=sections.find(([id])=>id===selected)||sections[0];
 const retrieval=pages.find(([id])=>id===section?.[0])?.[1]?.retrieval;
 const demo=run.result?.mode==='demo'||run.request?.demo;
 return <section className="card wiki-overview"><h2>项目全貌</h2><p>DeepWiki 原始分析 · {demo?'演示材料，不是实际仓库分析':'文档描述、源码实现和实测结果分别核对'}</p>{stale&&<p className="warning">这是旧分析版本，请核对当前仓库。</p>}
 <div className="wiki-reading"><nav aria-label="Wiki章节">{sections.map(([id,title])=><button key={id} aria-current={section?.[0]===id?'page':undefined} onClick={()=>setSelected(id)}>{title}</button>)}</nav>
 <article><h3>{section?.[1]||'暂无章节'}</h3>{retrieval&&<aside aria-label="章节证据范围" className={retrieval.status==='limited'?'warning':''}><p>{retrieval.status==='limited'?'本章存在未确认范围':'本章已完成证据覆盖审查'} · {retrieval.cached?'复用已验证章节':'固定快照材料'}。引用已核对，内容关系与实际运行效果仍需验证。</p>{retrieval.status==='limited'&&<p>停止原因：{retrieval.stop_reason}；请结合正文中的未确认范围阅读。</p>}</aside>}{section&&<Material content={section[2]}/>}</article></div>
 <FloatingChat wid={wid} surface="wiki" runId={run.id} pageId={pages.some(([id])=>id===section?.[0])?section?.[0]:undefined} contextLabel={section?.[1]||'整个项目'} disabled={!!demo||!pages.length}/>
 </section>;
}
