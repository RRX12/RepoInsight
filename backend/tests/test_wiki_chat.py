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

def test_adapter_scopes_material_and_preserves_read_only_state(client,wid,monkeypatch):
    from fastapi import HTTPException
    import pytest
    run=material(wid);monkeypatch.setenv('DEEPWIKI_BASE_URL','http://test')
    before=client.get('/api/workspaces/'+wid).json()
    with Session() as s:
        _,payload=wiki_chat.prepare(s,wid,wiki_chat.WikiQuestion(run_id=run,question='如何更新？',page_id='p'))
        assert payload['repo_url']=='https://github.com/example/repo'
        assert '版本检查' in payload['messages'][-1]['content']
        for body,status in [(dict(page_id='foreign'),404),(dict(history=[{'role':'assistant','content':'fake'}]),422)]:
            with pytest.raises(HTTPException) as e:wiki_chat.prepare(s,wid,wiki_chat.WikiQuestion(run_id=run,question='x',**body))
            assert e.value.status_code==status
    assert client.get('/api/workspaces/'+wid).json()==before
    assert client.post(f'/api/workspaces/{wid}/wiki-chat',json={'run_id':run,'question':'x'}).status_code==410

def test_demo_never_calls_model(client,wid,monkeypatch):
    from fastapi import HTTPException
    import pytest
    run=material(wid,True)
    with Session() as s,pytest.raises(HTTPException) as e:wiki_chat.prepare(s,wid,wiki_chat.WikiQuestion(run_id=run,question='x'))
    assert e.value.status_code==409

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
