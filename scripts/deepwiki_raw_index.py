"""Versioned raw-text index extension. No repository code execution or answer generation.

Installed into the sidecar; pure Index is also exercised with an offline embedder.
"""
import hashlib
import json
import math
import os
import re
import threading
from pathlib import Path, PurePosixPath

VERSION='raw-code-v2'
_lock=threading.RLock()

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def text_hash(text): return hashlib.sha256(text.encode()).hexdigest()

def safe_path(path):
    p=PurePosixPath(path)
    return bool(path) and not p.is_absolute() and '\\' not in path and ':' not in path and all(x not in ('.','..','.git') and not x.lower().startswith('.env') for x in p.parts) and p.suffix.lower() not in ('.pem','.key')

def publish(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.'+os.urandom(8).hex()+'.tmp')
    try:tmp.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8');tmp.replace(path)
    finally:tmp.unlink(missing_ok=True)

class Index:
    """Immutable manifests; reusable vectors keyed by full embedding input + config.

    Similarity is normalized dot product (cosine), descending. Never a confidence.
    """
    def __init__(self,root,fingerprint,embed,splitter_version=VERSION,splitter=None,ranker=None):
        self.root=Path(root);self.fingerprint=fingerprint;self.embed=embed;self.splitter_version=splitter_version;self.splitter=splitter;self.ranker=ranker

    def vectors(self,texts,usage,kind):
        rows=[]
        for text in texts:
            key=digest([self.fingerprint,text]);path=self.root/'vectors'/(key+'.json')
            if path.exists():
                row=json.loads(path.read_text(encoding='utf-8'))
                if row['key']!=key:raise ValueError('vector_cache_corrupt')
                vector=row['vector'];usage[kind+'_cache_hits']+=1
                if not vector or not all(isinstance(v,(float,int)) and math.isfinite(v) for v in vector) or not sum(v*v for v in vector):raise ValueError('vector_cache_corrupt')
            else:
                vector=self.embed(text);usage[kind+'_calls']+=1
                if not vector or not all(isinstance(v,(float,int)) and math.isfinite(v) for v in vector) or not sum(v*v for v in vector):raise ValueError('invalid_embedding')
                publish(path,{'key':key,'vector':vector})
            rows.append(vector)
        if rows and len({len(v) for v in rows})!=1:raise ValueError('embedding_dimension_mismatch')
        return rows

    @staticmethod
    def usage():return {'code_calls':0,'query_calls':0,'code_cache_hits':0,'query_cache_hits':0,'reported_tokens':None}

    def binding(self,repo,revision):return self.root/'bindings'/(digest([repo,revision,self.fingerprint,self.splitter_version])+'.json')

    def find(self,repo,revision):
        path=self.binding(repo,revision)
        if not path.exists():return None
        ident=json.loads(path.read_text(encoding='utf-8'))['index_id'];manifest=self.load(ident)
        if (manifest['repo_identity'],manifest['indexed_revision'])!=(repo,revision):raise ValueError('binding_corrupt')
        return manifest

    def prepare(self,repo,revision,files,max_new_vectors=0,seed=(),unread_paths=()):
        """Explicit preparation only. Caller supplies verified immutable file text.

        seed contains raw sidecar chunks with matching embedding fingerprint, never answers.
        """
        with _lock:
            if len(files)>20000:raise ValueError('file_budget')
            manifest_files={p:text_hash(t) for p,t in files.items()}
            identity={'repo_identity':repo,'indexed_revision':revision,'embedding_fingerprint':self.fingerprint,'splitter_version':self.splitter_version,'files':manifest_files}
            ident=digest(identity);path=self.root/'manifests'/(ident+'.json');usage=self.usage()
            if path.exists():
                publish(self.binding(repo,revision),{'index_id':ident})
                return {'manifest':self.load(ident),'usage':usage,'reused':True}
            chunks=[]
            for p,text in sorted(files.items()):
                if not safe_path(p):raise ValueError('invalid_path')
                lines=text.splitlines(keepends=True)
                pieces=self.splitter(p,text) if self.splitter else [''.join(lines[start:start+120]) for start in range(0,len(lines),100)]
                cursor=0
                for part in pieces:
                    pos=text.find(part,cursor)
                    if pos<0:pos=text.find(part)
                    if pos<0 or not part:raise ValueError('splitter_not_raw_text')
                    start=text.count('\n',0,pos)+1;end=start+part.count('\n')-int(part.endswith('\n'))
                    chunks.append({'chunk_id':digest([p,pos,part]),'path':p,'start_line':start,'end_line':end,'text':part,'content_hash':text_hash(part)})
                    cursor=pos+1
            # Reuse persisted DeepWiki text/vector pairs exactly, no invented version metadata.
            for text,vector in seed:
                if vector and all(isinstance(v,(int,float)) and math.isfinite(v) for v in vector):
                    key=digest([self.fingerprint,text]);target=self.root/'vectors'/(key+'.json')
                    if not target.exists():publish(target,{'key':key,'vector':vector})
            missing=sum(not (self.root/'vectors'/(digest([self.fingerprint,c['text']])+'.json')).exists() for c in {c['content_hash']:c for c in chunks}.values())
            if missing>max_new_vectors:raise ValueError('index_embedding_budget')
            vectors=self.vectors([c['text'] for c in chunks],usage,'code')
            if not vectors:raise ValueError('empty_index')
            manifest={**identity,'index_id':ident,'dimension':len(vectors[0]),'chunks':chunks,'coverage':{'files':len(files),'chunks':len(chunks),'note':'Only supplied filtered files; not whole-repository coverage','unread_paths':list(unread_paths)}}
            publish(path,manifest)
            publish(self.binding(repo,revision),{'index_id':ident})
            return {'manifest':manifest,'usage':usage,'reused':False}

    def load(self,ident):
        if len(ident)!=64 or any(c not in '0123456789abcdef' for c in ident):raise ValueError('invalid_index_id')
        path=self.root/'manifests'/(ident+'.json')
        if not path.exists():raise ValueError('not_indexed')
        m=json.loads(path.read_text(encoding='utf-8'))
        if m['index_id']!=ident or digest({k:m[k] for k in ('repo_identity','indexed_revision','embedding_fingerprint','splitter_version','files')})!=ident:raise ValueError('manifest_corrupt')
        if m['embedding_fingerprint']!=self.fingerprint or m['splitter_version']!=self.splitter_version:raise ValueError('index_configuration_mismatch')
        for c in m['chunks']:
            if not safe_path(c['path']) or text_hash(c['text'])!=c['content_hash']:raise ValueError('chunk_corrupt')
        return m

    def search(self,ident,repo,revision,query,top_k=8):
        with _lock:
            m=self.load(ident);usage=self.usage()
            if (m['repo_identity'],m['indexed_revision'])!=(repo,revision):raise ValueError('version_mismatch')
            if not query.strip() or len(query)>1000 or not 1<=top_k<=16:raise ValueError('query_budget')
            key=digest([ident,query,top_k]);path=self.root/'queries'/(key+'.json')
            if path.exists():return {**json.loads(path.read_text(encoding='utf-8')),'usage':usage,'cached':True}
            q=self.vectors([query],usage,'query')[0]
            if len(q)!=m['dimension']:raise ValueError('embedding_dimension_mismatch')
            vectors=[]
            for c in m['chunks']:
                vpath=self.root/'vectors'/(digest([self.fingerprint,c['text']])+'.json')
                if not vpath.exists():raise ValueError('index_vector_missing')
                row=json.loads(vpath.read_text(encoding='utf-8'));v=row['vector']
                if row['key']!=digest([self.fingerprint,c['text']]) or len(v)!=len(q) or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in v) or not sum(x*x for x in v):raise ValueError('embedding_dimension_mismatch')
                vectors.append(v)
            if self.ranker:order=self.ranker(vectors,q)
            else:
                scores=[sum(a*b for a,b in zip(q,v))/(math.sqrt(sum(a*a for a in q))*math.sqrt(sum(b*b for b in v))) for v in vectors]
                order=sorted(enumerate(scores),key=lambda pair:(-pair[1],pair[0]))
            vrank={i:r for r,(i,_) in enumerate(order,1)};scores=dict(order)
            terms=set(re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*|[\u4e00-\u9fff]{2,}',query.casefold()))
            lexical=[(i,sum(t in (c['path']+' '+c['text']).casefold() for t in terms)) for i,c in enumerate(m['chunks'])]
            lexical=sorted((p for p in lexical if p[1]),key=lambda pair:(-pair[1],pair[0]))
            lrank={i:r for r,(i,_) in enumerate(lexical,1)}
            pool={i for i,_ in order[:top_k*3]}|{i for i,_ in lexical[:top_k*3]}
            fused={i:1/(60+vrank[i])+(1/(60+lrank[i]) if i in lrank else 0) for i in pool}
            selected=sorted(pool,key=lambda i:(-fused[i],vrank[i]))[:top_k]
            hits=[{**m['chunks'][i],'score':scores[i],'vector_rank':vrank[i],'lexical_rank':lrank.get(i),'fusion_score':fused[i],'rank':rank} for rank,i in enumerate(selected,1)]
            result={k:m[k] for k in ('index_id','repo_identity','indexed_revision','embedding_fingerprint','splitter_version','dimension','coverage')}
            result.update(hits=hits,score_semantics='cosine_descending',ranking_method='rrf60_vector_lexical',warnings=[],usage=usage,cached=False)
            publish(path,result);return result
