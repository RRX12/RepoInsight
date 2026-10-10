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
def client(monkeypatch):
    # API fixtures use invented repositories, never perform live GitHub calls.
    monkeypatch.setattr('backend.app.source_reader.SourceReader.resolve_revision',lambda self,repo,ref=None:{'commit_sha':'unresolved:github','status':'unresolved','error':'offline fixture'})
    with TestClient(app) as client:
        yield client
    # Keep schema/migration version stable, remove data in FK-safe reverse order.
    with engine.begin() as c:
        for table in reversed(Base.metadata.sorted_tables): c.execute(table.delete())

@pytest.fixture
def wid(client):
    return client.post('/api/workspaces',json={'interest':'document processing','skills':'Python','time_budget':'2 周','environment':'CPU'}).json()['id']
