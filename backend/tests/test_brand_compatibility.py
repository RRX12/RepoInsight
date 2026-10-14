"""Renaming must preserve legacy data and let the new namespace take precedence."""
import json,os,subprocess,sys
from pathlib import Path
import pytest

@pytest.mark.parametrize('legacy,new,expected',[(False,False,'repoinsight.db'),(True,False,'repocareer.db'),(True,True,'repoinsight.db')])
def test_database_name_and_data_directory_compatibility(tmp_path,legacy,new,expected):
    current=tmp_path/'new';current.mkdir()
    if legacy:(current/'repocareer.db').touch()
    if new:(current/'repoinsight.db').touch()
    env={**os.environ,'REPOINSIGHT_DATA':str(current),'REPOCAREER_DATA':str(tmp_path/'wrong')}
    result=subprocess.run([sys.executable,'-c',"import json;from backend.app.db import DATA,DB_FILE;print(json.dumps({'data':str(DATA),'file':DB_FILE.name}))"],env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    value=json.loads(result.stdout);assert Path(value['data'])==current and value['file']==expected
    assert not (tmp_path/'wrong').exists()

def test_new_demo_configuration_overrides_legacy(monkeypatch):
    from backend.app.providers import ModelProvider
    monkeypatch.setenv('OPENAI_API_KEY','offline')
    monkeypatch.setenv('REPOINSIGHT_DEMO','false');monkeypatch.setenv('REPOCAREER_DEMO','true')
    assert not ModelProvider().demo
