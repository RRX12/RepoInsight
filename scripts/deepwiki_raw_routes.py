"""Loopback-only sidecar extension; explicit index preparation, no Wiki generation."""
import json
import io
import zipfile
import stat
import httpx
import re
import subprocess
from pathlib import Path, PurePosixPath
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ConfigDict
from api.repocareer_raw_index import Index, digest, safe_path,VERSION

router=APIRouter(prefix='/repocareer/code')

class Identity(BaseModel):
    model_config=ConfigDict(extra='forbid')
    repo_identity:str=Field(pattern=r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')
    snapshot_revision:str=Field(pattern=r'^([0-9a-f]{40}|archive-sha256:[0-9a-f]{64})$')

class Prepare(Identity):
    max_new_vectors:int=Field(default=0,ge=0,le=10000)
    uploaded_files:dict[str,str]|None=None

class Search(Identity):
    index_id:str=Field(pattern=r'^[0-9a-f]{64}$')
    expected_embedding_fingerprint:str
    query:str=Field(min_length=1,max_length=1000)
    top_k:int=Field(default=8,ge=1,le=16)

def bound(request,body):
    if request.client is None or request.client.host not in ('127.0.0.1','::1','testclient'):
        raise HTTPException(403,'loopback_only')
    from api.repository import Repo
    from api.config import get_embedder_config,get_embedder,configs
    from api.utils import deepwiki_root
    repo=Repo(repo_url='https://github.com/'+body.repo_identity,repo_type='github')
    folder=Path(repo.save_path).resolve()
    cfg=get_embedder_config()
    fingerprint=digest({'model_kwargs':cfg.get('model_kwargs'),'client_class':cfg.get('client_class'),'base_url':cfg.get('initialize_kwargs',{}).get('base_url')})
    def embed(text):
        result=get_embedder()(input=text)
        if getattr(result,'error',None):
            if 'FreeTierOnly' in str(result.error):raise ValueError('embedding_free_quota_exhausted')
            raise ValueError('embedding_failed')
        return list(result.data[0].embedding)
    from api.rag.pipeline import LineTrackingTextSplitter
    from adalflow.core.types import Document
    splitter=LineTrackingTextSplitter(**configs['text_splitter'])
    def split(path,text):return [doc.text for doc in splitter.call([Document(text=text,meta_data={'file_path':path})])]
    version=VERSION+'/filter-text-v1/deepwiki-line-tracking:'+digest(configs['text_splitter'])
    def rank(vectors,query):
        import numpy as np
        import faiss
        matrix=np.asarray(vectors,dtype='float32');q=np.asarray([query],dtype='float32')
        faiss.normalize_L2(matrix);faiss.normalize_L2(q)
        searcher=faiss.IndexFlatIP(matrix.shape[1]);searcher.add(matrix)
        scores,indices=searcher.search(q,len(vectors))
        return [(int(i),float(score)) for i,score in zip(indices[0],scores[0]) if i>=0]
    return repo,folder,Index(Path(deepwiki_root())/'repocareer-code-index',fingerprint,embed,version,split,rank)

def git(folder,*args):
    # Only Git object reads, no checkout, hooks, shell, or imported repository execution.
    r=subprocess.run(['git','--no-replace-objects','-C',str(folder),*args],capture_output=True,timeout=30,check=True)
    return r.stdout

def accepted(path,size,mode='100644'):
    return mode in ('100644','100755') and safe_path(path) and size<=524288 and not any(p in ('node_modules','vendor','dist','.venv') for p in Path(path).parts) and Path(path).suffix.lower() in ('.md','.py','.ts','.tsx','.js','.jsx','.mjs','.json','.toml','.yaml','.yml','.go','.rs','.java','.cs','.cpp','.h','.sql')

def git_files(folder,revision):
    if git(folder,'rev-parse',revision+'^{commit}').decode().strip()!=revision:raise ValueError('version_mismatch')
    files={};skipped=[];total=0
    for entry in git(folder,'ls-tree','-rz','--full-tree',revision).decode().split('\0'):
        if not entry:continue
        header,path=entry.split('\t',1);mode,kind,oid=header.split()
        size=int(git(folder,'cat-file','-s',oid)) if mode in ('100644','100755') else 0
        if not accepted(path,size,mode):skipped.append(path);continue
        total+=size
        if total>20_000_000 or len(files)>=20000:raise ValueError('repository_read_budget')
        try:text=git(folder,'cat-file','blob',oid).decode('utf-8')
        except UnicodeDecodeError:skipped.append(path);continue
        if '\0' in text:skipped.append(path);continue
        files[path]=text
    return files,skipped

def archive_files(repo,revision):
    # Isolated immutable archive; never unpack or overwrite the sidecar working tree.
    data=bytearray()
    with httpx.stream('GET','https://codeload.github.com/'+repo+'/zip/'+revision,timeout=60,follow_redirects=False) as response:
        response.raise_for_status()
        for part in response.iter_bytes():
            data.extend(part)
            if len(data)>50_000_000:raise ValueError('archive_download_budget')
    files={};skipped=[];total=0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if len(archive.infolist())>20000:raise ValueError('archive_entry_budget')
        for entry in archive.infolist():
            if entry.is_dir():continue
            parts=entry.filename.split('/',1)
            if len(parts)!=2 or PurePosixPath(parts[1]).is_absolute() or '..' in PurePosixPath(parts[1]).parts or '\\' in parts[1] or ':' in parts[1]:raise ValueError('archive_path')
            path=parts[1]
            if stat.S_ISLNK(entry.external_attr>>16) or not accepted(path,entry.file_size):skipped.append(path);continue
            total+=entry.file_size
            if total>20_000_000:raise ValueError('repository_read_budget')
            try:text=archive.read(entry).decode('utf-8')
            except UnicodeDecodeError:skipped.append(path);continue
            if '\0' in text:skipped.append(path);continue
            files[path]=text
    return files,skipped

@router.post('/prepare')
def prepare(request:Request,body:Prepare):
    repo,folder,index=bound(request,body)
    try:
        cached=index.find(body.repo_identity,body.snapshot_revision)
        if cached:
            cached.pop('chunks',None)
            return {'manifest':cached,'usage':index.usage(),'reused':True,'unread_paths':cached['coverage'].get('unread_paths',[])}
        revision=body.snapshot_revision
        if revision.startswith('archive-sha256:'):
            if body.uploaded_files is None:raise ValueError('uploaded_snapshot_required')
            files=body.uploaded_files;skipped=[]
            if len(files)>20000 or sum(len(t.encode()) for t in files.values())>20_000_000 or any(not safe_path(p) or len(t.encode())>524288 or '\0' in t for p,t in files.items()):raise ValueError('uploaded_file_budget_or_path')
        else:
            if body.uploaded_files is not None:raise ValueError('github_files_must_come_from_fixed_sha')
            try:files,skipped=git_files(folder,revision)
            except (OSError,subprocess.SubprocessError):files,skipped=archive_files(body.repo_identity,revision)
        # Existing sidecar owns deserialization; RepoInsight never opens this pickle.
        seed=[]
        from api.rag.pipeline import get_repo_db
        from adalflow.core.db import LocalDB
        existing=Path(get_repo_db(repo))
        if existing.is_file() and existing.parent.name==index.fingerprint[:16]:
            db=LocalDB.load_state(str(existing))
            for doc in db.get_transformed_data(key='split_and_embed') or []:
                vector=getattr(doc,'vector',None)
                if vector is not None:seed.append((doc.text,list(vector)))
        result=index.prepare(body.repo_identity,revision,files,body.max_new_vectors,seed,skipped)
        result['unread_paths']=skipped
        # No raw vectors or API credentials leave this process.
        result['manifest'].pop('chunks',None)
        return result
    except (ValueError,OSError,subprocess.SubprocessError,httpx.HTTPError,zipfile.BadZipFile) as exc:
        reason=str(exc) if isinstance(exc,ValueError) else 'snapshot_unavailable'
        raise HTTPException(409,reason) from exc

@router.post('/search')
def search(request:Request,body:Search):
    _,_,index=bound(request,body)
    if body.expected_embedding_fingerprint!=index.fingerprint:raise HTTPException(409,'embedding_configuration_mismatch')
    try:return index.search(body.index_id,body.repo_identity,body.snapshot_revision,body.query,body.top_k)
    except (ValueError,OSError):raise HTTPException(409,'index_unavailable_or_version_mismatch')
