import React,{useEffect,useState} from 'react';

export default function RunTiming({run}:{run:Record<string,any>}){
 const [clock,setClock]=useState(Date.now()),[expanded,setExpanded]=useState(false);
 const live=['queued','running'].includes(run.status);
 useEffect(()=>{setClock(Date.now());if(!live)return;const timer=setInterval(()=>setClock(Date.now()),1000);return()=>clearInterval(timer);},[run.id,run.status]);
 const start=Date.parse(run.result?.analysis_started_at||run.result?.queued_at||run.created_at||'');
 const seconds=typeof run.result?.elapsed_seconds==='number'?run.result.elapsed_seconds:live&&Number.isFinite(start)?(clock-start)/1000:null;
 const label=seconds===null?'用时未知':`用时 ${Math.max(0,Math.floor(seconds))}秒`;
 return <div className="run-timing"><button className="run-timing-button" aria-label="分析用时与阶段" aria-expanded={expanded} onClick={()=>setExpanded(!expanded)}>{label}<span aria-hidden="true">{expanded?'⌄':'›'}</span></button>{expanded&&<div className="run-timing-details" role="region" aria-label="分析阶段记录">{run.steps?.length?run.steps.map((step:Record<string,any>,i:number)=><p key={i}>{step.summary}</p>):<p>暂无阶段记录</p>}</div>}</div>;
}
