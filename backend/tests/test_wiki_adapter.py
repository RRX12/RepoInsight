import json
from types import SimpleNamespace
import httpx,pytest
from backend.app.deepwiki import DeepWikiOpen
from backend.app.providers import ProviderError
from scripts.wiki_rag_contract import settings_from_env,Budgets

def snapshot():return SimpleNamespace(id='s',workspace_id='w',commit_sha='a'*40,metadata_json={'source_kind':'github_link','github_url':'https://github.com/o/r'})
def adapter(monkeypatch,handler):
    monkeypatch.setenv('DEEPWIKI_BASE_URL','http://offline.test');monkeypatch.setenv('DEEPWIKI_PROVIDER','deepseek')
    p=DeepWikiOpen(transport=httpx.MockTransport(handler));p.wiki_config={'mode':'enhanced','budgets':Budgets().model_dump()};return p

def test_enhanced_payload_and_only_versioned_cache_endpoint(monkeypatch):
    seen=[];snap=snapshot()
    def handler(request):
        seen.append(request)
        if request.method=='POST':
            data=json.loads(request.content)
            assert data['revision']==snap.commit_sha and data['workspace_id']=='w' and data['snapshot_id']=='s'
            return httpx.Response(200,json={'task_id':'enhanced_'+'f'*64,'from_cache':True})
        assert request.url.path=='/repocareer/wiki/cache'
        return httpx.Response(200,json={'provenance':{'mode':'enhanced','revision':snap.commit_sha,'workspace_id':'w','snapshot_id':'s','task_id':'enhanced_'+'f'*64},'generated_pages':{'p':{'content':'valid'}}})
    p=adapter(monkeypatch,handler)
    try:assert p.wiki(snap,lambda *a:None,lambda *a:None,lambda:False)['generated_pages']
    finally:p.close()
    assert len(seen)==2 and all('/api/wiki_cache'!=r.url.path for r in seen)

@pytest.mark.parametrize('provenance',[{}, {'mode':'legacy','revision':'a'*40},{'mode':'enhanced','revision':'b'*40,'workspace_id':'w','snapshot_id':'s'},{'mode':'enhanced','revision':'a'*40,'workspace_id':'other','snapshot_id':'s'}])
def test_unknown_wrong_version_and_workspace_cache_rejected(monkeypatch,provenance):
    p=adapter(monkeypatch,lambda req:httpx.Response(200,json={'provenance':provenance,'generated_pages':{}}))
    try:
        with pytest.raises(ProviderError):p.cache(p.repo_payload(snapshot()),'enhanced_'+'f'*64)
    finally:p.close()

def test_cancel_or_input_change_does_not_accept_late_cache(monkeypatch):
    requests=[];snap=snapshot();changed=[False]
    def handler(req):
        requests.append(req.url.path)
        if req.url.path=='/wiki/tasks':changed[0]=True;return httpx.Response(200,json={'task_id':'t'})
        assert req.url.path=='/repocareer/wiki/tasks/t/cancel'
        return httpx.Response(200,json={'cancelled':True})
    p=adapter(monkeypatch,handler)
    def check():
        if changed[0]:raise ProviderError('changed','source_revision')
    p.check_inputs=check
    try:
        with pytest.raises(ProviderError,match='changed'):p.wiki(snap,lambda *a:None,lambda *a:None,lambda:False)
    finally:p.close()
    assert requests==['/wiki/tasks','/repocareer/wiki/tasks/t/cancel']

def test_cancelled_existing_task_performs_no_cache_read(monkeypatch):
    p=adapter(monkeypatch,lambda req:(_ for _ in ()).throw(AssertionError('must not read cache')))
    try:
        with pytest.raises(ProviderError):p.wiki(snapshot(),lambda *a:None,lambda *a:None,lambda:True,'t')
    finally:p.close()

def test_settings_frozen_in_run_and_invalid_mode_rejected(client,wid,monkeypatch):
    monkeypatch.setattr('backend.app.main.submit',lambda rid:None)
    snap=client.post(f'/api/workspaces/{wid}/repository-link',json={'url':'https://github.com/o/r'}).json()
    monkeypatch.setenv('WIKI_RETRIEVAL_MODE','enhanced');monkeypatch.setenv('WIKI_RAG_TOOLS','7')
    r=client.post(f'/api/workspaces/{wid}/architecture-runs',json={'snapshot_id':snap['id'],'idempotency_key':'frozen','demo':False})
    assert r.status_code==200,r.text
    assert r.json()['request']['wiki_retrieval']['budgets']['tools']==7
    assert 'provider' in r.json()['request']['wiki_retrieval'] and 'model' in r.json()['request']['wiki_retrieval']
    monkeypatch.setenv('WIKI_RAG_TOOLS','8')
    assert client.post(f'/api/workspaces/{wid}/architecture-runs',json={'snapshot_id':snap['id'],'idempotency_key':'frozen','demo':False}).status_code==409
    monkeypatch.setenv('WIKI_RETRIEVAL_MODE','invalid')
    assert client.post(f'/api/workspaces/{wid}/architecture-runs',json={'snapshot_id':snap['id'],'idempotency_key':'bad','demo':False}).status_code==422

def test_default_mode_and_explicit_budget(monkeypatch):
    monkeypatch.delenv('WIKI_RETRIEVAL_MODE',raising=False);monkeypatch.delenv('WIKI_RAG_MAX_NEW_VECTORS',raising=False);monkeypatch.setenv('CODE_INDEX_NEW_VECTOR_BUDGET','0')
    assert settings_from_env()['mode']=='legacy' and settings_from_env()['budgets']['max_new_vectors']==0

def test_old_legacy_retry_cannot_bypass_new_enhanced_mode(client,wid,monkeypatch):
    from backend.app.db import Run,Session
    monkeypatch.setattr('backend.app.main.submit',lambda rid:(_ for _ in ()).throw(AssertionError('must not submit old mode')))
    with Session.begin() as s:
        r=Run(workspace_id=wid,status='failed',request={'architecture':True},idempotency_key='old-mode',result={'wiki':{'legacy':True}});s.add(r);s.flush();rid=r.id
    monkeypatch.setenv('WIKI_RETRIEVAL_MODE','enhanced')
    response=client.post(f'/api/runs/{rid}/retry?workspace_id={wid}')
    assert response.status_code==409 and '发起新分析' in response.text
    with Session() as s:assert s.get(Run,rid).status=='failed' and s.get(Run,rid).result['wiki']['legacy']
    assert client.get('/api/config').json()['wiki_retrieval_mode']=='enhanced'

def test_dry_run_failure_exposes_counts_without_fallback(monkeypatch):
    seen=[]
    def handler(req):
        seen.append(req.url.path)
        if req.method=='POST':return httpx.Response(200,json={'task_id':'t'})
        return httpx.Response(200,json={'status':'failed','error':'index_embedding_budget:'+json.dumps({'candidate_chunks':9,'cached_vectors':1,'required_new_vectors':8})})
    p=adapter(monkeypatch,handler)
    try:
        with pytest.raises(ProviderError,match='所需新向量 8'):p.wiki(snapshot(),lambda *a:None,lambda *a:None,lambda:False)
    finally:p.close()
    assert seen==['/wiki/tasks','/wiki/tasks/t']

def test_auto_mode_polls_index_progress_without_second_implicit_search(monkeypatch):
    polls=[0];steps=[];task='enhanced_'+'f'*64
    def handle(req):
        if req.method=='POST':return httpx.Response(200,json={'task_id':task})
        if req.url.path=='/wiki/tasks/'+task:
            polls[0]+=1;return httpx.Response(200,json={'status':'indexing' if polls[0]==1 else 'completed'})
        if req.url.path=='/repocareer/wiki/progress':return httpx.Response(200,json={'cached_vectors':2,'required_new_vectors':3,'new_completed':1,'remaining_new_vectors':2,'phase':'building'})
        assert req.url.path=='/repocareer/wiki/cache'
        return httpx.Response(200,json={'generated_pages':{'p':{}},'provenance':{'task_id':task,'mode':'enhanced','workspace_id':'w','snapshot_id':'s','revision':'a'*40}})
    p=adapter(monkeypatch,handle);p.wiki_config['budgets']['index_mode']='auto';monkeypatch.setattr('backend.app.deepwiki.time.sleep',lambda *a:None)
    try:p.wiki(snapshot(),lambda *args:steps.append(args),lambda *a:None,lambda:False)
    finally:p.close()
    assert any(tool=='deepwiki_index' and '1/3' in summary and '剩余 2' in summary for tool,summary in steps)

def test_old_reuse_only_retry_cannot_keep_zero_limit_after_auto_switch(client,wid,monkeypatch):
    from backend.app.db import Run,Session
    monkeypatch.setenv('WIKI_RETRIEVAL_MODE','enhanced');monkeypatch.setenv('WIKI_RAG_INDEX_MODE','auto')
    with Session.begin() as s:
        r=Run(workspace_id=wid,status='failed',request={'architecture':True,'wiki_retrieval':{'mode':'enhanced','budgets':{'max_new_vectors':0}}},idempotency_key='old-index-mode',result={});s.add(r);s.flush();rid=r.id
    response=client.post(f'/api/runs/{rid}/retry?workspace_id={wid}')
    assert response.status_code==409 and '索引准备策略' in response.text
