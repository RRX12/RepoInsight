"""Offline A/B/C context replay. Never invokes a model or touches production data."""
import argparse,asyncio,json,os,sys,tempfile,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='docs/memory/offline-results.json')
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='repocareer-memory-eval-') as temp:
        os.environ['REPOCAREER_DATA']=temp;os.environ['REPOCAREER_DEMO']='true'
        from backend.app.db import migrate,Session,Workspace,Snapshot,engine
        from backend.app import discussion_memory as mem,discussion_service as svc
        from backend.app.discussion_contract import Question,Plan,MemoryChange,MemoryCandidate
        from backend.app.discussion_context import assemble
        from fastapi import HTTPException
        migrate();results=[]
        cases=json.loads((ROOT/'fixtures/discussion-memory/scenarios.json').read_text(encoding='utf-8'))['cases']
        for case in cases:
            with Session.begin() as s:w=Workspace(interest='isolated replay');s.add(w);s.flush();wid=w.id
            cid=mem.open_conversation(wid,'wiki')['id'];operation=case['operation']
            def start(content,rid=None):return mem.begin(wid,cid,Question(request_id=rid or uuid.uuid4().hex,expected_revision=mem.view(wid,cid)['revision'],content=content))
            def complete(content,answer,topic):
                t=start(content);mem.finish(wid,cid,t,'completed',answer,Plan(topic_title=topic,focused_refs=[topic]));return t
            def change(**kwargs):
                return mem.change_memory(wid,cid,MemoryChange(request_id=uuid.uuid4().hex,expected_revision=mem.view(wid,cid)['revision'],subject_key='deployment',content=case['constraint'],**kwargs))
            for turn in case['turns']:complete(turn['question'],turn['answer'],turn['topic'])
            change()
            if operation=='refresh':assert mem.open_conversation(wid,'wiki')['id']==cid
            if operation=='long_turn':complete('长代码','x'*10000,case['topic'])
            if operation=='switch':complete('讨论“其他方案”','仅讨论其他方案','其他方案')
            if operation=='repeat':
                change();change();assert len(mem.view(wid,cid)['memories'])==1
            if operation=='correct':
                m=mem.view(wid,cid)['memories'][0]
                mem.change_memory(wid,cid,MemoryChange(request_id='correct',expected_revision=mem.view(wid,cid)['revision'],subject_key=m['subject_key'],target_id=m['id'],action='SUPERSEDE',content=case['corrected_constraint']))
            if operation=='scopes':change(scope='workspace');assert len(mem.view(wid,cid)['memories'])==2
            if operation=='proposal':complete('讨论笔记：计划新增'+case['topic'],'尚未实现',case['topic'])
            if operation=='revision':
                with Session.begin() as s:s.add(Snapshot(workspace_id=wid,owner='fixture',repo='project',commit_sha='a'*40,metadata_json={}))
                t=start('查看代码');e={'fixture:source':dict(id='fixture:source',kind='code',commit_sha='a'*40,path='app.py',start_line=1,end_line=1,excerpt='state = {}')}
                mem.finish(wid,cid,t,'completed','仅局部观察',Plan(topic_title=case['topic'],focused_refs=[case['topic']]),{},e)
                with Session.begin() as s:s.add(Snapshot(workspace_id=wid,owner='fixture',repo='project',commit_sha='b'*40,metadata_json={}))
            if operation=='isolation':
                with Session.begin() as s:other=Workspace(interest='other');s.add(other);s.flush();oid=other.id
                assert mem.view(oid,mem.open_conversation(oid,'wiki')['id'])['memories']==[]
            if operation=='invalid_source':
                t=start('非法引用')
                try:mem.finish(wid,cid,t,'completed','不保存',Plan(memory_candidates=[MemoryCandidate(kind='proposal_note',subject_key='x',content='不保存',origin='assistant_proposal',source_message_ids=['foreign'])]))
                except HTTPException:pass
                else:raise AssertionError('Invalid source accepted')
                mem.finish(wid,cid,t,'failed')
            if operation=='failed':
                t=start('中断问题');mem.finish(wid,cid,t,'cancelled')
            ticket=start(case['current_question'],rid='current')
            if operation=='idempotency':assert start(case['current_question'],rid='current')['replay']
            if operation=='concurrent':change(kind='proposal_note')
            if operation=='delete':mem.delete_conversation(wid,cid)
            # Pure planner rules only. No model event words in these fixtures.
            if operation not in ('delete','business'):
                plan=asyncio.run(svc.plan_turn(wid,cid,ticket))
            elif operation=='business':plan=Plan(clarification='使用独立入口')
            else:plan=Plan()
            for variant in ('A','B','C'):
                started=time.perf_counter();row={'id':case['id'],'variant':variant}
                try:
                    payload,log=assemble(wid,cid,ticket,plan,variant=variant)
                    state_text=' '.join(m['content'] for m in payload['memory']);recent_text=json.dumps(payload['recent'],ensure_ascii=False);history_text=json.dumps(payload['history'],ensure_ascii=False)
                    expected_constraint=case['corrected_constraint'] if operation=='correct' else case['constraint']
                    row.update(status='assembled',object_in_context=case['expected_object'] in str(payload),constraint_in_state=expected_constraint in state_text,constraint_in_context=expected_constraint in str(payload),correction_in_state=(expected_constraint in state_text) if operation=='correct' else None,required_history_loaded=(case['required_history'] in history_text or case['required_history'] in recent_text) if case['required_history'] else None,stale_observation_loaded=any(m['kind']=='code_observation' for m in payload['memory']) if operation=='revision' else None,token_estimate=log['token_estimate'],input_limit=log['input_limit'],memory_ids=log['memory_ids'],history_message_ids=log['history_message_ids'],recent_message_ids=log['recent_message_ids'],evidence_ids=log['evidence_ids'],omitted=log['omitted_reason'],clarification=plan.clarification,history_notice=payload.get('history_notice'))
                    assert not case['expected_rejection']
                except HTTPException as exc:
                    row.update(status='rejected',code=exc.status_code,reason=exc.detail)
                    assert case['expected_rejection'],row
                row['context_latency_ms']=round((time.perf_counter()-started)*1000,3);results.append(row)
        summary={}
        for variant in ('A','B','C'):
            rows=[r for r in results if r['variant']==variant and r['status']=='assembled']
            summary[variant]={k:{'numerator':sum(r.get(k) is True for r in rows),'denominator':sum(r.get(k) is not None for r in rows),'failed_cases':[r['id'] for r in rows if r.get(k) is False]} for k in ('object_in_context','constraint_in_context','constraint_in_state','correction_in_state','required_history_loaded')}
            summary[variant]['max_input_estimate']=max(r['token_estimate'] for r in rows)
        report={'kind':'offline_context_replay_not_answer_quality','cases':len(cases),'same_input_budget':16000,'model':'not_called','source_fixture':'fixed a/b revisions; no remote retrieval','summary':summary,'rows':results,'unmeasured':['真实对象识别准确率','回答约束遵守','方案状态保真','回答依据','真实token usage和模型延迟'],'limitations':'脚本只测实际加载上下文；A/B/C不生成回答。安全操作断言与M01-M20生产接口回归互补。合成材料不是用户原话，也不是模型结果。'}
        target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'cases':len(cases),'contexts':len(results),'summary':summary,'output':str(target)},ensure_ascii=False))
        engine.dispose()
    return 0
if __name__=='__main__':sys.exit(main())
