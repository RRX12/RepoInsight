"""One bounded discussion orchestrator for Wiki, discussion and legacy surfaces."""
import asyncio,json,re,time
from typing import TypedDict
from langgraph.graph import StateGraph,START,END
from fastapi import HTTPException
from .db import Session,Run,Snapshot
from .memory import require
from .discussion_contract import Plan
from .discussion_context import assemble,RULES,tokens,budget
from . import discussion_memory as store,wiki_chat
from .providers import ProviderError

async def plan_turn(wid,cid,ticket):
    view=store.view(wid,cid);content=ticket['user']['content'];focus=view['data'].get('focused_refs',[])
    relation='return' if any(w in content for w in ('回到','上次','之前','原话')) else 'compare' if '比较' in content else 'continue'
    # Simple questions avoid extra LLM calls. Exact user words only, no assumed implementation.
    refs=re.findall(r'[A-Za-z0-9_./-]+\.(?:py|ts|tsx|js)|缓存|恢复|记忆|编排|上下文',content)
    if refs and focus and not set(refs)&set(focus) and relation=='continue':relation='switch'
    refs=re.findall(r'[“「](.{1,50}?)[”」]',content)+refs
    refs=[r for r in dict.fromkeys(refs) if not any(r!=other and r in other for other in refs)][:6]
    chosen=refs or ([] if relation=='switch' else focus)
    query=content if not chosen else '讨论对象：'+', '.join(chosen)+'。问题：'+content+'。请先确认该机制是否存在，不预设已实现。'
    history=relation in ('return','compare')
    plan=Plan(topic_relation=relation,topic_title=chosen[0] if chosen else '',focused_refs=chosen,standalone_query=query[:4000],history_needed=history,history_query=' '.join(refs) or content[:200],source_lookup_needed=any(w in content for w in ('源码','实现','现状','现在','版本','代码')))
    if not chosen and re.search('这个|那.*以后|它',content):plan.clarification='你指的是哪个方案、文件或机制？'
    # Only eventful explicit memory language requests one parse; no rolling summary.
    if not re.search('记住|更正|纠正|继续研究|以后都|整个项目|补充约束',content):return plan
    from .model_support import ProjectModel
    payload={'message_id':ticket['user']['id'],'message':content,'focus':focus,'memories':view['memories'],'default_plan':plan.model_dump()}
    payload['memories']=[m for m in payload['memories'] if m['status']=='active']
    prompt='DISCUSSION_PLAN\n'+RULES+'\n识别值得跨轮保留的显式约束、更正、方案态度或未决问题。user_explicit必须逐字引用用户原话。只讨论，不更新业务状态。target_id仅来自给定记忆；不臆造源码观察；工作区范围必须有用户明确授权。不要因讨论过就记录已实现。\n'+json.dumps(payload,ensure_ascii=False)+'\nJSON schema:'+json.dumps(Plan.model_json_schema(),ensure_ascii=False)
    if tokens(prompt)>budget('CHAT_INPUT_TOKEN_BUDGET',16000):raise HTTPException(422,'记忆解析输入超预算，请缩小问题或清理无关记忆')
    def run():
        model=ProjectModel()
        try:
            result=Plan.model_validate(json.loads(model.request(prompt,stage='DISCUSSION_PLAN',input_budget=min(budget('CHAT_INPUT_TOKEN_BUDGET',16000),budget('CHAT_MODEL_WINDOW',32768)-budget('CHAT_OUTPUT_TOKEN_RESERVE',2000)-1024),output_budget=budget('CHAT_OUTPUT_TOKEN_RESERVE',2000),system_instruction=RULES)))
            ticket['planner_usage']=model.usage
            return result
        finally:model.close()
    result=await asyncio.to_thread(run)
    allowed_text=content+' '+json.dumps(focus,ensure_ascii=False)+' '+json.dumps(view['data'].get('topics',[]),ensure_ascii=False)
    if any(r not in allowed_text for r in result.focused_refs) or (result.topic_title and result.topic_title not in allowed_text):raise HTTPException(422,'讨论焦点不在实际输入中')
    if any(m.origin=='source_observation' for m in result.memory_candidates):raise HTTPException(422,'意图解析不能生成源码事实')
    result.standalone_query=content if not result.focused_refs else '讨论对象：'+', '.join(result.focused_refs)+'。问题：'+content+'。请先确认该机制是否存在，不预设已实现。'
    return result

def source_lookup(wid,ticket,plan):
    if not plan.source_lookup_needed:return {},[]
    from .source_reader import SourceReader,resolved
    from .code_retrieval import CodeRetrieval
    from .db import Snapshot
    from sqlalchemy import select
    with Session() as s:snap=s.scalar(select(Snapshot).where(Snapshot.workspace_id==wid).order_by(Snapshot.created_at.desc()))
    if not snap or not resolved(snap.commit_sha):return {},['当前源码SHA未知，不能确认实现']
    with Session() as s:
        c=store.get(s,wid,ticket['user']['proposal']['discussion']['conversation_id']);cached=c.data.get('source_cache',{})
        if cached.get('repo_identity')==snap.owner+'/'+snap.repo and cached.get('revision')==snap.commit_sha and cached.get('query')==plan.standalone_query and cached.get('evidence'):return cached['evidence'],[]
    reader=SourceReader(wid,snap,max_calls=8);retriever=None;evidence={};gaps=[]
    try:
        retriever=CodeRetrieval(max_queries=1)
        manifest=retriever.prepare(snap.owner+'/'+snap.repo,snap.commit_sha,0)
        for hit in retriever.search(manifest,plan.standalone_query[:1000],3):
            try:
                item=retriever.reread(reader,manifest,hit);evidence[item.id]=item.model_dump()
            except ProviderError as e:gaps.append(e.code)
    except ProviderError as e:gaps.append(e.code+'：源码未补查成功，不代表机制不存在')
    finally:
        reader.close()
        if retriever:retriever.close()
    return evidence,gaps

async def answer_stream(wid,cid,body,ticket):
    status='failed';full='';started=time.monotonic()
    try:
        if ticket.get('replay'):
            for message in ticket['messages']:
                if message['role']=='assistant' and message['proposal']['discussion']['status']=='completed':
                    yield wiki_chat.event(delta=message['content']);yield wiki_chat.event(done=True,reused=True);return
            yield wiki_chat.event(error='该请求已记录但未完成；请刷新状态，用新请求重试');return
        prepared=await discussion_graph.ainvoke({'wid':wid,'cid':cid,'body':body,'ticket':ticket})
        plan=prepared['plan'];evidence=prepared['evidence'];gaps=prepared['gaps']
        upstream=None;base=None
        if not plan.clarification:
            with Session() as s:
                from sqlalchemy import select
                run_id=body.run_id or next((r.id for r in s.scalars(select(Run).where(Run.workspace_id==wid).order_by(Run.created_at.desc())) if r.result.get('wiki')),None)
                if not run_id:raise HTTPException(409,'请先完成项目Wiki分析；约束记录仍保留')
                base,upstream=wiki_chat.prepare(s,wid,wiki_chat.WikiQuestion(run_id=run_id,question=body.content[:4000],page_id=body.page_id))
                if body.page_id:
                    page=require(s,Run,run_id,wid).result['wiki']['generated_pages'][body.page_id]
                    evidence['wiki:'+body.page_id]={'id':'wiki:'+body.page_id,'kind':'wiki','source_revision':'unknown','title':page.get('title'),'excerpt':page.get('content',''),'run_id':run_id}
        if ticket.get('direction_context'):
            direction=ticket['direction_context'];evidence['direction:'+direction['id']]={**direction,'id':'direction:'+direction['id'],'source_revision':'proposal-v'+str(direction['details'].get('version','unknown'))}
        payload,log=assemble(wid,cid,ticket,plan,evidence);log['source_lookup_count']=int(plan.source_lookup_needed and not plan.clarification);log['source_gaps']=gaps;log['planner_usage']=ticket.get('planner_usage');log['planner_call_count']=int('planner_usage' in ticket)
        if plan.clarification:
            full=plan.clarification;yield wiki_chat.event(delta=full)
        else:
            # Avoid forwarding all history as search queries. DeepWiki sees a single explicit query+bounded context.
            upstream['messages']=[{'role':'user','content':json.dumps(payload,ensure_ascii=False)}]
            log['external_index_revision']='unknown';log['source_revision']=ticket['source_revision']
            if tokens(upstream)>min(budget('CHAT_INPUT_TOKEN_BUDGET',16000),budget('CHAT_MODEL_WINDOW',32768)-budget('CHAT_OUTPUT_TOKEN_RESERVE',2000)-1024):raise HTTPException(422,'实际问答请求含协议开销后超预算，请缩小问题')
            log['token_estimate']=tokens(upstream)
            finished=False
            async for raw in guarded_stream(wid,cid,ticket,base,upstream):
                if not store.active(wid,cid,ticket):raise HTTPException(409,'会话已停止、更正或删除')
                event=json.loads(raw)
                if event.get('error'):raise ProviderError(event['error'],'discussion_answer')
                if event.get('delta'):full+=event['delta'];yield raw
                if event.get('done'):finished=True
            if not finished:raise ProviderError('回答提前中断','discussion_answer')
        for m in plan.memory_candidates:
            if m.origin=='assistant_proposal' and m.content not in full:raise HTTPException(422,'派生笔记未出现在最终回答，不写入')
        log['elapsed_seconds']=round(time.monotonic()-started,3)
        if store.finish(wid,cid,ticket,'completed',full,plan,log,{k:v for k,v in evidence.items() if k in log['evidence_ids']}):status='completed';yield wiki_chat.event(done=True)
        else:status='cancelled';yield wiki_chat.event(error='会话已更正、停止或删除，旧回答未保存')
    except asyncio.CancelledError:
        status='cancelled';raise
    except (ProviderError,HTTPException,ValueError) as e:
        yield wiki_chat.event(error=str(e.detail) if isinstance(e,HTTPException) else str(e)[:300])
    finally:
        if not ticket.get('replay') and status!='completed':store.finish(wid,cid,ticket,status)


async def guarded_stream(wid,cid,ticket,base,payload):
    """A stop from another browser closes the pending HTTP stream within a second."""
    iterator=wiki_chat.stream(base,payload).__aiter__();task=None
    try:
        while True:
            task=asyncio.create_task(anext(iterator))
            while not task.done():
                await asyncio.wait({task},timeout=1)
                if not store.active(wid,cid,ticket):raise HTTPException(409,'会话已停止、更正或删除')
            try:yield task.result()
            except StopAsyncIteration:return
    finally:
        if task and not task.done():
            task.cancel()
            try:await task
            except (asyncio.CancelledError,StopAsyncIteration):pass
        await iterator.aclose()


class DiscussionState(TypedDict, total=False):
    wid:str
    cid:str
    body:object
    ticket:dict
    plan:Plan
    evidence:dict
    gaps:list

async def plan_node(state):
    wid,cid,body,ticket=(state[k] for k in ('wid','cid','body','ticket'))
    prohibited=any(w in body.content for w in ('生成简历','修改JD','修改指标','标记已实施'))
    plan=Plan(clarification='此处仅讨论项目与优化取舍；简历生成功能已移除，修改项目业务信息请使用独立按钮/表单。') if prohibited else await plan_turn(wid,cid,ticket)
    store.commit_explicit(wid,cid,ticket,plan)
    if not store.active(wid,cid,ticket):raise HTTPException(409,'会话已停止或更正')
    return {'plan':plan,'ticket':ticket}

async def source_node(state):
    plan=state['plan']
    evidence,gaps=await asyncio.to_thread(source_lookup,state['wid'],state['ticket'],plan) if not plan.clarification else ({},[])
    return {'evidence':evidence,'gaps':gaps}

# One bounded graph, no recursive tool loop or duplicate checkpointer history.
_builder=StateGraph(DiscussionState)
_builder.add_node('plan',plan_node);_builder.add_node('source',source_node)
_builder.add_edge(START,'plan');_builder.add_edge('plan','source');_builder.add_edge('source',END)
discussion_graph=_builder.compile()
