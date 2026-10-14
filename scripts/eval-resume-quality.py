"""Evaluate the single production writer; offline fixtures never prove content quality."""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fixture',default='fixtures/resume-quality/memory.json')
    p.add_argument('--real',action='store_true');p.add_argument('--authorize-paid',action='store_true')
    p.add_argument('--workspace');p.add_argument('--input');p.add_argument('--before')
    p.add_argument('--paid-call-limit',type=int,default=8,choices=range(1,25))
    p.add_argument('--output',default='data/resume-quality-eval.json')
    args=p.parse_args();scratch=Path(tempfile.mkdtemp(prefix='repocareer-eval-'))
    if not args.real:os.environ['REPOCAREER_DATA']=str(scratch)
    if args.real and not args.authorize_paid:p.error('--real requires explicit --authorize-paid and user authorization')
    from backend.app.resume_writer import write,collect
    from backend.app.resume_harness import digest
    from backend.app.source_reader import SourceEvidence,sha256
    from backend.app.providers import ProviderError
    from backend.app import shared_analysis
    shared_analysis.cache_directory=lambda:scratch/'analysis'
    snapshot=None;reader=None;provider=None;calls=[]
    if args.real:
        if args.input:material=json.loads(Path(args.input).read_text(encoding='utf-8'))
        elif args.workspace:
            from backend.app.db import Session,asdict
            with Session() as s:
                snap,material,_=collect(s,args.workspace);snapshot=SimpleNamespace(**asdict(snap))
        else:p.error('--real needs --input frozen-material.json or --workspace')
        from backend.app.resume_support import WritingModel
        provider=WritingModel()
        def model(prompt):
            if len(calls)>=args.paid_call_limit:raise ProviderError('评测付费调用预算耗尽','resume_budget')
            calls.append(prompt.split('\n',1)[0]);return provider.request(prompt,stage=calls[-1],json_output=True)
        model.usage=provider.usage;model.model=provider.model
    else:
        fixture=json.loads(Path(args.fixture).read_text(encoding='utf-8'));material=fixture['material'];files=fixture['source_files']
        from backend.app.code_retrieval import Hit
        import importlib.util
        spec=importlib.util.spec_from_file_location('raw',Path(__file__).with_name('deepwiki_raw_index.py'));raw=importlib.util.module_from_spec(spec);spec.loader.exec_module(raw)
        index=raw.Index(scratch/'index','offline-d2',lambda text:[1.,float(len(text)%11+1)])
        prepared=index.prepare(material['repo'],material['commit'],files,len(files))['manifest']
        class Reader:
            def close(self):pass
            def list_tree(self,*a):return {'paths':list(files),'truncated':False}
            def read_source(self,repo,sha,path,line_range=None):
                lines=files[path].splitlines(keepends=True);start,end=line_range or (1,len(lines));text=''.join(lines[start-1:end])
                return SourceEvidence(id='fixture:'+path,kind='code',repo=repo,commit_sha=sha,path=path,start_line=start,end_line=end,excerpt=text,content_hash=sha256(text),revision_status='resolved')
            def search_ranges(self,repo,sha,path,terms):return [self.read_source(repo,sha,path)]
        class Retrieval:
            trace=[]
            def prepare(self,*a,**kw):return {k:v for k,v in prepared.items() if k!='chunks'}
            def search(self,m,q,top_k=8):return [Hit.model_validate(h) for h in index.search(m['index_id'],m['repo_identity'],m['indexed_revision'],q,top_k)['hits']]
            def reread(self,r,m,h):return r.read_source(m['repo_identity'],m['indexed_revision'],h.path,(h.start_line,h.end_line))
        reader=Reader();material['_code_retriever']=Retrieval()
        def model(prompt):
            stage=prompt.split('\n',1)[0];calls.append(stage)
            return json.dumps(fixture['responses'][stage],ensure_ascii=False)
    fingerprint=digest({k:v for k,v in material.items() if not k.startswith('_')})
    before=json.loads(Path(args.before).read_text(encoding='utf-8')) if args.before else None
    if before and before.get('material_fingerprint')!=fingerprint:p.error('Baseline input fingerprint differs; no like-for-like claim allowed')
    record={'evaluation_kind':'real_unscored' if args.real else 'offline_contract_not_quality','material_fingerprint':fingerprint,'before':before,'after':None,'human_review':{k:None for k in ('mechanism_discovery','fact_support','topic_selection','attribution','duplication','readability')},'limitations':'模型评分不等于人工验收；旧结果只读，不运行旧流水线。'}
    try:
        text,audit=write(snapshot,material,model,reader);record['after']={'text':text,'audit':audit}
    except Exception as e:
        record['error']={'code':getattr(e,'code',type(e).__name__),'message':str(e),'stages':getattr(e,'stage_trace',[]),'calls':getattr(e,'stage_calls',[])}
    finally:
        if provider:record['usage']=provider.usage;provider.close()
    record['calls']=calls;record['budgets']={'llm_calls':args.paid_call_limit if args.real else None,'retrieval_queries':16,'new_code_vectors':int(os.getenv('CODE_INDEX_NEW_VECTOR_BUDGET','0')),'note':'付费请求上限仅约束LLM；query embedding与显式代码embedding分别统计'};target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'output':str(target),'kind':record['evaluation_kind'],'calls':len(calls),'success':bool(record['after'])}))
    if record.get('error'):raise SystemExit(1)
if __name__=='__main__':main()
