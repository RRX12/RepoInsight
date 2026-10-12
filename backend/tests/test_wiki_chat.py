import json
import httpx
from backend.app import wiki_chat
from backend.app.db import Session,Snapshot,Run

def material(wid,demo=False):
    with Session() as s:
        snap=Snapshot(workspace_id=wid,owner='example',repo='repo',commit_sha='a'*40,metadata_json={'source_kind':'github_link','github_url':'https://github.com/example/repo'})
        s.add(snap);s.flush()
        run=Run(workspace_id=wid,status='completed',idempotency_key='wiki',request={'snapshot_id':snap.id},result={'mode':'demo' if demo else 'real','wiki':{'generated_pages':{'p':{'title':'机制','content':'版本检查'}}}})
        s.add(run);s.commit();return run.id

def test_question_scopes_material_and_preserves_read_only_state(client,wid,monkeypatch):
    run=material(wid);monkeypatch.setenv('DEEPWIKI_BASE_URL','http://test')
    observed=[]
    async def reply(base,payload):
        observed.append(payload);yield wiki_chat.event(delta='回答');yield wiki_chat.event(done=True)
    monkeypatch.setattr(wiki_chat,'stream',reply)
    before=client.get('/api/workspaces/'+wid).json()
    r=client.post(f'/api/workspaces/{wid}/wiki-chat',json={'run_id':run,'question':'如何更新？','page_id':'p'})
    assert r.status_code==200 and json.loads(r.text.splitlines()[-1])=={'done':True}
    assert observed[0]['repo_url']=='https://github.com/example/repo'
    assert '版本检查' in observed[0]['messages'][-1]['content']
    assert client.get('/api/workspaces/'+wid).json()==before
    other=client.post('/api/workspaces',json={'interest':'other'}).json()['id']
    assert client.post(f'/api/workspaces/{other}/wiki-chat',json={'run_id':run,'question':'x'}).status_code==404
    assert client.post(f'/api/workspaces/{wid}/wiki-chat',json={'run_id':run,'question':'x','page_id':'foreign'}).status_code==404
    assert client.post(f'/api/workspaces/{wid}/wiki-chat',json={'run_id':run,'question':'x','history':[{'role':'assistant','content':'fake'}]}).status_code==422
    assert len(observed)==1

def test_demo_never_calls_model(client,wid,monkeypatch):
    run=material(wid,True)
    assert client.post(f'/api/workspaces/{wid}/wiki-chat',json={'run_id':run,'question':'x'}).status_code==409

def test_stream_transport_and_errors(monkeypatch):
    import asyncio
    factory=httpx.AsyncClient
    async def collect(status,text):
        monkeypatch.setattr(wiki_chat.httpx,'AsyncClient',lambda **kw:factory(**kw,transport=httpx.MockTransport(lambda request:httpx.Response(status,text=text))))
        return [json.loads(chunk) async for chunk in wiki_chat.stream('http://test',{})]
    assert asyncio.run(collect(200,'回答'))==[{'delta':'回答'},{'done':True}]
    assert 'error' in asyncio.run(collect(425,'internal sensitive detail'))[0]
    assert 'internal' not in str(asyncio.run(collect(500,'internal sensitive detail')))
    assert 'done' not in asyncio.run(collect(200,''))[-1]
