"""Versioned raw-text index extension. No repository code execution or answer generation.

Installed into the sidecar; pure Index is also exercised with an offline embedder.
"""
import hashlib
import json
import math
import os
import re
import threading
from weakref import WeakValueDictionary
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path, PurePosixPath

VERSION='raw-code-v2'
_lock=threading.RLock()
_vector_locks=WeakValueDictionary()
_vector_guard=threading.Lock()

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

    def vectors(self,texts,usage,kind,check=None):
        rows=[]
        for text in texts:
            key=digest([self.fingerprint,text])
            with _vector_guard:
                guard=_vector_locks.get(key)
                if guard is None:guard=threading.Lock();_vector_locks[key]=guard
            with guard:
                rows.extend(self._vectors([text],usage,kind,check or (lambda:None)))
        if rows and len({len(v) for v in rows})!=1:raise ValueError('embedding_dimension_mismatch')
        return rows

    def _vectors(self,texts,usage,kind,check):
        rows=[]
        for text in texts:
            key=digest([self.fingerprint,text]);path=self.root/'vectors'/(key+'.json')
            if path.exists():
                row=json.loads(path.read_text(encoding='utf-8'))
                if row['key']!=key:raise ValueError('vector_cache_corrupt')
                vector=row['vector'];usage[kind+'_cache_hits']+=1
                if not vector or not all(isinstance(v,(float,int)) and math.isfinite(v) for v in vector) or not sum(v*v for v in vector):raise ValueError('vector_cache_corrupt')
            else:
                check();vector=self.embed(text);usage[kind+'_calls']+=1;check()
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

    def chunks(self,repo,revision,files):
        chunks=[]
        for path,text in sorted(files.items()):
            if not safe_path(path):raise ValueError('invalid_path')
            lines=text.splitlines(keepends=True)
            pieces=self.splitter(path,text) if self.splitter else [''.join(lines[start:start+120]) for start in range(0,len(lines),100)]
            cursor=0
            for part in pieces:
                if isinstance(part,dict):
                    row=dict(part);start=row['start_byte'];end=row['end_byte']
                    if text.encode('utf-8')[start:end].decode('utf-8')!=row['text']:raise ValueError('splitter_not_raw_text')
                    row.update(path=path,repo_identity=repo,revision=revision,file_hash=text_hash(text))
                    row['chunk_id']=digest([repo,revision,path,start,end,self.splitter_version,row['content_hash']])
                else:
                    pos=text.find(part,cursor)
                    if pos<0:pos=text.find(part)
                    if pos<0 or not part:raise ValueError('splitter_not_raw_text')
                    start=text.count('\n',0,pos)+1;end=start+part.count('\n')-int(part.endswith('\n'))
                    row={'chunk_id':digest([path,pos,part]),'path':path,'start_line':start,'end_line':end,'text':part,'content_hash':text_hash(part)}
                    cursor=pos+1
                chunks.append(row)
        return chunks

    def dry_run(self,repo,revision,files,seed=()):
        chunks=self.chunks(repo,revision,files)
        inputs={c.get('embedding_text',c['text']) for c in chunks}
        seeded={text for text,vector in seed if vector and all(isinstance(v,(int,float)) and math.isfinite(v) for v in vector) and sum(v*v for v in vector)}
        hits=sum(text in seeded or (self.root/'vectors'/(digest([self.fingerprint,text])+'.json')).exists() for text in inputs)
        return {'candidate_chunks':len(chunks),'unique_embedding_inputs':len(inputs),'cached_vectors':hits,'required_new_vectors':len(inputs)-hits,'embedding_calls':0}

    def build_vectors(self,texts,usage,concurrency,batch_size,check,progress,assessment):
        """Bounded windows of independent singleton API calls, not an unverified batch API."""
        unique=list(dict.fromkeys(texts));results={};stopped=threading.Event()
        def emit(status):
            progress({**assessment,'embedding_calls':None,'dry_run_embedding_calls':0,'phase':status,'completed_inputs':len(results),'new_completed':usage['code_calls'],'remaining_new_vectors':max(0,assessment['required_new_vectors']-usage['code_calls']),'concurrency':concurrency,'batch_size':batch_size})
        def work(text):
            check()
            if stopped.is_set():raise ValueError('index_build_stopped')
            local=self.usage()
            try:
                vector=self.vectors([text],local,'code',check)[0];check();return text,vector,local
            except BaseException:stopped.set();raise
        emit('building')
        try:
            with ThreadPoolExecutor(max_workers=concurrency,thread_name_prefix='wiki-vectors') as pool:
                pending=[]
                try:
                    for start in range(0,len(unique),batch_size):
                        check()
                        pending=[pool.submit(work,t) for t in unique[start:start+batch_size]]
                        for completed in as_completed(pending):
                            text,vector,local=completed.result()
                            check();results[text]=vector
                            usage['code_calls']+=local['code_calls'];usage['code_cache_hits']+=local['code_cache_hits'];emit('building')
                except BaseException:
                    stopped.set()
                    for future in pending:future.cancel()
                    raise
            check()
            if results and len({len(v) for v in results.values()})!=1:raise ValueError('embedding_dimension_mismatch')
            emit('completed');return [results[t] for t in texts]
        except BaseException:
            stopped.set()
            cached=sum((self.root/'vectors'/(digest([self.fingerprint,t])+'.json')).exists() for t in unique)
            progress({**assessment,'embedding_calls':None,'dry_run_embedding_calls':0,'phase':'stopped','new_completed':max(0,cached-assessment['cached_vectors']),'remaining_new_vectors':len(unique)-cached,'concurrency':concurrency,'batch_size':batch_size,'usage_status':'partial_requests_unknown'})
            raise

    def prepare(self,repo,revision,files,max_new_vectors=0,seed=(),unread_paths=(),dry_run=False,*,concurrency=1,batch_size=32,check=None,progress=None):
        with _lock:
            check=check or (lambda:None);progress=progress or (lambda row:None);check()
            if not 1<=concurrency<=8 or not 1<=batch_size<=128:raise ValueError('index_execution_limits')
            if len(files)>20000:raise ValueError('file_budget')
            manifest_files={p:text_hash(t) for p,t in files.items()}
            identity={'repo_identity':repo,'indexed_revision':revision,'embedding_fingerprint':self.fingerprint,'splitter_version':self.splitter_version,'files':manifest_files}
            ident=digest(identity);path=self.root/'manifests'/(ident+'.json');usage=self.usage()
            seed=list(seed);assessment=self.dry_run(repo,revision,files,seed)
            progress({**assessment,'phase':'dry_run','new_completed':0,'remaining_new_vectors':assessment['required_new_vectors']})
            if dry_run:return {'dry_run':assessment,'usage':usage,'index_id':ident}
            if assessment['required_new_vectors']>max_new_vectors:
                error=ValueError('index_embedding_budget');error.dry_run=assessment;raise error
            chunks=self.chunks(repo,revision,files)
            for text,vector in seed:
                if vector and all(isinstance(v,(int,float)) and math.isfinite(v) for v in vector) and sum(v*v for v in vector):
                    key=digest([self.fingerprint,text]);target=self.root/'vectors'/(key+'.json')
                    if not target.exists():publish(target,{'key':key,'vector':vector})
            if path.exists():
                manifest=self.load(ident)
                # A surviving manifest is not proof that its vector cache survived.
                inputs=[c.get('embedding_text',c['text']) for c in manifest['chunks']]
                if any(not (self.root/'vectors'/(digest([self.fingerprint,t])+'.json')).exists() for t in inputs):self.build_vectors(inputs,usage,concurrency,batch_size,check,progress,assessment)
                else:progress({**assessment,'phase':'reused','new_completed':0,'remaining_new_vectors':0})
                check()
                publish(self.binding(repo,revision),{'index_id':ident})
                return {'manifest':manifest,'usage':usage,'reused':True,'dry_run':assessment}
            vectors=self.build_vectors([c.get('embedding_text',c['text']) for c in chunks],usage,concurrency,batch_size,check,progress,assessment)
            if not vectors:raise ValueError('empty_index')
            for c in chunks:
                if 'start_byte' in c:c['index_id']=ident
            manifest={**identity,'index_id':ident,'dimension':len(vectors[0]),'chunks':chunks,'coverage':{'files':len(files),'chunks':len(chunks),'note':'Only supplied filtered files; not whole-repository coverage','unread_paths':list(unread_paths)}}
            check();publish(path,manifest);check();publish(self.binding(repo,revision),{'index_id':ident})
            return {'manifest':manifest,'usage':usage,'reused':False,'dry_run':assessment}

    def exact(self,ident,repo,revision,query,path=None,top_k=8):
        m=self.load(ident)
        if (m['repo_identity'],m['indexed_revision'])!=(repo,revision):raise ValueError('version_mismatch')
        if not query or len(query)>300 or not 1<=top_k<=12:raise ValueError('query_budget')
        hits=[c for c in m['chunks'] if (path is None or c['path']==path) and (query in c['text'] or query in c.get('qualified_name',''))]
        return [{**c,'rank':i,'channel':'exact'} for i,c in enumerate(hits[:top_k],1)]

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

    def search(self,ident,repo,revision,query,top_k=8,channel_k=None):
        with _lock:
            m=self.load(ident);usage=self.usage()
            if (m['repo_identity'],m['indexed_revision'])!=(repo,revision):raise ValueError('version_mismatch')
            if not query.strip() or len(query)>1000 or not 1<=top_k<=16:raise ValueError('query_budget')
            key=digest([ident,query,top_k] if channel_k is None else [ident,query,top_k,channel_k]);path=self.root/'queries'/(key+'.json')
            if path.exists():return {**json.loads(path.read_text(encoding='utf-8')),'usage':usage,'cached':True}
            q=self.vectors([query],usage,'query')[0]
            if len(q)!=m['dimension']:raise ValueError('embedding_dimension_mismatch')
            vectors=[]
            for c in m['chunks']:
                vpath=self.root/'vectors'/(digest([self.fingerprint,c.get('embedding_text',c['text'])])+'.json')
                if not vpath.exists():raise ValueError('index_vector_missing')
                row=json.loads(vpath.read_text(encoding='utf-8'));v=row['vector']
                if row['key']!=digest([self.fingerprint,c.get('embedding_text',c['text'])]) or len(v)!=len(q) or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in v) or not sum(x*x for x in v):raise ValueError('embedding_dimension_mismatch')
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
            candidate_limit=channel_k if channel_k is not None else top_k*3
            pool={i for i,_ in order[:candidate_limit]}|{i for i,_ in lexical[:candidate_limit]}
            fused={i:1/(60+vrank[i])+(1/(60+lrank[i]) if i in lrank else 0) for i in pool}
            selected=sorted(pool,key=lambda i:(-fused[i],vrank[i]))[:top_k]
            hits=[{**m['chunks'][i],'score':scores[i],'vector_rank':vrank[i],'lexical_rank':lrank.get(i),'fusion_score':fused[i],'rank':rank} for rank,i in enumerate(selected,1)]
            result={k:m[k] for k in ('index_id','repo_identity','indexed_revision','embedding_fingerprint','splitter_version','dimension','coverage')}
            result.update(hits=hits,score_semantics='cosine_descending',ranking_method='rrf60_vector_lexical',warnings=[],usage=usage,cached=False)
            publish(path,result);return result
