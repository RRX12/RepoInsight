import React from 'react';
type Row=Record<string,any>;
export default function ProcessPanel({w}:{w:Row}){
 return <section className="card process-panel"><h2>执行记录与中间材料</h2><p>本地过程查看页；模型判断和运行记录不等于已验证事实。</p>
 {(w.runs||[]).slice().reverse().map((r:Row)=><details key={r.id}><summary>{r.request?.resume_generation?'简历生成':'项目分析'} · {r.status} · {new Date(r.created_at).toLocaleString()}</summary>{r.error&&<p role="alert">{r.error}</p>}<h3>阶段记录</h3><pre>{JSON.stringify(r.steps,null,2)}</pre><details><summary>输入与结果</summary><pre>{JSON.stringify({request:r.request,result:r.result},null,2)}</pre></details></details>)}
 <details><summary>事实与证据索引</summary><pre>{JSON.stringify({findings:w.findings,evidence:w.evidence},null,2)}</pre></details>
 <details><summary>状态变更记录</summary><pre>{JSON.stringify(w.events||[],null,2)}</pre></details>
 </section>;
}
