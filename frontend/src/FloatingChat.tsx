import React,{useEffect,useRef,useState} from 'react';
import DiscussionChat from './DiscussionChat';

type Props={wid:string,surface:'wiki'|'discussion',runId?:string,pageId?:string,improvementId?:string,disabled?:boolean,contextLabel:string};
export default function FloatingChat({contextLabel,...props}:Props){
 const [collapsed,setCollapsed]=useState(false);
 const [box,setBox]=useState({x:Math.max(8,window.innerWidth-460),y:100,width:440,height:560});
 const gesture=useRef<{kind:'move'|'resize',x:number,y:number,box:typeof box}|null>(null);
 function fit(b:typeof box){const width=Math.min(window.innerWidth-16,Math.max(300,b.width)),height=Math.min(window.innerHeight-16,Math.max(300,b.height));return {width,height,x:Math.min(Math.max(8,b.x),Math.max(8,window.innerWidth-width-8)),y:Math.min(Math.max(8,b.y),Math.max(8,window.innerHeight-(collapsed?54:height)-8))};}
 useEffect(()=>{const resize=()=>setBox(b=>fit(b));window.addEventListener('resize',resize);resize();return()=>window.removeEventListener('resize',resize);},[collapsed]);
 function begin(e:React.PointerEvent,kind:'move'|'resize'){if(e.button!==0)return;gesture.current={kind,x:e.clientX,y:e.clientY,box};e.currentTarget.setPointerCapture(e.pointerId);e.preventDefault();}
 function move(e:React.PointerEvent){const g=gesture.current;if(!g)return;const dx=e.clientX-g.x,dy=e.clientY-g.y;setBox(fit(g.kind==='move'?{...g.box,x:g.box.x+dx,y:g.box.y+dy}:{...g.box,width:g.box.width+dx,height:g.box.height+dy}));}
 return <aside className={'floating-chat'+(collapsed?' is-collapsed':'')} aria-label="项目聊天窗口" style={{left:box.x,top:box.y,width:box.width,height:collapsed?54:box.height}}>
  <div className="floating-chat-toolbar"><button className="chat-drag" aria-label="移动聊天框" title="拖动移动；方向键微调" onPointerDown={e=>begin(e,'move')} onPointerMove={move} onPointerUp={()=>gesture.current=null} onPointerCancel={()=>gesture.current=null} onKeyDown={e=>{const delta:Record<string,[number,number]>={ArrowLeft:[-20,0],ArrowRight:[20,0],ArrowUp:[0,-20],ArrowDown:[0,20]};if(delta[e.key]){e.preventDefault();const [x,y]=delta[e.key];setBox(b=>fit({...b,x:b.x+x,y:b.y+y}));}}}>⠿ {props.surface==='wiki'?'项目问答':'优化讨论'}</button>
   <button aria-label="缩小聊天框" disabled={collapsed} onClick={()=>setBox(b=>fit({...b,width:b.width-60,height:b.height-60}))}>−</button><button aria-label="放大聊天框" disabled={collapsed} onClick={()=>setBox(b=>fit({...b,width:b.width+60,height:b.height+60}))}>＋</button><button aria-label={collapsed?'展开聊天框':'收起聊天框'} onClick={()=>setCollapsed(v=>!v)}>{collapsed?'展开':'收起'}</button></div>
  <div className="floating-chat-body" hidden={collapsed}><p className="chat-context">当前讨论：{contextLabel}</p><DiscussionChat {...props}/></div>
  {!collapsed&&<button className="chat-resize" aria-label="调整聊天框大小" title="拖动调整大小" onPointerDown={e=>begin(e,'resize')} onPointerMove={move} onPointerUp={()=>gesture.current=null} onPointerCancel={()=>gesture.current=null}>◢</button>}
 </aside>;
}
