import json
import pytest
from backend.app.resume_harness import Harness
from backend.app.providers import ProviderError

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
