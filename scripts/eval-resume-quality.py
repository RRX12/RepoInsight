"""Run the actual resume writer. Offline fixtures test contracts, never semantic quality."""
import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app.resume_writer import collect,write,write_legacy
from backend.app.resume_harness import digest
from backend.app.source_reader import SourceReader
from backend.app.db import Session,asdict

class FixtureModel:
    def __init__(self,responses):self.responses=responses
    def __call__(self,prompt):
        stage=prompt.split('\n',1)[0]
        if stage not in self.responses:raise ValueError('Missing fixture stage '+stage)
        response=self.responses[stage]
        return response if isinstance(response,str) else json.dumps(response,ensure_ascii=False)

def main():
    p=argparse.ArgumentParser();p.add_argument('--fixture',default='fixtures/resume-quality/memory.json');p.add_argument('--real',action='store_true');p.add_argument('--workspace');p.add_argument('--freeze-revision',action='store_true');p.add_argument('--output-mode',choices=['project_reference','personal_resume'],default='project_reference');p.add_argument('--output',default='data/resume-quality-eval.json');p.add_argument('--compare-legacy',action='store_true');args=p.parse_args()
    if args.real:
        if not args.workspace:p.error('--real requires --workspace')
        with Session() as s:
            snap,material,fingerprint=collect(s,args.workspace);snapshot=SimpleNamespace(**asdict(snap))
        if args.freeze_revision:
            material['_wiki_snapshot_id']=material['snapshot_id']
            reader=SourceReader(args.workspace)
            try:revision=reader.resolve_revision(material['repo'])
            finally:reader.close()
            material['commit']=revision['commit_sha'];snapshot.commit_sha=revision['commit_sha']
            # Evaluation-only snapshot; does not retroactively fix a historical database record.
            material['snapshot_id']='eval:'+material['snapshot_id']+':'+revision['commit_sha']
        model=None;before_model=None;label='real_model_unscored'
    else:
        fixture=json.loads(Path(args.fixture).read_text(encoding='utf-8'));material=fixture['material'];snapshot=None
        model=FixtureModel(fixture['responses']);before_model=FixtureModel(fixture['legacy_responses']);label='offline_contract_example_not_quality_evidence'
    material['_output_mode']=args.output_mode
    fingerprint=digest({k:v for k,v in material.items() if not k.startswith('_')})
    target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True)
    record={'evaluation_kind':label,'material_fingerprint':fingerprint,'output_mode':args.output_mode,'before':None,'after':None,'human_review':{'fact_support':None,'job_mechanisms':None,'attribution':None,'duplication':None,'readability':None},'limitations':'Stub验证控制流与契约，不证明语义质量；真实输出仍需人工核对源码，不从小样本推导产品效果。'}
    try:
        if args.compare_legacy:
            text,audit=write_legacy(snapshot,material,before_model);record['before']={'text':text,'audit':audit}
        text,audit=write(snapshot,material,model);record['after']={'text':text,'audit':audit}
    except Exception as exc:
        record['error']={'type':type(exc).__name__,'code':getattr(exc,'code',None),'message':str(exc)[:1000],'trace_id':getattr(exc,'trace_id',None),'stages':getattr(exc,'stage_trace',[]),'calls':getattr(exc,'stage_calls',[])}
    target.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    if record['after']:
        after=record['after']['audit'];before=record['before']
        report=['# 同输入新旧流程对比',f'类型：{label}；输入指纹：{fingerprint}','## 旧版正文',before['text'] if before else '本次未运行旧版，不能声称同输入质量比较。','## 新版正文',text,'## 候选与证据差异',f'旧版选题：{json.dumps(before["audit"]["selection"]["selected"],ensure_ascii=False) if before else "未运行"}',f'新版候选：{json.dumps(after["candidates"],ensure_ascii=False)}',f'新版Claim：{json.dumps(after["generated_claims"],ensure_ascii=False)}','## 改进与退化观察','结构变化：新流程记录候选池、独立支持状态、段落claim映射，成果可以省略。文案质量尚未人工评分；更多请求和源码读取会增加时延，词面召回及同源评审仍可能漏查。','## 人工复核','事实支持、岗位关键机制、归属、重复、可读性均待填写。']
        target.with_suffix('.md').write_text('\n\n'.join(report),encoding='utf-8')
        print(json.dumps({'output':str(target),'kind':label,'status':after['status'],'model':after['generation_context']['model'],'calls':len(after['harness']['calls']),'sources':len(after['source_evidence']),'candidates':len(after['candidates'])},ensure_ascii=False))
    else:print(json.dumps({'output':str(target),'error':record.get('error')},ensure_ascii=False))
    if record.get('error'):raise SystemExit(1)
if __name__=='__main__':main()
