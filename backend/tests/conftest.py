import os
import tempfile
from pathlib import Path
os.environ['REPOCAREER_DATA']=tempfile.mkdtemp(prefix='repocareer-tests-')
os.environ['REPOCAREER_DEMO']='true'
from fastapi.testclient import TestClient
import pytest
from backend.app.main import app
from backend.app.db import Base, engine

@pytest.fixture
def client(monkeypatch,request):
    # API fixtures use invented repositories, never perform live GitHub calls.
    monkeypatch.setattr('backend.app.source_reader.SourceReader.resolve_revision',lambda self,repo,ref=None:{'commit_sha':'a'*40,'status':'resolved'})
    with TestClient(app) as client:
        yield client
    # Keep schema/migration version stable, remove data in FK-safe reverse order.
    with engine.begin() as c:
        for table in reversed(Base.metadata.sorted_tables): c.execute(table.delete())

@pytest.fixture
def wid(client):
    return client.post('/api/workspaces',json={'interest':'document processing','skills':'Python','time_budget':'2 周','environment':'CPU'}).json()['id']

@pytest.fixture(autouse=True)
def isolated_writer_sources(request,monkeypatch,tmp_path):
    # Only writer contract tests: run real shared analysis, fake external I/O only.
    if request.module.__name__.split('.')[-1] not in ('test_resume_quality','test_resume_mechanisms','test_resume_roles_index','test_shared_analysis'):return
    from backend.tests.source_fixture import Reader,Retriever
    monkeypatch.setattr('backend.app.resume_quality.SourceReader',Reader)
    monkeypatch.setattr('backend.app.shared_analysis.CodeRetrieval',Retriever)
    monkeypatch.setattr('backend.app.shared_analysis.cache_directory',lambda:tmp_path/'analysis')
    monkeypatch.setattr('backend.app.source_reader.SourceReader.resolve_revision',lambda self,repo,ref=None:{'commit_sha':'a'*40,'status':'resolved'})
