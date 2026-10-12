"""Read-only, immutable-revision evidence. Imported code is never executed."""
import base64
import ast
import hashlib
import json
import re
import posixpath
from pathlib import Path
from urllib.parse import quote
from pydantic import BaseModel, Field
from .db import DATA
from .providers import GitHub, ProviderError, safe_path, repo_name

class SourceEvidence(BaseModel):
    id: str
    kind: str
    repo: str
    commit_sha: str
    path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    content_hash: str
    excerpt: str
    wiki_page_id: str | None = None
    revision_status: str

def sha256(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()
def resolved(sha):return bool(re.fullmatch(r'[0-9a-f]{40}',sha or ''))

def related_source_paths(path,excerpt,tree_paths):
    """Resolve explicit local import hints only; not a call graph or execution proof."""
    refs=re.findall(r"(?:from\s*|import\s*|require\s*\(\s*)['\"](\.[^'\"]+)['\"]",excerpt)
    matches=[]
    for ref in refs:
        base=posixpath.normpath(posixpath.join(posixpath.dirname(path),ref))
        if not safe_path(base) or base.startswith('../'):continue
        options=[base]+[base+ext for ext in ('.ts','.tsx','.js','.jsx','.py','.mjs')]+[base+'/index'+ext for ext in ('.ts','.tsx','.js')]
        if base.endswith(('.js','.jsx')):options += [base.rsplit('.',1)[0]+ext for ext in ('.ts','.tsx')]
        matches.extend(p for p in options if p in tree_paths and p!=path)
    return list(dict.fromkeys(matches))

class SourceReader:
    def __init__(self,workspace_id,snapshot=None,github=None,cache_dir=None,max_calls=32):
        self.workspace_id=workspace_id;self.snapshot=snapshot
        self.github=github or GitHub();self.github.client.timeout=8
        self.cache=Path(cache_dir or DATA/'workspaces'/workspace_id/'source-cache')
        self.max_calls=max_calls;self.calls=0;self.trace=[]
    def close(self):self.github.client.close()
    def get(self,path,**kwargs):
        if self.calls>=self.max_calls:raise ProviderError('源码工具预算耗尽','source_budget')
        self.calls+=1
        return self.github.get(path,**kwargs)
    def resolve_revision(self,repo,ref=None):
        owner,name=repo_name('https://github.com/'+repo);prefix=f'/repos/{owner}/{name}'
        try:
            branch=ref or self.get(prefix)['default_branch']
            sha=self.get(prefix+'/commits/'+quote(branch,safe=''))['sha']
            if not resolved(sha):raise ProviderError('GitHub没有返回有效提交SHA','source_revision')
            return {'commit_sha':sha,'status':'resolved','ref':branch}
        except (ProviderError,KeyError) as exc:
            return {'commit_sha':'unresolved:github','status':'unresolved','error':str(exc),'error_code':getattr(exc,'code','source_parse')}
    def _cache(self,key,load):
        path=self.cache/(sha256(key)+'.json')
        if path.is_file():
            try:return json.loads(path.read_text(encoding='utf-8'))
            except (ValueError,OSError):pass
        result=load();path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_suffix('.tmp');temp.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8');temp.replace(path)
        return result
    def _identity(self,repo,sha):
        repo_name('https://github.com/'+repo)
        if self.snapshot and repo!=self.snapshot.owner+'/'+self.snapshot.repo:raise ProviderError('源码仓库身份不匹配','source_identity')
        if self.snapshot and sha!=self.snapshot.commit_sha:raise ProviderError('源码版本不匹配','source_revision')
        if not resolved(sha) and not sha.startswith('archive-sha256:'):raise ProviderError('未解析真实SHA，不能核验源码','source_revision')
    def list_tree(self,repo,sha):
        self._identity(repo,sha)
        if sha.startswith('archive-sha256:'):
            return {'paths':list(self.snapshot.coverage['read_files']),'truncated':False}
        def load():
            tree=self.get(f'/repos/{repo}/git/trees/{sha}',params={'recursive':'1'})
            return {'paths':[x['path'] for x in tree.get('tree',[]) if x.get('type')=='blob' and x.get('mode')!='120000' and safe_path(x['path'])], 'truncated':bool(tree.get('truncated'))}
        return self._cache(repo+'|'+sha+'|tree',load)
    def read_source(self,repo,sha,path,line_range=None):
        self._identity(repo,sha)
        if not safe_path(path) or any(part=='.git' or part.lower().startswith('.env') for part in Path(path).parts) or Path(path).suffix.lower() in ('.pem','.key'):raise ProviderError('源码路径非法或敏感','source_path')
        if line_range and (line_range[0]<1 or line_range[1]<line_range[0] or line_range[1]-line_range[0]>240):raise ProviderError('源码行范围无效','source_range')
        def load():
            if sha.startswith('archive-sha256:'):
                if path not in self.snapshot.coverage['read_files']:raise ProviderError('路径不在上传快照','source_path')
                folder=(DATA/self.snapshot.metadata_json['local_relative_path']).resolve();target=(folder/path).resolve()
                if not folder.is_relative_to(DATA) or not target.is_relative_to(folder) or target.is_symlink():raise ProviderError('源码路径越界','source_path')
                raw=target.read_bytes()
            else:
                entry=self.get(f'/repos/{repo}/contents/'+quote(path,safe='/'),params={'ref':sha})
                if entry.get('type')!='file' or entry.get('size',999999)>524288 or entry.get('encoding')!='base64':raise ProviderError('源码非普通文本或超过512KB','source_size')
                raw=base64.b64decode(entry['content'])
            if len(raw)>524288 or b'\0' in raw:raise ProviderError('源码非文本或超过512KB','source_size')
            try:text=raw.decode('utf-8')
            except UnicodeDecodeError:raise ProviderError('源码编码不支持','source_encoding')
            return {'text':text,'hash':sha256(text)}
        cached=self._cache(repo+'|'+sha+'|'+path,load)
        if cached['hash']!=sha256(cached['text']):raise ProviderError('源码缓存校验失败','source_cache')
        if sha.startswith('archive-sha256:'):
            from sqlalchemy import select
            from .db import Session,Evidence
            with Session() as s:
                baseline=s.scalar(select(Evidence).where(Evidence.workspace_id==self.workspace_id,Evidence.snapshot_id==self.snapshot.id,Evidence.path==path))
                if not baseline or baseline.content_hash!=cached['hash']:raise ProviderError('上传内容与原快照哈希不一致','source_revision')
        lines=cached['text'].splitlines();start,end=line_range or (1,min(241,len(lines)))
        if start>len(lines) or end>len(lines):raise ProviderError('源码行范围超出文件','source_range')
        excerpt='\n'.join(lines[start-1:end]);key=f'{repo}|{sha}|{path}|{start}:{end}|{cached["hash"]}'
        return SourceEvidence(id='code:'+sha256(key)[:24],kind='documentation' if Path(path).suffix.lower()=='.md' else 'test_source' if re.search(r'(^|/)(tests?|__tests__)(/|$)|[._]test[._]|test_',path) else 'code',repo=repo,commit_sha=sha,path=path,start_line=start,end_line=end,content_hash=sha256(excerpt),excerpt=excerpt,revision_status='resolved' if resolved(sha) else 'content_hash_bound')
    def search_ranges(self,repo,sha,path,terms):
        """Structure-friendly windows around matches; overlap preserves nearby guards/callers."""
        self.read_source(repo,sha,path) # fills immutable full-file cache
        cached=self._cache(repo+'|'+sha+'|'+path,lambda:None);lines=cached['text'].splitlines()
        terms=list(dict.fromkeys(t.lower() for t in terms if t))
        hits=[i for i,line in enumerate(lines) if any(t in line.lower() for t in terms)]
        # Early declarations often mention every symbol but omit execution. Rank
        # bounded windows by term diversity and actual control-flow, not file order.
        windows=[]
        frequency={t:sum(t in line.lower() for line in lines) for t in terms}
        for center in hits:
            start=max(0,center-45);end=min(len(lines),center+76)
            text='\n'.join(lines[start:end]).lower()
            found={t for t in terms if t in text}
            controls=sum(bool(re.search(r'\b(if|return|throw|raise|except|catch|await|for|while)\b',line)) for line in lines[start:end])
            windows.append((start,end,found,min(controls,12)))
        ranges=[];covered=set()
        while windows and len(ranges)<3:
            best=max(windows,key=lambda w:(sum(1+1/max(1,frequency[t]) for t in w[2]-covered)+w[3]*0.5,-w[0]))
            start,end,found,_=best;ranges.append((start+1,end));covered.update(found)
            windows=[w for w in windows if max(0,min(end,w[1])-max(start,w[0]))<0.5*min(end-start,w[1]-w[0])]
        if not ranges:ranges=[(1,min(61,len(lines)))]
        if path.endswith('.py'):
            try:
                nodes=[n for n in ast.walk(ast.parse(cached['text'])) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and any(n.lineno<=i+1<=n.end_lineno for i in hits)]
                nodes.sort(key=lambda n:n.end_lineno-n.lineno)
                expanded=[]
                for start,end in ranges:
                    for n in nodes:
                        if not any(start<=i+1<=end and n.lineno<=i+1<=n.end_lineno for i in hits):continue
                        a=max(1,min(start,n.lineno-8));b=min(len(lines),max(end,n.end_lineno+8))
                        if b-a<=240:start,end=a,b
                    expanded.append((start,end))
                ranges=list(dict.fromkeys(expanded))
            except SyntaxError:pass
        self.trace.append({'stage':'source_search','path':path,'matched_lines':len(hits),'ranges':[list(r) for r in ranges],
                           'unread_matched_lines':[i+1 for i in hits if not any(a<=i+1<=b for a,b in ranges)]})
        return [self.read_source(repo,sha,path,r) for r in ranges[:3]]
