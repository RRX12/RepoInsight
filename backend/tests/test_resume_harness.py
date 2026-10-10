import json
import pytest
from backend.app.resume_harness import Harness, chunks
from backend.app.providers import ProviderError


def material(text, workspace='a'):
    return {'workspace_id':workspace,'snapshot_id':'s','repo':'o/r',
            '_full_wiki_pages':[{'title':'角色','content':text}]}


def mapper(calls):
    def chat(prompt):
        calls.append(prompt)
        batch=json.loads(prompt.split('\nJSON schema:')[0].split('\n')[-1])
        return json.dumps({'facts':[{'capability':'保存经历','mechanism':'读取状态','limitation':'效果未验证',
                                    'source_ref':c['spans'][-1]['id'],'quote':''} for c in batch],
                           'uncertainties':[]},ensure_ascii=False)
    return chat


def test_every_character_and_tail_enters_mapping_without_jd():
    data=material('a'*11000+'末尾关系状态影响动作')
    parts=chunks(data)
    assert ''.join(c['content'] for c in parts)==data['_full_wiki_pages'][0]['content']
    calls=[];result=Harness(mapper(calls)).map_wiki({**data,'jd':'不可传入的岗位关键词'})
    assert len(result['coverage'])==3
    assert '末尾关系状态影响动作' in calls[-1]
    assert all('不可传入的岗位关键词' not in p for p in calls)


def test_cache_is_source_model_workspace_and_version_scoped(tmp_path):
    calls=[]
    Harness(mapper(calls),model='m1',cache_dir=tmp_path).map_wiki(material('事实'))
    cached=Harness(mapper(calls),model='m1',cache_dir=tmp_path).map_wiki(material('事实'))
    assert len(calls)==1 and cached['cache_hits']==1
    for data,model in [(material('新事实'),'m1'),(material('事实','b'),'m1'),(material('事实'),'m2')]:
        Harness(mapper(calls),model=model,cache_dir=tmp_path).map_wiki(data)
    assert len(calls)==4


def test_invented_quote_or_chunk_is_rejected_and_not_cached(tmp_path):
    def chat(_):
        return json.dumps({'facts':[{'capability':'自主','mechanism':'决策','limitation':'',
                                    'source_ref':'wiki:0:chunk:0','quote':'原文没有的证据'}],'uncertainties':[]})
    with pytest.raises(ProviderError):Harness(chat,cache_dir=tmp_path).map_wiki(material('只有文本'))
    assert not list(tmp_path.glob('*.json'))


def test_large_project_budget_fails_explicitly_before_any_call():
    calls=[]
    with pytest.raises(ProviderError):Harness(mapper(calls)).map_wiki(material('x'*(5000*129)))
    assert not calls


def test_interrupted_mapping_resumes_cached_completed_batches(tmp_path):
    calls=[];normal=mapper(calls)
    def chat(p):
        if len(calls)==1:raise ProviderError('中断','test')
        return normal(p)
    data=material('x'*21000)
    with pytest.raises(ProviderError):Harness(chat,cache_dir=tmp_path).map_wiki(data)
    result=Harness(normal,cache_dir=tmp_path).map_wiki(data)
    assert result['cache_hits']==1 and len(result['coverage'])==5


def test_evidence_anchor_program_fills_original_quote():
    calls=[];data=material('原文：角色读取过去经历。')
    result=Harness(mapper(calls)).map_wiki(data)
    assert result['facts'][0]['quote']=='原文：角色读取过去经历。'
    assert result['facts'][0]['source_ref'].endswith(':span:0')


def test_reported_token_budget_stops_next_call(monkeypatch):
    monkeypatch.setenv('RESUME_MAX_REPORTED_TOKENS','1')
    class Chat:
        usage=[{'usage':{'total_tokens':1}}]
        def __call__(self,p):raise AssertionError('不应调用')
    with pytest.raises(ProviderError):Harness(Chat()).call('WRITE\n文本')


def test_failed_call_keeps_metadata_without_prompt_or_secret(tmp_path):
    def chat(_):raise ProviderError('连接失败','test')
    harness=Harness(chat,cache_dir=tmp_path)
    with pytest.raises(ProviderError):harness.call('WRITE\nSECRET_MATERIAL')
    trace=json.loads((tmp_path/'attempts'/(harness.trace_id+'.json')).read_text(encoding='utf-8'))
    assert trace['calls'][0]['status']=='failed' and trace['calls'][0]['usage'] is None
    assert 'SECRET_MATERIAL' not in json.dumps(trace)
