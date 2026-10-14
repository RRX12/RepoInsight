import json
import httpx
import pytest
from backend.app.resume_support import WritingModel
from backend.app.providers import ProviderError

@pytest.mark.parametrize('stage,expected',[
    ('INVESTIGATE',12000),('INVESTIGATE_REPAIR',12000),
    ('INVESTIGATE_SCHEMA_REPAIR',12000),('SYNTHESIZE_REPAIR',12000),
    ('CONTRIBUTION_BIND_SCHEMA_REPAIR',12000),('PROJECT_CONTEXT_REPAIR',6000),
    ('DISCOVER_LINK_REPAIR',3500),('HR_REVIEW',3500)])
def test_full_schema_repair_inherits_budget(monkeypatch,stage,expected):
    monkeypatch.setenv('RESUME_MODEL_API_KEY','offline')
    monkeypatch.setenv('RESUME_DISCOVERY_MAX_TOKENS','12000')
    def handle(request):
        assert json.loads(request.content)['max_tokens']==expected
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{}'}}]})
    model=WritingModel(transport=httpx.MockTransport(handle))
    try:assert model.request(stage,stage=stage)=='{}'
    finally:model.close()

def test_repair_truncation_still_fails(monkeypatch):
    monkeypatch.setenv('RESUME_MODEL_API_KEY','offline')
    model=WritingModel(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'content':'{'}}]})))
    try:
        with pytest.raises(ProviderError) as error:model.request('INVESTIGATE_REPAIR',stage='INVESTIGATE_REPAIR')
        assert error.value.code=='resume_model_truncated'
    finally:model.close()
