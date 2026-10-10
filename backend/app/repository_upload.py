"""Validated text-only repository imports. Imported code is never executed."""
import hashlib
import io
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath
from fastapi import HTTPException
from .db import DATA, Snapshot, Finding, Improvement
from .memory import scoped, attach, invalidate

MAX_ARCHIVE = 20 * 1024 * 1024
MAX_EXPANDED = 50 * 1024 * 1024
MAX_FILE = 1024 * 1024
MAX_ENTRIES = 5000
EXCLUDED = {'.git','.svn','node_modules','.venv','venv','__pycache__','dist','build','vendor','.idea','.next','coverage'}
TEXT_TYPES = {'.py','.md','.txt','.rst','.toml','.yaml','.yml','.json','.xml','.ini','.cfg','.js','.jsx','.ts','.tsx','.css','.scss','.html','.vue','.svelte','.go','.rs','.java','.kt','.c','.h','.cpp','.hpp','.cs','.sql','.sh','.ps1','.dockerfile','.proto','.graphql','.ipynb','.rb','.php'}
def valid_archive_path(name):
    if not name or '\\' in name or name.startswith('/') or ':' in name or '\x00' in name: return False
    parts = PurePosixPath(name).parts
    return bool(parts) and all(p not in ('.','..') and not p.endswith(('.', ' ')) and not re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',p,re.I) for p in parts)

def import_zip(s, wid, raw, filename='repository.zip'):
    if len(raw)>MAX_ARCHIVE: raise HTTPException(413,'仓库 ZIP 超过20 MB')
    archive_hash = hashlib.sha256(raw).hexdigest()
    previous = scoped(s,Snapshot,wid)
    for snap in previous[-1:]:
        if snap.metadata_json.get('archive_hash')==archive_hash: return snap
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        entries = z.infolist()
        if len(entries)>MAX_ENTRIES or sum(x.file_size for x in entries)>MAX_EXPANDED:
            raise HTTPException(413,'解压范围超过5000条目或50 MB，请移除依赖/构建产物后上传')
        # Validate every path first; a malicious ignored entry still rejects the upload.
        names=set()
        for e in entries:
            if not valid_archive_path(e.filename.rstrip('/')) or stat.S_ISLNK(e.external_attr>>16):
                raise HTTPException(422,'ZIP 含非法路径、Windows设备路径或符号链接')
            key=e.filename.rstrip('/').casefold()
            if key in names: raise HTTPException(422,'ZIP 含重复或大小写冲突路径')
            names.add(key)
            if e.flag_bits & 1: raise HTTPException(422,'不接受加密 ZIP')
        files=[e for e in entries if not e.is_dir()]
        root=None
        if files and all('/' in e.filename for e in files):
            roots={e.filename.split('/')[0] for e in files}
            if len(roots)==1: root=next(iter(roots))+'/'
        accepted={};omitted=[]
        for e in files:
            path=e.filename[len(root):] if root else e.filename
            p=PurePosixPath(path)
            if any(x.lower() in EXCLUDED for x in p.parts) or p.name.lower().startswith('.env') or p.suffix.lower() in {'.pem','.key','.p12','.pfx'}:
                omitted.append({'path':path,'reason':'依赖/构建/版本目录或敏感配置'});continue
            if e.file_size>MAX_FILE:
                omitted.append({'path':path,'reason':'单文件超过1 MB'});continue
            if p.suffix.lower() not in TEXT_TYPES and p.name.lower() not in ('dockerfile','makefile','license','requirements.txt'):
                omitted.append({'path':path,'reason':'非支持的源码/文档文本类型'});continue
            content=z.read(e)
            if b'\x00' in content:
                omitted.append({'path':path,'reason':'二进制'});continue
            try: accepted[path]=content.decode('utf-8-sig')
            except UnicodeDecodeError: omitted.append({'path':path,'reason':'非UTF-8文本'})
        z.close()
    except (zipfile.BadZipFile,RuntimeError,ValueError,NotImplementedError):
        raise HTTPException(422,'无法解析 ZIP，请上传未加密的标准 ZIP 仓库压缩包')
    if not accepted: raise HTTPException(422,'ZIP 中没有可分析的源码或文档文本')
    manifest='\n'.join(f'{p}:{hashlib.sha256(t.encode()).hexdigest()}' for p,t in sorted(accepted.items()))
    digest=hashlib.sha256(manifest.encode()).hexdigest()
    # Unique directory names also isolate DeepWiki-Open's local index cache across workspaces.
    folder=DATA/'workspaces'/wid/'repositories'/f'{wid}-{digest}'
    folder.mkdir(parents=True,exist_ok=True)
    for path,text in accepted.items():
        target=(folder/path).resolve()
        if not target.is_relative_to(folder.resolve()): raise HTTPException(422,'路径越界')
        target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text,encoding='utf-8')
    coverage={'read_files':list(accepted),'omitted':omitted,'archive_entries':len(entries),'accepted_files':len(accepted),'tree_truncated':False,
        'note':'上传的文本快照；排除依赖、构建、敏感配置与超限文件。未执行代码。内容哈希不是Git commit SHA。'}
    snapshot=Snapshot(workspace_id=wid,owner='uploaded',repo=Path(filename).stem[:100],commit_sha='archive-sha256:'+digest,
        metadata_json={'mode':'uploaded','archive_hash':archive_hash,'local_relative_path':folder.relative_to(DATA).as_posix(),'description':'用户上传仓库 ZIP','filename':filename,'source_kind':'archive'},coverage=coverage)
    s.add(snapshot);s.flush()
    for path,text in accepted.items():
        attach(s,wid,'readme' if 'readme' in PurePosixPath(path).name.lower() else 'source_code',text,f'upload://{snapshot.id}/{path}',snapshot_id=snapshot.id,path=path,line_start=1,line_end=max(1,len(text.splitlines())))
    if previous:
        prev=previous[-1]
        for f in scoped(s,Finding,wid):
            if f.snapshot_id==prev.id: f.status='stale'
        for i in scoped(s,Improvement,wid):
            if i.snapshot_id==prev.id: i.status='stale'
        invalidate(s,wid)
    return snapshot

