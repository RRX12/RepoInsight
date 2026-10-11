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

class CheckpointModel:
    """Replay explicitly frozen upstream stages; only downstream calls are paid.

    This is a one-theme diagnosis through write(), not a full discovery quality test.
    """
    def __init__(self,audit,material,theme,limit,source_paths=(),questions=(),resume=None):
        from backend.app.resume_support import WritingModel
        self.provider=WritingModel();self.model=self.provider.model;self.usage=self.provider.usage
        self.audit=audit;self.limit=limit;self.paid=0;self.replayed=[]
        self.previous_paid=(resume or {}).get('checkpoint',{}).get('total_paid_calls',(resume or {}).get('checkpoint',{}).get('paid_calls',0))
        self.limit=min(limit,8-self.previous_paid)
        self.resume_outputs={r['stage']:r['output_structure']['output'] for r in (resume or {}).get('error',{}).get('stages',[]) if r['stage'] in ('CANDIDATE_ENRICH','CANDIDATE_ENRICH_LINK_REPAIR','CLAIM_VERIFY') and r['status']=='completed'}
        card=next(c for c in audit['candidates'] if c['candidate_id']==theme)
        self.discovery={'candidates':[dict(card)],'claims':[c for c in audit['generated_claims'] if c['id'] in card['claim_ids']]}
        hints=[]
        for c in self.discovery['claims']:
            for ref in c['evidence_ids']:
                if ref.startswith('wiki:'):
                    try:hints.extend(material['_full_wiki_pages'][int(ref.split(':')[1])]['filePaths'])
                    except (IndexError,KeyError,ValueError):pass
        self.discovery['candidates'][0]['source_paths']=list(dict.fromkeys([*source_paths,*hints]))[:4]
        self.discovery['candidates'][0]['investigation_questions']=list(questions)[:3] or [card['mechanism']+'：哪些调用连接存在，哪些只是Wiki描述？']
    def request(self,prompt,*,stage,json_output=True):
        if stage=='ANALYZE':
            value={'facts':[{k:v for k,v in f.items() if k!='quote'} for f in self.audit['project_map']['facts'] if '"'+f['source_ref']+'"' in prompt],'uncertainties':[]}
        elif stage=='PRODUCT':value=self.audit['selection']['project_value']
        elif stage=='JD_PLAN':value=self.audit['requirements']
        elif stage=='DISCOVER':value=self.discovery
        elif stage in self.resume_outputs:value=self.resume_outputs[stage]
        else:
            if self.paid>=self.limit:
                from backend.app.providers import ProviderError
                raise ProviderError('单主题评测付费调用预算耗尽','resume_budget')
            self.paid+=1
            return self.provider.request(prompt,stage=stage,json_output=json_output)
        self.replayed.append(stage);return json.dumps(value,ensure_ascii=False)
    def close(self):self.provider.close()

class FixtureModel:
    def __init__(self,responses):self.responses=responses
    def __call__(self,prompt):
        stage=prompt.split('\n',1)[0]
        if stage not in self.responses:raise ValueError('Missing fixture stage '+stage)
        response=self.responses[stage]
        return response if isinstance(response,str) else json.dumps(response,ensure_ascii=False)

def main():
    p=argparse.ArgumentParser();p.add_argument('--fixture',default='fixtures/resume-quality/memory.json');p.add_argument('--real',action='store_true');p.add_argument('--workspace');p.add_argument('--freeze-revision',action='store_true');p.add_argument('--output-mode',choices=['project_reference','personal_resume'],default='project_reference');p.add_argument('--output',default='data/resume-quality-eval.json');p.add_argument('--compare-legacy',action='store_true')
    p.add_argument('--checkpoint-input');p.add_argument('--checkpoint-before');p.add_argument('--theme');p.add_argument('--paid-call-limit',type=int,choices=range(1,9),default=8);p.add_argument('--source-path',action='append',default=[]);p.add_argument('--source-question',action='append',default=[]);p.add_argument('--resume-checkpoint');args=p.parse_args()
    # Optional immutable checkpoint mode shares the same production writer and contracts.
    if args.checkpoint_input:
        if not args.real or not args.checkpoint_before or not args.theme:p.error('checkpoint requires --real, --checkpoint-before and --theme; actual API authorization is required')
        if args.compare_legacy:p.error('single-theme checkpoint may not run a second paid legacy pipeline')
        material=json.loads(Path(args.checkpoint_input).read_text(encoding='utf-8'))
        baseline=json.loads(Path(args.checkpoint_before).read_text(encoding='utf-8'))['after']
        if args.output_mode!=baseline['audit']['generation_context']['output_mode']:p.error('checkpoint output mode differs from baseline')
        if digest({k:v for k,v in material.items() if not k.startswith('_')})!=baseline['audit']['generation_context']['material_fingerprint']:p.error('checkpoint input differs from the recorded baseline')
        resume=json.loads(Path(args.resume_checkpoint).read_text(encoding='utf-8')) if args.resume_checkpoint else None
        if resume and (resume['material_fingerprint']!=baseline['audit']['generation_context']['material_fingerprint'] or resume['theme']!=args.theme or resume.get('manual_investigation_hints',{}).get('paths')!=args.source_path or resume.get('manual_investigation_hints',{}).get('questions')!=args.source_question):p.error('resume checkpoint input/theme/investigation hints changed')
        snapshot=None;model=CheckpointModel(baseline['audit'],material,args.theme,args.paid_call_limit,args.source_path,args.source_question,resume);before_model=None;label='real_downstream_single_theme_checkpoint_unscored'
    elif args.real:
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
    if args.checkpoint_input:
        record['before']=baseline
        record['theme']=args.theme
        record['manual_investigation_hints']={'paths':args.source_path,'questions':args.source_question,'note':'人工定位后提供的检索问题，不是已核验事实；原材料/JD/提交指纹不变。'}
        record['limitations']='同指纹输入，复用原映射/全貌/JD/单主题候选检查点，真实运行后续生产write流程；不证明新版全量发现质量，不与完整简历直接评分。'
    try:
        if args.compare_legacy:
            text,audit=write_legacy(snapshot,material,before_model);record['before']={'text':text,'audit':audit}
        text,audit=write(snapshot,material,model);record['after']={'text':text,'audit':audit}
    except Exception as exc:
        record['error']={'type':type(exc).__name__,'code':getattr(exc,'code',None),'message':str(exc)[:1000],'trace_id':getattr(exc,'trace_id',None),'stages':getattr(exc,'stage_trace',[]),'calls':getattr(exc,'stage_calls',[])}
    finally:
        if isinstance(model,CheckpointModel):
            record['checkpoint']={'replayed_stages':model.replayed,'paid_calls':model.paid,'total_paid_calls':model.previous_paid+model.paid,'previous_checkpoint':args.resume_checkpoint,'usage':model.usage}
            model.close()
    target.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    if record['after']:
        after=record['after']['audit'];before=record['before']
        report=['# 同输入新旧流程对比',f'类型：{label}；输入指纹：{fingerprint}','## 旧版正文',before['text'] if before else '本次未运行旧版，不能声称同输入质量比较。','## 新版正文',text,'## 候选与证据差异',f'旧版选题：{json.dumps(before["audit"]["selection"]["selected"],ensure_ascii=False) if before else "未运行"}',f'新版候选：{json.dumps(after["candidates"],ensure_ascii=False)}',f'新版Claim：{json.dumps(after["generated_claims"],ensure_ascii=False)}','## 改进与退化观察','结构变化：新流程记录候选池、独立支持状态、段落claim映射，成果可以省略。文案质量尚未人工评分；更多请求和源码读取会增加时延，词面召回及同源评审仍可能漏查。','## 人工复核','事实支持、岗位关键机制、归属、重复、可读性均待填写。']
        target.with_suffix('.md').write_text('\n\n'.join(report),encoding='utf-8')
        print(json.dumps({'output':str(target),'kind':label,'status':after['status'],'model':after['generation_context']['model'],'calls':len(after['harness']['calls']),'sources':len(after['source_evidence']),'candidates':len(after['candidates'])},ensure_ascii=False))
    else:print(json.dumps({'output':str(target),'error':{k:v for k,v in (record.get('error') or {}).items() if k in ('type','code','message')},'checkpoint':{'paid_calls':record.get('checkpoint',{}).get('total_paid_calls')}},ensure_ascii=False))
    if record.get('error'):raise SystemExit(1)
if __name__=='__main__':main()
