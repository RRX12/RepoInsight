import os
import tempfile
from pathlib import Path
os.environ['REPOINSIGHT_DATA']=tempfile.mkdtemp(prefix='repocareer-tests-')
os.environ['REPOINSIGHT_DEMO']='true'
# Legacy fixtures explicitly test the compatibility path, independent of the local .env.
# Enhanced behavior tests select their mode with monkeypatch.
os.environ['WIKI_RETRIEVAL_MODE']='legacy'
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
    if request.module.__name__.split('.')[-1] not in ('test_shared_analysis','test_project_flow','test_advisor'):return
    from backend.tests.source_fixture import Reader,Retriever
    monkeypatch.setattr('backend.app.shared_analysis.CodeRetrieval',Retriever)
    monkeypatch.setattr('backend.app.shared_analysis.cache_directory',lambda:tmp_path/'analysis')
    monkeypatch.setattr('backend.app.optimization_review.cache_directory',lambda:tmp_path/'analysis')
    monkeypatch.setattr('backend.app.source_reader.SourceReader.resolve_revision',lambda self,repo,ref=None:{'commit_sha':'a'*40,'status':'resolved'})
