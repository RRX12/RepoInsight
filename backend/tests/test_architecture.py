import io,json,zipfile,stat
from pathlib import Path
import httpx,pytest
from backend.app.db import Session,Snapshot
from backend.app.deepwiki import DeepWikiOpen
from backend.app.architecture_schema import ArchitectureReport,validate_paths
from backend.app.providers import ProviderError

def archive(files):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:
        for p,t in files.items():z.writestr(zipfile.ZipInfo(p,date_time=(2020,1,1,0,0,0)),t)
    return b.getvalue()
def upload(c,w,files):return c.post(f'/api/workspaces/{w}/repository-upload',content=archive(files),headers={'Content-Type':'application/zip','X-Filename':'project.zip'})

@pytest.mark.parametrize('path',['../escape.py','C:/escape.py','root/NUL.py','root/link/../../escape.py'])
def test_zip_paths(client,wid,path):
    assert upload(client,wid,{path:'x'}).status_code==422

def test_upload_isolation_and_idempotence(client,wid):
    files={'root/app.py':'raise RuntimeError("must not execute")','root/.env':'secret','root/node_modules/x.js':'ignored'}
    first=upload(client,wid,files).json()
    assert first['coverage']['read_files']==['app.py']
    assert len(first['coverage']['omitted'])==2
    assert upload(client,wid,files).json()['id']==first['id']
    other=client.post('/api/workspaces',json={'interest':'other'}).json()['id']
    second=upload(client,other,files).json()
    assert first['metadata_json']['local_relative_path']!=second['metadata_json']['local_relative_path']
    assert client.post(f'/api/workspaces/{other}/architecture-runs',json={'snapshot_id':first['id'],'idempotency_key':'isolated'}).status_code in (404,422)

def test_deepwiki_adapter_and_path_validation(client,wid,monkeypatch):
    snap=upload(client,wid,{'app/workflow.py':'x=1'}).json()
    monkeypatch.setenv('DEEPWIKI_BASE_URL','http://deepwiki.test')
    fixture=json.loads(Path('fixtures/architecture_demo.json').read_text(encoding='utf-8'))
    # Single file common root is removed during upload.
    fixture['report']['overview']['modules'][0]['paths']=['workflow.py']
    fixture['report']['overview']['core_flows'][0]['paths']=['workflow.py']
    fixture['report']['overview']['existing_capabilities'][0]['paths']=['workflow.py']
    fixture['report']['directions'][0]['source_paths']=['workflow.py']
    fixture['wiki']['generated_pages']['overview']['filePaths']=['workflow.py']
    fixture['wiki']['generated_pages']['failed']={'title':'失败页','content':'Error generating content: model error'}
    requests=[]
    def handle(req):
        requests.append(req)
        if req.method=='POST':
            payload=json.loads(req.content);assert payload['comprehensive'] is True;assert payload['type']=='local'
            return httpx.Response(200,json={'task_id':'t','from_cache':True})
        return httpx.Response(200,json=fixture['wiki'])
    with Session() as s: snapshot=s.get(Snapshot,snap['id'])
    p=DeepWikiOpen(transport=httpx.MockTransport(handle),chat_call=lambda _:json.dumps(fixture['report']))
    try:
        wiki=p.wiki(snapshot,lambda *a:None,lambda *a:None,lambda:False)
        report,coverage=p.review(snapshot,wiki,'Agent','MCP multi-agent Skill',lambda *a:None,lambda:False)
        assert coverage['failed_pages']==['失败页']
        assert report['jd_assessment'][0]['recommendation']=='not_needed'
        report['directions']=[];report['no_change_reason']='已有架构足够'
        validate_paths(ArchitectureReport.model_validate(report),snapshot.coverage['read_files'])
        report['overview']['modules'][0]['paths']=['invented.py']
        with pytest.raises(ValueError):validate_paths(ArchitectureReport.model_validate(report),snapshot.coverage['read_files'])
    finally:p.close()

@pytest.mark.parametrize('response,expected', [('not JSON','invalid_json'), ('{}','missing')])
def test_review_records_json_and_schema_diagnostics(client,wid,monkeypatch,response,expected):
    monkeypatch.setenv('DEEPWIKI_BASE_URL','http://deepwiki.test')
    snap=upload(client,wid,{'workflow.py':'x=1'}).json()
    with Session() as s: snapshot=s.get(Snapshot,snap['id'])
    wiki=json.loads(Path('fixtures/architecture_demo.json').read_text(encoding='utf-8'))['wiki']
    diagnostics=[];p=DeepWikiOpen(chat_call=lambda _:response)
    try:
        with pytest.raises(ProviderError):
            p.review(snapshot,wiki,'Agent','Skill',lambda *a:None,lambda:False,diagnostics.append)
        assert len(diagnostics)==2
        assert diagnostics[0]['errors'][0]['type']==expected
        assert 'input' not in diagnostics[0]['errors'][0]
    finally:p.close()

def test_missing_deepwiki_never_falls_back(monkeypatch):
    monkeypatch.delenv('DEEPWIKI_BASE_URL',raising=False)
    with pytest.raises(ProviderError,match='不会用旧AST模板替代'):DeepWikiOpen()

def test_review_repairs_specific_errors_without_accepting_unknown_paths(client,wid,monkeypatch):
    monkeypatch.setenv('DEEPWIKI_BASE_URL','http://deepwiki.test')
    snap=upload(client,wid,{'workflow.py':'x=1'}).json()
    with Session() as s: snapshot=s.get(Snapshot,snap['id'])
    fixture=json.loads(Path('fixtures/architecture_demo.json').read_text(encoding='utf-8'))
    report=fixture['report']
    for m in report['overview']['modules']+report['overview']['existing_capabilities']: m['paths']=['workflow.py']
    for f in report['overview']['core_flows']: f['paths']=['workflow.py']
    for d in report['directions']: d['source_paths']=['workflow.py']
    bad=json.loads(json.dumps(report));bad['overview']['modules'][0]['paths']=['invented.py']
    calls=[];diagnostics=[]
    def chat(payload):
        calls.append(payload['messages'][0]['content'])
        return json.dumps(bad if len(calls)==1 else report)
    p=DeepWikiOpen(chat_call=chat)
    try:
        result,_=p.review(snapshot,fixture['wiki'],'Agent','Skill',lambda *a:None,lambda:False,diagnostics.append)
        assert result['overview']['modules'][0]['paths']==['workflow.py']
        assert 'invented.py' in calls[1] and '上次具体校验错误' in calls[1]
        assert diagnostics[0]['errors'][0]['type']=='ValueError'
        p.chat_call=lambda _:json.dumps(bad)
        with pytest.raises(ProviderError,match='invented.py'):
            p.review(snapshot,fixture['wiki'],'Agent','Skill',lambda *a:None,lambda:False,diagnostics.append)
        assert diagnostics[-1]['attempt']==2
    finally:p.close()

def test_analysis_correction_invalidates_resume(client,wid):
    a=client.post(f'/api/workspaces/{wid}/artifacts',json={'type':'resume','idempotency_key':'a'}).json()
    client.post(f'/api/workspaces/{wid}/evidence',json={'type':'user_statement','excerpt':'已有插件机制，不能声称缺少扩展能力','source_ref':'用户确认的项目分析更正'})
    assert client.get(f'/api/artifacts/{a["id"]}?workspace_id={wid}').json()['review_status']=='needs_review'

def test_github_link_payload_cache_and_switch(client,wid,monkeypatch):
    from backend.app.db import Improvement,Artifact
    link=client.post(f'/api/workspaces/{wid}/repository-link',json={'url':'https://github.com/example/document-agent.git'}).json()
    assert link['metadata_json']['github_url']=='https://github.com/example/document-agent'
    assert link['commit_sha'].startswith('unresolved:')
    assert client.post(f'/api/workspaces/{wid}/repository-link',json={'url':'https://github.com/example/document-agent'}).json()['id']==link['id']
    assert client.post(f'/api/workspaces/{wid}/repository-link',json={'url':'http://127.0.0.1/secret'}).status_code==502
    artifact=client.post(f'/api/workspaces/{wid}/artifacts',json={'type':'resume','idempotency_key':'before-switch'}).json()
    switched=client.post(f'/api/workspaces/{wid}/repository-link',json={'url':'https://github.com/example/other'}).json()
    assert switched['id']!=link['id']
    assert client.get(f'/api/artifacts/{artifact["id"]}?workspace_id={wid}').json()['review_status']=='needs_review'
    monkeypatch.setenv('DEEPWIKI_BASE_URL','http://deepwiki.test')
    fixture=json.loads(Path('fixtures/architecture_demo.json').read_text(encoding='utf-8'))
    def handle(req):
        if req.method=='POST':
            payload=json.loads(req.content)
            assert payload['repo_url']=='https://github.com/example/document-agent'
            assert payload['type']=='github' and payload['comprehensive'] is True
            assert payload['owner']=='example' and payload['repo']=='document-agent'
            return httpx.Response(200,json={'task_id':'github-task','from_cache':True})
        assert req.url.params['repo_type']=='github'
        return httpx.Response(200,json=fixture['wiki'])
    with Session() as s:snapshot=s.get(Snapshot,link['id'])
    p=DeepWikiOpen(transport=httpx.MockTransport(handle),chat_call=lambda _:json.dumps(fixture['report']))
    try:
        wiki=p.wiki(snapshot,lambda *a:None,lambda *a:None,lambda:False)
        report,coverage=p.review(snapshot,wiki,'Agent','Skill MCP',lambda *a:None,lambda:False)
        assert coverage['source_paths']==['app/workflow.py']
        assert '未独立读取源码' in coverage['note']
    finally:p.close()

def test_deepwiki_network_failure_is_specific(client,wid,monkeypatch):
    monkeypatch.setenv('DEEPWIKI_BASE_URL','http://deepwiki.test')
    link=client.post(f'/api/workspaces/{wid}/repository-link',json={'url':'https://github.com/example/project'}).json()
    def handle(req):
        if req.method=='POST':return httpx.Response(200,json={'task_id':'failed'})
        return httpx.Response(200,json={'status':'failed','error':'git clone: RPC failed; Connection was reset'})
    with Session() as s:snapshot=s.get(Snapshot,link['id'])
    p=DeepWikiOpen(transport=httpx.MockTransport(handle))
    try:
        with pytest.raises(ProviderError,match='GitHub仓库下载失败'):
            p.wiki(snapshot,lambda *a:None,lambda *a:None,lambda:False)
    finally:p.close()

def test_archive_fallback_rejects_traversal_and_preserves_existing(monkeypatch,tmp_path):
    import importlib.util
    spec=importlib.util.spec_from_file_location('archive_fallback',Path('scripts/deepwiki_archive_fallback.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    original=httpx.Client
    raw=archive({'repo/../escape.py':'unsafe'})
    monkeypatch.setattr(module.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(lambda _:httpx.Response(200,content=raw)),**kw))
    with pytest.raises(ValueError,match='Unsafe archive path'):
        module.download_github_archive('https://github.com/example/repo',tmp_path/'repo',tmp_path)
    assert not (tmp_path/'escape.py').exists()
    raw=archive({'repo/app.py':'x=1'})
    module.download_github_archive('https://github.com/example/repo',tmp_path/'repo',tmp_path)
    assert (tmp_path/'repo/app.py').read_text()=='x=1'
    with pytest.raises(ValueError,match='Existing repository directory preserved'):
        module.download_github_archive('https://github.com/example/repo',tmp_path/'repo',tmp_path)
