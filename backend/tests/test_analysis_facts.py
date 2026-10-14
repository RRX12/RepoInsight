import json,base64
from pathlib import Path
import httpx,pytest
from backend.app.providers import ProviderError,GitHub
from backend.app.source_reader import SourceReader,SourceEvidence,sha256
from backend.app.analysis_contract import *
SHA="a"*40
def claim(i='c1',support='insufficient'):
    return {'id':i,'statement':'角色记忆按版本更新，过期更新被拒绝。','evidence_ids':['source:memory'],'support':support,'implementation_state':'implemented','attribution':'upstream','validation_level':'unknown'}


def candidate(i='n1',cid='c1'):
    return {'candidate_id':i,'title':'版本化记忆','mechanism':'拒绝过期更新','claim_ids':[cid],'requirement_ids':['r1'],'reason':'状态连续性'}


def test_source_fixed_revision_cache_and_invalid_paths(tmp_path):
    calls=[]
    def handle(req):
        calls.append(str(req.url))
        if '/commits/' in req.url.path:return httpx.Response(200,json={'sha':SHA})
        if '/git/trees/' in req.url.path:return httpx.Response(200,json={'tree':[{'path':'memory.ts','type':'blob','mode':'100644'}]})
        if '/contents/' in req.url.path:
            assert req.url.params['ref']==SHA
            return httpx.Response(200,json={'type':'file','size':20,'encoding':'base64','content':base64.b64encode(b'if old: reject()\n').decode()})
        return httpx.Response(200,json={'default_branch':'main'})
    r=SourceReader('w',github=GitHub(httpx.MockTransport(handle)),cache_dir=tmp_path)
    assert r.resolve_revision('example/demo')['commit_sha']==SHA
    assert r.list_tree('example/demo',SHA)['paths']==['memory.ts']
    a=r.read_source('example/demo',SHA,'memory.ts');n=len(calls)
    assert r.read_source('example/demo',SHA,'memory.ts').id==a.id and len(calls)==n
    for path in ('../x','.env','config/.env.secret','x.pem','x.PEM'):
        with pytest.raises(ProviderError):r.read_source('example/demo',SHA,path)
    with pytest.raises(ProviderError):r.read_source('example/demo','unresolved','memory.ts')
    r.close()


def context():return GenerationContext(workspace_id='w',snapshot_id='s',commit_sha=SHA,revision_status='resolved',role='AI',jd_version_id='j',target_origin='jd',material_fingerprint='f')


def test_old_source_and_test_definition_cannot_be_runtime_validation():
    e=SourceEvidence(id='e',kind='test_source',repo='x/y',commit_sha='b'*40,content_hash='h',excerpt='assert',revision_status='resolved')
    c=Claim(id='c',statement='测试通过',evidence_ids=['e'],support='supported',implementation_state='implemented',validation_level='test_passed')
    with pytest.raises(ValueError):check_claims([c],{'e':e},context(),{})
    e.commit_sha=SHA
    with pytest.raises(ValueError):check_claims([c],{'e':e},context(),{})


def test_contribution_retraction_cannot_remain_supported():
    e=SourceEvidence(id='optimization:p',kind='user_statement',repo='x/y',commit_sha=SHA,content_hash='h',excerpt='我还没实现',revision_status='user_submitted')
    c=Claim(id='c',statement='我已实现',evidence_ids=[e.id],support='supported',implementation_state='implemented',attribution='user_confirmed',contribution_id='p')
    with pytest.raises(ValueError):check_claims([c],{e.id:e},context(),{'p':{'id':'p','state':'proposed','action':'只是讨论','evidence_ids':[]}})


def test_fixed_revision_is_used_after_branch_changes(tmp_path):
    from types import SimpleNamespace
    refs=[]
    def handler(req):
        refs.append(str(req.url))
        return httpx.Response(200,json={'type':'file','size':10,'encoding':'base64','content':base64.b64encode(b'old code').decode()})
    r=SourceReader('w',SimpleNamespace(owner='example',repo='demo',commit_sha=SHA),GitHub(httpx.MockTransport(handler)),tmp_path)
    assert r.read_source('example/demo',SHA,'memory.ts').commit_sha==SHA
    assert 'ref='+SHA in refs[0]
    with pytest.raises(ProviderError):r.read_source('example/demo','b'*40,'memory.ts')
    r.close()


def test_model_output_truncation_is_not_a_completed_json():
    from backend.app.model_support import ProjectModel
    model=ProjectModel.__new__(ProjectModel);model.base='https://fixture';model.key='fixture-key';model.model='fixture';model.usage=[]
    model.client=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'choices':[{'message':{'content':'{"broken":'},'finish_reason':'length'}],'usage':{'total_tokens':10}})))
    with pytest.raises(ProviderError) as caught:model('PRODUCT\nJSON schema:{}')
    assert caught.value.code=='resume_model_truncated' and model.usage[0]['usage']['total_tokens']==10
    model.close()
