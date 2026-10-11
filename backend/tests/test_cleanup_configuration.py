import json
import runpy
from pathlib import Path
import httpx
import pytest
from backend.app.resume_support import WritingModel, cache_directory
from backend.app.resume_harness import Harness


def test_writer_model_config_is_independent_of_deepwiki(monkeypatch,tmp_path):
    monkeypatch.setenv('RESUME_MODEL_ENV_FILE',str(tmp_path/'absent.env'))
    monkeypatch.setenv('RESUME_MODEL_API_KEY','fixture-key')
    monkeypatch.setenv('RESUME_MODEL_BASE_URL','https://fixture/')
    monkeypatch.setenv('DEEPWIKI_MODEL','ollama-only-model')
    monkeypatch.delenv('RESUME_MODEL',raising=False)
    model=WritingModel(transport=httpx.MockTransport(lambda r:httpx.Response(500)))
    assert model.model=='deepseek-v4-pro' and model.base=='https://fixture'
    model.close()
    monkeypatch.setenv('RESUME_MODEL','explicit-model')
    model=WritingModel(transport=httpx.MockTransport(lambda r:httpx.Response(500)))
    assert model.model=='explicit-model'
    model.close()


def test_cache_override_and_explicit_stage_protocol(monkeypatch,tmp_path):
    monkeypatch.setenv('RESUME_ANALYSIS_CACHE_DIR',str(tmp_path))
    assert cache_directory()==tmp_path
    monkeypatch.setenv('RESUME_MODEL_ENV_FILE',str(tmp_path/'absent.env'))
    monkeypatch.setenv('RESUME_MODEL_API_KEY','fixture-key')
    requests=[]
    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200,json={'choices':[{'message':{'content':'{}'}}]})
    model=WritingModel(transport=httpx.MockTransport(handle))
    try:
        # A text edit cannot switch the production format off or change the stage budget.
        model.request('arbitrary text without schema',stage='WRITE',json_output=True)
        Harness(model,structured_output=True).call('WRITE\ntext without schema')
        assert all(r['response_format']=={'type':'json_object'} and r['max_tokens']==5000 for r in requests)
        assert all(u['stage']=='WRITE' for u in model.usage)
    finally:model.close()


def test_sidecar_initialization_refuses_existing_configuration_before_any_write(tmp_path):
    script=Path(__file__).resolve().parents[2]/'scripts/configure-deepwiki.py'
    initialize=runpy.run_path(str(script))['initialize']
    api=tmp_path/'api/config';api.mkdir(parents=True)
    generator=api/'generator.json';generator.write_text(json.dumps({'providers':{'ollama':{'models':{}}}}),encoding='utf-8')
    (api/'embedder.json').write_text(json.dumps({'embedder_ollama':{}}),encoding='utf-8')
    (tmp_path/'api/config.py').write_text('text only; never execute this source',encoding='utf-8')
    env=tmp_path/'.env';env.write_text('CUSTOM_KEY=fictional-secret\nCLOUD_CONFIG=fixture\n',encoding='utf-8')
    before={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    with pytest.raises(ValueError):initialize(tmp_path)
    assert all(p.read_bytes()==data for p,data in before.items())
    env.unlink()  # Only this test's fictional temporary configuration.
    initialize(tmp_path)
    first={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    with pytest.raises(ValueError):initialize(tmp_path)
    assert all(p.read_bytes()==data for p,data in first.items())
