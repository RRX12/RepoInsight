"""Offline integration using the installed sidecar splitter, LocalDB and real ASGI routes.
Run with the sidecar Python; fake embeddings and a temporary self-created Git repository.
Does not install extensions, start services, touch existing indexes, or call any model.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace

p=argparse.ArgumentParser();p.add_argument('--sidecar',type=Path,required=True);args=p.parse_args()
sidecar=args.sidecar.resolve();root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(sidecar))
with tempfile.TemporaryDirectory(prefix='repocareer-native-index-') as tmp:
    temp=Path(tmp)
    os.environ['DEEPWIKI_CONFIG_DIR']=str(sidecar/'api/config')
    import api.config as config
    import api.repository as repository
    import api.utils as utils
    import api.rag.pipeline as pipeline
    from adalflow.core.types import Document
    from adalflow.core.db import LocalDB
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    def load(name,path):
        spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod);return mod
    raw=load('api.repocareer_raw_index',root/'scripts/deepwiki_raw_index.py')
    routes=load('api.repocareer_raw_routes',root/'scripts/deepwiki_raw_routes.py')
    # Archive filtering skips sensitive files but still rejects traversal.
    import io,zipfile
    def archive(entries):
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as z:
            for name,text in entries.items():z.writestr(name,text)
        return buffer.getvalue()
    original_stream=routes.httpx.stream
    class Stream:
        def __init__(self,data):self.data=data
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def raise_for_status(self):pass
        def iter_bytes(self):yield self.data
    routes.httpx.stream=lambda *a,**k:Stream(archive({'root/.env.example':'SECRET=x','root/main.py':'print(1)'}))
    files,skipped=routes.archive_files('example/repo','a'*40)
    assert files=={'main.py':'print(1)'} and '.env.example' in skipped
    routes.httpx.stream=lambda *a,**k:Stream(archive({'root/../escape.py':'x'}))
    try:routes.archive_files('example/repo','a'*40)
    except ValueError as e:assert str(e)=='archive_path'
    else:raise AssertionError('Traversal accepted')
    routes.httpx.stream=original_stream
    real_repo=repository.Repo
    repository.Repo=lambda **kw:real_repo(**kw,root_path=str(temp/'repos'))
    utils.deepwiki_root=lambda:str(temp/'data')
    config.get_embedder_config=lambda:{'model_kwargs':{'model':'fake-2d'},'client_class':'offline','initialize_kwargs':{}}
    calls=[]
    def embed(*,input):
        calls.append(input);return SimpleNamespace(error=None,data=[SimpleNamespace(embedding=[1.,float(len(input)%7+1)])])
    config.get_embedder=lambda:embed
    repo=repository.Repo(repo_url='https://github.com/offline/example',repo_type='github')
    folder=Path(repo.save_path);folder.mkdir(parents=True)
    def git(*arguments):return subprocess.check_output(['git','-c','core.autocrlf=false','-C',str(folder),*arguments],stderr=subprocess.DEVNULL).decode().strip()
    git('init');files={'main.py':'def run():\n    return 1\n','old.py':'OLD = 1\n'}
    for path,text in files.items():(folder/path).write_text(text,encoding='utf-8',newline='')
    git('add','.');git('-c','user.name=Offline','-c','user.email=offline@example.invalid','commit','-m','fixture')
    sha=git('rev-parse','HEAD')
    splitter=pipeline.LineTrackingTextSplitter(**config.configs['text_splitter'])
    docs=splitter.call([Document(text=t,meta_data={'file_path':p}) for p,t in files.items()])
    for doc in docs:doc.vector=[1.,float(len(doc.text)%7+1)]
    db=LocalDB();db.transformed_items['split_and_embed']=docs;seed=temp/raw.digest({'model_kwargs':{'model':'fake-2d'},'client_class':'offline','base_url':None})[:16]/'seed.pkl';seed.parent.mkdir();db.save_state(str(seed))
    pipeline.get_repo_db=lambda repo:str(seed)
    app=FastAPI();app.include_router(routes.router)
    with TestClient(app) as client:
        body={'repo_identity':'offline/example','snapshot_revision':sha,'max_new_vectors':0}
        r=client.post('/repocareer/code/prepare',json=body);assert r.status_code==200,r.text
        m=r.json()['manifest'];assert not calls,'native chunks must reuse seeded vectors'
        original_read=routes.git_files
        def forbid_read(*args):raise AssertionError('same version must not reread repository')
        routes.git_files=forbid_read
        assert client.post('/repocareer/code/prepare',json=body).json()['reused']
        routes.git_files=original_read
        query={'repo_identity':'offline/example','snapshot_revision':sha,'index_id':m['index_id'],'expected_embedding_fingerprint':m['embedding_fingerprint'],'query':'task state','top_k':2}
        r=client.post('/repocareer/code/search',json=query);assert r.status_code==200,r.text
        hits=r.json()['hits'];assert {h['path'] for h in hits}==set(files)
        assert all(h['text'] in files[h['path']] for h in hits) and len(calls)==1
        assert client.post('/repocareer/code/search',json=query).json()['cached'] and len(calls)==1
        (folder/'old.py').unlink();(folder/'new.py').write_text('NEW = 2\n',encoding='utf-8',newline='')
        git('add','-A');git('-c','user.name=Offline','-c','user.email=offline@example.invalid','commit','-m','revision')
        newer=git('rev-parse','HEAD')
        assert client.post('/repocareer/code/prepare',json={**body,'snapshot_revision':newer}).status_code==409
        r=client.post('/repocareer/code/prepare',json={**body,'snapshot_revision':newer,'max_new_vectors':1});assert r.status_code==200,r.text
        assert r.json()['usage']['code_calls']==1 and len(calls)==2
        assert client.post('/repocareer/code/search',json={**query,'snapshot_revision':newer}).status_code==409
        assert client.post('/repocareer/code/search',json={**query,'expected_embedding_fingerprint':'wrong'}).status_code==409
    print(json.dumps({'native_splitter':True,'native_LocalDB':True,'ASGI_routes':True,'initial_code_embedding_calls':0,'new_revision_embedding_calls':1,'query_embedding_calls':1,'network_model_calls':0}))
