import React, {useEffect,useState,useRef} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';
import './architecture.css';
import Discussion from './Discussion';
type Row=Record<string,any>;
const states:Row={queued:'等待分析',running:'分析中',completed:'分析完成',failed:'分析未完成',interrupted:'服务重启中断',cancelled:'已停止等待'};
const necessity:Row={recommended:'建议优化',conditional:'满足条件再考虑',not_recommended:'暂不建议引入'};
const decisions:Row={use_existing:'复用现有机制',consider_change:'可考虑改进',not_needed:'当前不需要',insufficient_evidence:'证据不足'};
async function api(path:string,method='GET',body?:unknown){
  const r=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await r.json();if(!r.ok)throw Error(data.error?.message||'请求失败');return data;
}
function App(){
  const [config,setConfig]=useState<Row>({}),[workspaces,setWorkspaces]=useState<Row[]>([]),[w,setW]=useState<Row|null>(null);
  const [role,setRole]=useState(''),[jd,setJD]=useState(''),[demo,setDemo]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const [evidence,setEvidence]=useState<Row|null>(null),[tab,setTab]=useState('overview'),[displayRun,setDisplayRun]=useState(''),[repoURL,setRepoURL]=useState('');
  const activeId=useRef<string|null>(null);
  const snapshot=w?.snapshots?.filter((s:Row)=>s.metadata_json.source_kind==='github_link').at(-1);
  const runs=w?.runs?.filter((r:Row)=>r.request.architecture)||[];
  const currentRun=runs.find((r:Row)=>r.id===displayRun)||runs.at(-1);
  const active=runs.find((r:Row)=>['queued','running'].includes(r.status));
  const result=currentRun?.result,report=result?.report,currentJD=w?.jd_versions?.at(-1);
  const stale=!!report&&(currentRun.request.snapshot_id!==snapshot?.id||currentRun.request.jd_version_id!==currentJD?.id||currentRun.request.role!==w?.role);
  async function refresh(id=activeId.current){if(!id)return;const data=await api('/workspaces/'+id+'?summary=true');if(activeId.current===id)setW(data);}
  async function choose(id:string){activeId.current=id;setDisplayRun('');setEvidence(null);setError('');const data=await api('/workspaces/'+id+'?summary=true');if(activeId.current!==id)return;setW(data);setRepoURL(data.snapshots.filter((s:Row)=>s.metadata_json.source_kind==='github_link').at(-1)?.metadata_json.github_url||'');setRole(data.role==='待填写'?'':data.role);setJD(data.jd_versions.at(-1)?.raw_text||'');localStorage.setItem('repocareer.workspace',id);}
  async function action(fn:()=>Promise<void>){setBusy(true);setError('');setNotice('');try{await fn();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  useEffect(()=>{action(async()=>{setConfig(await api('/config'));const rows=await api('/workspaces');setWorkspaces(rows);const saved=localStorage.getItem('repocareer.workspace');if(rows.find((r:Row)=>r.id===saved))await choose(saved!);});},[]);
  useEffect(()=>{if(!active||!w)return;const id=w.id;const timer=setInterval(()=>refresh(id).catch(e=>setError(e.message)),1500);return()=>clearInterval(timer);},[active?.id,w?.id]);
  async function saveRepository(){
    let workspace=w;
    if(!workspace){workspace=await api('/workspaces','POST',{interest:repoURL,role:'待填写'});activeId.current=workspace!.id;localStorage.setItem('repocareer.workspace',workspace!.id);}
    await api('/workspaces/'+workspace!.id+'/repository-link','POST',{url:repoURL});
    await refresh(workspace!.id);setWorkspaces(await api('/workspaces'));setNotice('GitHub链接已保存。DeepWiki-Open将在分析时直接获取仓库。');setDisplayRun('');
  }
  async function saveTarget(){
    if(!w||!snapshot)throw Error('请先保存GitHub仓库链接');
    if(!role.trim()||!jd.trim())throw Error('请填写岗位名称和JD');
    await api('/workspaces/'+w.id,'PATCH',{interest:w.interest,role,skills:w.skills,time_budget:w.time_budget,environment:w.environment});
    if(jd.trim()!==currentJD?.raw_text)await api('/workspaces/'+w.id+'/jd-versions','POST',{content:jd});
    await refresh();setNotice('岗位与JD已保存；已有报告保留，重新分析会生成新版本。');
  }
  async function start(){await saveTarget();const r=await api('/workspaces/'+w!.id+'/architecture-runs','POST',{snapshot_id:snapshot!.id,idempotency_key:crypto.randomUUID(),demo});setDisplayRun(r.id);await refresh();setTab('overview');}
  function newWorkspace(){activeId.current=null;setW(null);setRepoURL('');setRole('');setJD('');setDisplayRun('');setEvidence(null);setNotice('');setError('');localStorage.removeItem('repocareer.workspace');}
  async function viewPath(path:string){
    const original=w?.snapshots.find((s:Row)=>s.id===currentRun?.request.snapshot_id);
    if(original?.metadata_json.source_kind==='github_link'){
      const href=original.metadata_json.github_url+'/blob/HEAD/'+path.split('/').map(encodeURIComponent).join('/');
      window.open(href,'_blank','noopener,noreferrer');return;
    }
    const e=w?.evidence.find((e:Row)=>e.snapshot_id===currentRun?.request.snapshot_id&&e.path===path);if(!e)throw Error('此引用未关联本地源码');setEvidence(await api('/workspaces/'+w!.id+'/evidence/'+e.id));
  }
  const paths=(items:string[])=>items.length?<div className="source-paths">{items.map(p=><button className="link" key={p} disabled={result?.mode==='demo'} onClick={()=>action(()=>viewPath(p))}>{p}</button>)}</div>:<small>此项未关联具体源码路径。</small>;
  async function exportReport(){
    if(!report)return;
    const text=['# 项目全貌与岗位优化建议',`岗位：${currentRun.request.role}\n来源：${result.mode==='demo'?'演示示例（不是链接仓库分析）':'DeepWiki-Open'}\n快照：${currentRun.request.snapshot_id}`,stale?'> 旧报告待复核，仓库或岗位JD已变化。':'','## 项目全貌',report.overview.summary,report.overview.current_architecture,...report.overview.modules.map((m:Row)=>`### ${m.name}\n${m.responsibility}\n路径：${m.paths.join('、')}`),'## 架构级方向',...report.directions.map((d:Row)=>`### ${d.title}（${necessity[d.necessity]}）\n业务问题：${d.business_problem}\n现有设计：${d.current_design}\n必要性：${d.why_now}\n方案：${d.proposal}\n模块：${d.affected_modules.join('、')}\n已有解法检查：${d.existing_solution_checked}\n替代方案：${d.alternatives}\n取舍：${d.tradeoffs}\n验证：${d.validation_plan}\nJD关联：${d.jd_relation}\n源码路径：${d.source_paths.join('、')}`),'## JD能力评审',...report.jd_assessment.map((a:Row)=>`- ${a.requirement}：${decisions[a.recommendation]}。${a.reason}`),'## 未覆盖与限制',...report.overview.coverage_notes,result.review_coverage.note].join('\n\n');
    const href=URL.createObjectURL(new Blob([text],{type:'text/markdown;charset=utf-8'}));const a=document.createElement('a');a.href=href;a.download='architecture-review.md';a.click();URL.revokeObjectURL(href);
  }
  return <>
    <header><a className="brand" href="#" onClick={e=>e.preventDefault()}><span className="logo">R</span><span>RepoCareer<small>项目全貌 · 岗位实践方向</small></span></a><div className="header-right">{workspaces.length>0&&<select aria-label="选择项目" value={w?.id||''} disabled={busy} onChange={e=>action(()=>choose(e.target.value))}><option value="" disabled>选择已有项目</option>{workspaces.map(p=><option key={p.id} value={p.id}>{p.interest}</option>)}</select>}<button onClick={newWorkspace} disabled={busy}>＋ 新项目</button></div></header>
    <div className="mode-bar"><span className="dot"/>仓库分析引擎：DeepWiki-Open<span>·</span>{config.deepwiki_configured?`${config.deepwiki_provider} / ${config.deepwiki_model}`:'待配置分析服务'}<span className="mode-note">先判断改进必要性，再关联 JD</span></div>
    <main className="architecture-app"><div className="architecture-heading"><span className="eyebrow">REPOSITORY → UNDERSTANDING → OPPORTUNITIES</span><h1>读懂整个项目，再找到值得做的改进。</h1><p>填写 GitHub 仓库链接和目标岗位 JD，先分析架构与业务链路，再给出模块与框架层面的优化方向。</p></div>
      {error&&<div className="alert" role="alert"><strong>操作未完成：</strong>{error}<button onClick={()=>setError('')}>关闭</button></div>}{notice&&<div className="notice" role="status">{notice}</div>}
      <div className="input-grid"><section className="card"><div className="section-title"><span className="step-number">01</span><div><h2>GitHub 代码仓库</h2><small>粘贴公开仓库链接，由DeepWiki-Open读取与分析</small></div></div><label>仓库链接<input aria-label="GitHub仓库链接" value={repoURL} onChange={e=>setRepoURL(e.target.value)} placeholder="https://github.com/owner/repo" disabled={busy||!!active}/></label><button className="primary" disabled={busy||!!active||!repoURL.trim()} onClick={()=>action(saveRepository)}>保存仓库链接</button>{snapshot&&<div className="uploaded-info"><strong>{snapshot.owner}/{snapshot.repo}</strong><a href={snapshot.metadata_json.github_url} target="_blank" rel="noreferrer">在GitHub查看仓库 ↗</a><small>DeepWiki-Open直接获取仓库并生成Wiki；可能复用服务缓存。当前不固定Git提交，源码引用与版本需核对。</small></div>}<p>先保存仓库链接，再填写岗位与JD。无需打包或本地源码。</p></section>
        <section className="card"><div className="section-title"><span className="step-number">02</span><div><h2>目标岗位与 JD</h2><small>JD用于方向相关性，不强制堆技术</small></div></div><label>岗位名称<input aria-label="岗位名称" value={role} onChange={e=>setRole(e.target.value)} placeholder="例如：Agent 开发工程师" disabled={busy||!!active}/></label><label>岗位 JD<textarea className="jd-text" aria-label="岗位JD" value={jd} onChange={e=>setJD(e.target.value)} placeholder="粘贴岗位职责与要求，例如 multi-agent、MCP、Skill 等。建议仍需有项目问题和必要性依据。" disabled={busy||!!active}/></label><div className="row"><button className="primary" disabled={busy||!!active||!snapshot||!role.trim()||!jd.trim()} onClick={()=>action(start)}>{active?'正在分析项目全貌…':'分析项目全貌与优化方向 →'}</button>{currentJD&&<button disabled={busy||!!active} onClick={()=>action(saveTarget)}>仅更新岗位与JD</button>}</div><details className="service-help"><summary>分析服务与演示说明</summary><p>{config.deepwiki_configured?'已配置服务地址；实际可用性与模型由分析调用验证。':'尚未配置DeepWiki-Open。可先保存仓库链接与岗位JD；启动真实分析会明确提示待配置，不会回退到函数级模板。'}</p><p>服务端设置 DEEPWIKI_BASE_URL、DEEPWIKI_PROVIDER、DEEPWIKI_MODEL；GitHub链接分析无需共享本地源码目录。密钥仅配置在DeepWiki-Open服务中。</p><label className="check"><input type="checkbox" checked={demo} onChange={e=>setDemo(e.target.checked)} disabled={!!active}/>仅预览演示报告（不会分析链接仓库或实际JD）</label></details></section></div>
      {currentRun&&<section className="card run-panel"><div className="row"><h2>分析进度</h2><span className="badge">{states[currentRun.status]}</span>{active&&<button onClick={()=>action(async()=>{await api('/runs/'+active.id+'/cancel?workspace_id='+w!.id,'POST');await refresh();})}>停止等待</button>}{['failed','cancelled','interrupted'].includes(currentRun.status)&&<button disabled={busy} onClick={()=>action(async()=>{await api('/runs/'+currentRun.id+'/retry?workspace_id='+w!.id,'POST');await refresh();})}>安全重试</button>}</div><p>GitHub仓库 → DeepWiki-Open 全面 Wiki → 结合 JD 评审架构必要性</p>{currentRun.steps.at(-1)&&<div className="progress-line">{currentRun.steps.at(-1).summary}</div>}{currentRun.error&&<div role="alert" className="warning">{currentRun.error}</div>}{result?.wiki&&!report&&<p>Wiki已保存；评审失败时重试会复用，不需要重新上传。</p>}<details><summary>查看运行步骤（{currentRun.steps.length}）</summary>{currentRun.steps.map((s:Row,i:number)=><small key={i}>{s.tool} · {s.summary}</small>)}</details></section>}
      {report&&<section className="report"><div className="report-header"><div><span className="eyebrow">PROJECT REVIEW</span><h2>项目全貌与架构级优化方向</h2><small>{currentRun.request.role} · JD版本 {w?.jd_versions.find((j:Row)=>j.id===currentRun.request.jd_version_id)?.version} · {result.mode==='demo'?'演示示例':'DeepWiki-Open真实服务输出'}</small></div><button onClick={()=>action(exportReport)}>下载 Markdown</button></div>{result.mode==='demo'&&<div className="warning">此报告只展示演示文档服务的示例，不是对你上传的仓库或岗位JD的分析。</div>}{stale&&<div className="warning">仓库或岗位JD已变化，此旧报告待复核。重新分析生成新报告，旧版本保留。</div>}<div className="report-tabs">{[['overview','项目全貌'],['directions','优化大方向'],['jd','JD适配与取舍'],['wiki','DeepWiki分析材料']].map(([key,label])=><button className={tab===key?'active':''} key={key} onClick={()=>setTab(key)}>{label}</button>)}</div>
        {tab==='overview'&&<><section className="card"><h2>项目定位与现有架构</h2><p className="pre">{report.overview.summary}</p><div className="architecture-description">{report.overview.current_architecture}</div></section><section className="card"><h2>模块与职责</h2><div className="module-grid">{report.overview.modules.map((m:Row,i:number)=><article key={i}><h3>{m.name}</h3><p>{m.responsibility}</p>{paths(m.paths)}</article>)}</div></section><section className="card"><h2>核心业务链路</h2>{report.overview.core_flows.map((f:Row,i:number)=><article className="flow" key={i}><h3>{f.name}</h3><p className="pre">{f.description}</p>{paths(f.paths)}</article>)}</section><section className="card"><h2>项目已有能力</h2><p>以下属于原项目，不能归为你的新增贡献。</p>{report.overview.existing_capabilities.map((m:Row,i:number)=><article key={i}><h3>{m.name}</h3><p>{m.responsibility}</p>{paths(m.paths)}</article>)}<h3>覆盖限制</h3>{report.overview.coverage_notes.map((n:string,i:number)=><p key={i}>○ {n}</p>)}<p>{result.review_coverage.note}</p>{['failed_pages','omitted_pages','unmatched_paths','truncated_pages'].map(k=>result.review_coverage[k]?.length>0&&<p key={k}>{({failed_pages:'生成失败页面',omitted_pages:'评审未纳入页面',unmatched_paths:'未匹配源码路径',truncated_pages:'评审输入截断页面'} as Row)[k]}：{result.review_coverage[k].join('、')}</p>)}</section></>}
        {tab==='directions'&&<><div className="notice">先说明业务问题、已有解法与必要性，再说明JD关联。建议不代表已实施。</div>{!report.directions.length&&<section className="card"><h2>当前建议维持架构</h2><p>{report.no_change_reason}</p></section>}{report.directions.map((d:Row,i:number)=><section className="card direction" key={i}><div className="row"><span className="badge">{necessity[d.necessity]}</span><small>架构 / 能力方向 · {d.direction}</small></div><h2>{d.title}</h2><p className="direction-proposal">{d.proposal}</p><dl>{[['business_problem','实际问题'],['current_design','当前设计'],['existing_solution_checked','已有解法检查'],['why_now','为何值得改'],['alternatives','替代方案'],['tradeoffs','复杂度与代价'],['validation_plan','验证必要性和收益'],['jd_relation','岗位JD关联']].map(([key,label])=><React.Fragment key={key}><dt>{label}</dt><dd className="pre">{d[key]}</dd></React.Fragment>)}</dl><p><strong>影响模块：</strong>{d.affected_modules.join('、')}</p>{paths(d.source_paths)}{d.assumptions.length>0&&<div className="warning">待确认假设：{d.assumptions.join('；')}</div>}</section>)}</>}
        {tab==='jd'&&<section className="card"><h2>岗位要求与项目实际适配</h2><p>项目没有某个技术名词，并不自动意味着需要引入它。</p>{report.jd_assessment.map((a:Row,i:number)=><article className="jd-assessment" key={i}><div className="row"><h3>{a.requirement}</h3><span className="badge">{decisions[a.recommendation]}</span></div><p>现状：{a.current_fit}</p><p>{a.reason}</p></article>)}</section>}
        {tab==='wiki'&&<section className="card"><h2>DeepWiki-Open 原始分析页面</h2><p>外部分析材料；路径可核对，不等于运行验证或个人贡献。</p>{Object.entries(result.wiki?.generated_pages||{}).map(([id,page])=>{const p=page as Row;return <details key={id}><summary>{p.title}</summary>{paths(p.filePaths||[])}<pre>{p.content}</pre></details>;})}</section>}
      </section>}
      {w?.messages&&<Discussion key={w.id} w={w} refresh={()=>refresh()}/>}
      {runs.length>1&&<details className="card"><summary>历史分析报告（{runs.length}）</summary>{runs.slice().reverse().map((r:Row)=><button key={r.id} className="history-run" onClick={()=>{setDisplayRun(r.id);setTab('overview');}}>{new Date(r.created_at).toLocaleString()} · {states[r.status]} · {r.request.demo?'演示':'DeepWiki-Open'}</button>)}</details>}
      {!report&&!currentRun&&<div className="result-empty"><span>03</span><h2>分析结果会显示在这里</h2><p>项目全貌、核心模块与链路、架构级方向，以及“不需要引入”的技术取舍。</p></div>}
    </main>{evidence&&<div className="overlay" onClick={()=>setEvidence(null)}><section className="modal" role="dialog" aria-label="源码引用" onClick={e=>e.stopPropagation()}><div className="row"><h2>{evidence.path}</h2><button onClick={()=>setEvidence(null)}>关闭源码</button></div><small>快照 {evidence.snapshot_id} · SHA256 {evidence.content_hash}</small><pre>{evidence.excerpt}</pre></section></div>}<footer>RepoCareer · 架构建议来自项目需要，JD决定相关性。</footer>
  </>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);


