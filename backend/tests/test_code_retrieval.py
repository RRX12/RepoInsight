import importlib.util
import json
from pathlib import Path
import httpx
import pytest
from backend.app.code_retrieval import CodeRetrieval
from backend.app.providers import ProviderError
from backend.app.source_reader import SourceEvidence,sha256

spec=importlib.util.spec_from_file_location('raw_index',Path(__file__).resolve().parents[2]/'scripts/deepwiki_raw_index.py')
raw=importlib.util.module_from_spec(spec);spec.loader.exec_module(raw)

def test_real_extension_incremental_index_and_query_cache(tmp_path):
    calls=[]
    def embed(text):calls.append(text);return [1.0,float(len(text)%7+1)]
    idx=raw.Index(tmp_path,'model-dim-2',embed)
    a=idx.prepare('a/b','a'*40,{'main.py':'def run():\n return 1','old.py':'old'},2)
    assert len(calls)==2
    same=idx.prepare('a/b','a'*40,{'main.py':'def run():\n return 1','old.py':'old'},0)
    assert same['reused'] and len(calls)==2
    result=idx.search(a['manifest']['index_id'],'a/b','a'*40,'task',2)
    assert result['score_semantics']=='cosine_descending' and result['usage']['query_calls']==1
    assert idx.search(a['manifest']['index_id'],'a/b','a'*40,'task',2)['cached']
    b=idx.prepare('a/b','b'*40,{'main.py':'def run():\n return 1','new.py':'new'},1)
    assert b['usage']['code_calls']==1 and b['usage']['code_cache_hits']==1
    hits=idx.search(b['manifest']['index_id'],'a/b','b'*40,'task',2)['hits']
    assert {h['path'] for h in hits}=={'main.py','new.py'}
    assert len(calls)==4  # original 2, one query, one changed block
    with pytest.raises(ValueError,match='version_mismatch'):idx.search(a['manifest']['index_id'],'a/b','b'*40,'task')
    with pytest.raises(ValueError,match='configuration'):raw.Index(tmp_path,'different',embed).load(a['manifest']['index_id'])
    with pytest.raises(ValueError,match='budget'):idx.prepare('a/b','c'*40,{'other.py':'new content'},0)

def test_http_contract_raw_text_and_target_reread(tmp_path):
    idx=raw.Index(tmp_path,'fp',lambda text:[1.,2.]);prepared=idx.prepare('a/b','a'*40,{'main.py':'return 1'},1)
    requests=[]
    def handler(req):
        body=json.loads(req.content);requests.append(body)
        if req.url.path.endswith('prepare'):return httpx.Response(200,json=prepared)
        return httpx.Response(200,json=idx.search(body['index_id'],body['repo_identity'],body['snapshot_revision'],body['query'],body['top_k']))
    adapter=CodeRetrieval('http://sidecar',httpx.MockTransport(handler),max_queries=1)
    try:
        m=adapter.prepare('a/b','a'*40);hit=adapter.search(m,'task',1)[0]
        class Reader:
            def read_source(self,*args):return SourceEvidence(id='code:1',repo='a/b',commit_sha='a'*40,kind='code',path='main.py',start_line=1,end_line=1,excerpt='return 1',content_hash=sha256('return 1'),revision_status='resolved')
        assert adapter.reread(Reader(),m,hit).excerpt=='return 1'
        hit.text='return 2'
        with pytest.raises(ProviderError,match='SHA'):adapter.reread(Reader(),m,hit)
        with pytest.raises(ProviderError,match='预算'):adapter.search(m,'again')
        assert requests[-1]['top_k']==1 and requests[-1]['expected_embedding_fingerprint']=='fp'
    finally:adapter.close()

def test_transport_failures_and_cancellation():
    def failure(req):raise httpx.ReadTimeout('timeout')
    a=CodeRetrieval('http://sidecar',httpx.MockTransport(failure))
    with pytest.raises(ProviderError) as err:a.prepare('a/b','a'*40)
    assert err.value.code=='index_unavailable';a.close()
    calls=[]
    def cancelled():raise RuntimeError('cancelled')
    a=CodeRetrieval('http://sidecar',httpx.MockTransport(lambda req:calls.append(req)),check_active=cancelled)
    with pytest.raises(RuntimeError):a.prepare('a/b','a'*40)
    assert not calls;a.close()


@pytest.mark.parametrize('field,value',[('indexed_revision','b'*40),('embedding_fingerprint','wrong'),('splitter_version','wrong'),('dimension',9)])
def test_adapter_rejects_mismatched_manifest_fields(tmp_path,field,value):
    idx=raw.Index(tmp_path,'fp',lambda t:[1.,2.]);m=idx.prepare('a/b','a'*40,{'x.py':'x'},1)['manifest']
    result=idx.search(m['index_id'],'a/b','a'*40,'x',1);result[field]=value
    adapter=CodeRetrieval('http://local',httpx.MockTransport(lambda r:httpx.Response(200,json=result)))
    try:
        with pytest.raises(ProviderError) as e:adapter.search(m,'x',1)
        assert e.value.code=='index_version_mismatch'
    finally:adapter.close()

@pytest.mark.parametrize('alter',['path','hash','answer'])
def test_raw_hit_rejects_unsafe_or_answer_shaped_output(tmp_path,alter):
    idx=raw.Index(tmp_path,'fp',lambda t:[1.,2.]);m=idx.prepare('a/b','a'*40,{'x.py':'x'},1)['manifest']
    result=idx.search(m['index_id'],'a/b','a'*40,'x',1)
    if alter=='path':result['hits'][0]['path']='../secret'
    if alter=='hash':result['hits'][0]['text']='invented analysis'
    if alter=='answer':result={'answer':'This project has multi-agent support'}
    adapter=CodeRetrieval('http://local',httpx.MockTransport(lambda r:httpx.Response(200,json=result)))
    try:
        with pytest.raises(ProviderError):adapter.search(m,'x',1)
    finally:adapter.close()

def test_reread_preserves_native_crlf_and_rejects_old_lines(tmp_path):
    import base64
    from backend.app.source_reader import SourceReader
    from backend.app.providers import GitHub
    text='first\r\nreturn 1\r\n'
    idx=raw.Index(tmp_path/'index','fp',lambda t:[1.,2.]);m=idx.prepare('a/b','a'*40,{'x.py':text},1)['manifest']
    from backend.app.code_retrieval import Hit
    hit=Hit.model_validate(idx.search(m['index_id'],'a/b','a'*40,'return',1)['hits'][0])
    gh=GitHub(httpx.MockTransport(lambda r:httpx.Response(200,json={'type':'file','encoding':'base64','size':len(text),'content':base64.b64encode(text.encode()).decode()})))
    reader=SourceReader('w',github=gh,cache_dir=tmp_path/'source');adapter=CodeRetrieval('http://local')
    try:
        assert adapter.reread(reader,m,hit).excerpt==text
        hit.start_line=2
        with pytest.raises(ProviderError):adapter.reread(reader,m,hit)
    finally:reader.close();adapter.close()

def test_query_embedding_is_reused_for_new_revision_but_hit_cache_is_not(tmp_path):
    idx=raw.Index(tmp_path,'fp',lambda t:[1.,2.]);a=idx.prepare('a/b','a'*40,{'x.py':'same'},1)['manifest']
    idx.search(a['index_id'],'a/b','a'*40,'question')
    b=idx.prepare('a/b','b'*40,{'y.py':'same'},0)['manifest']
    result=idx.search(b['index_id'],'a/b','b'*40,'question')
    assert not result['cached'] and result['usage']['query_calls']==0 and result['usage']['query_cache_hits']==1
    assert result['hits'][0]['path']=='y.py' and result['ranking_method']=='rrf60_vector_lexical'


def test_installer_checks_baseline_and_is_idempotent_without_starting(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('install_raw',Path('scripts/install-deepwiki-retrieval.py'))
    installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
    (tmp_path/'api/rag').mkdir(parents=True)
    (tmp_path/'api/main.py').write_text('app = existing_app\n',encoding='utf-8')
    (tmp_path/'api/config.py').write_text('def get_embedder(): pass',encoding='utf-8')
    (tmp_path/'api/rag/pipeline.py').write_text('def get_repo_db(repo): pass',encoding='utf-8')
    monkeypatch.setattr(installer.subprocess,'check_output',lambda *a,**kw:'wrong')
    with pytest.raises(ValueError):installer.install(tmp_path)
    assert not (tmp_path/'api/repocareer_raw_index.py').exists()
    monkeypatch.setattr(installer.subprocess,'check_output',lambda *a,**kw:installer.BASELINE)
    installer.install(tmp_path);installer.install(tmp_path)
    assert (tmp_path/'api/main.py').read_text(encoding='utf-8').count(installer.MARKER)==1
    assert (tmp_path/'api/repocareer_raw_routes.py').read_text(encoding='utf-8')==Path('scripts/deepwiki_raw_routes.py').read_text(encoding='utf-8')
