import React from 'react';

function inline(text:string){
 return text.split(/(\*\*[^*]+\*\*)/g).map((part,i)=>part.startsWith('**')&&part.endsWith('**')?<strong key={i}>{part.slice(2,-2)}</strong>:part);
}
export default function ResumePreview({content}:{content:string}){
 const [body,notes]=content.split('\n## 使用说明');
 const blocks:React.ReactNode[]=[];let bullets:string[]=[];
 function flush(){if(bullets.length){blocks.push(<ul key={'list'+blocks.length}>{bullets.map((line,i)=><li key={i}>{inline(line)}</li>)}</ul>);bullets=[];}}
 for(const line of body.split('\n')){
  if(line.startsWith('- ')){bullets.push(line.slice(2));continue;}
  flush();if(!line.trim())continue;
  blocks.push(line.startsWith('# ')?<h3 key={blocks.length}>{inline(line.slice(2))}</h3>:line.startsWith('## ')?<h4 key={blocks.length}>{inline(line.slice(3))}</h4>:<p key={blocks.length}>{inline(line)}</p>);
 }
 flush();
 return <article data-testid="resume-preview">{blocks}{notes&&<details><summary>来源与使用说明</summary><p className="pre">{notes.trim()}</p></details>}</article>;
}
