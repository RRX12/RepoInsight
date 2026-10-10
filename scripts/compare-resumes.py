"""Export a human comparison worksheet; never infer quality from model approval."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.db import Session, Artifact

p=argparse.ArgumentParser()
p.add_argument('--workspace',required=True)
p.add_argument('--baseline',required=True)
p.add_argument('--candidate',required=True)
p.add_argument('--output',required=True)
args=p.parse_args()
with Session() as s:
    artifacts=[s.get(Artifact,i) for i in (args.baseline,args.candidate)]
    if any(a is None or a.workspace_id!=args.workspace or a.type!='resume' for a in artifacts):
        raise SystemExit('两个简历必须属于指定工作区')
    audits=[next((c for c in a.claims if c.get('kind')=='writing_review'),{}) for a in artifacts]
    same=bool(audits[0].get('material_sha256')) and audits[0].get('material_sha256')==audits[1].get('material_sha256')
    lines=['# 简历人工对比记录','',f'材料指纹一致：{same}。不一致时只能做描述比较，不能据此宣称控制变量效果。',
           '先核对原文来源，再由人填写；模型approved不是质量分数。','',
           '| 维度 | 基线问题及依据 | 新版问题及依据 | 人工结论 |',
           '|---|---|---|---|']
    for dimension in ('岗位重点','具体技术机制','跨模块链路','无依据主张','贡献/状态','重复与篇幅','需要修改的条目'):
        lines.append(f'| {dimension} | 待核对 | 待核对 | 待填写 |')
    for label,a,audit in zip(('基线','新版'),artifacts,audits):
        lines.extend(['',f'## {label} v{a.version}',f'Artifact：{a.id}；材料：{audit.get("material_sha256","未知")}',
                      f'状态：{a.review_status}；字数：{len(a.content)}','',a.content,'',
                      '调用与用量（未知不等于零）：','```json',json.dumps(audit.get('harness',{}),ensure_ascii=False,indent=2),'```'])
    Path(args.output).write_text('\n'.join(lines),encoding='utf-8')
print(args.output)
