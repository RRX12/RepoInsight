"""External source/retrieval fixtures, no pipeline stages are mocked."""
from backend.app.source_reader import SourceEvidence,sha256
from backend.app.code_retrieval import Hit
SHA='a'*40
TEXT='角色记忆按版本更新，过期更新被拒绝。'
class Reader:
    def __init__(self,*args,**kwargs):self.trace=[];self.reads=[]
    def close(self):pass
    def list_tree(self,*args):return {'paths':['README.md','memory.ts','caller.ts'],'truncated':False}
    def read_source(self,repo,sha,path,line_range=None):
        self.reads.append((path,line_range))
        return SourceEvidence(id='source:readme' if path=='README.md' else 'source:memory',kind='code',repo=repo,commit_sha=sha,path=path,start_line=1,end_line=1,content_hash=sha256(TEXT),excerpt=TEXT,revision_status='resolved')
    def search_ranges(self,repo,sha,path,terms):return [self.read_source(repo,sha,path)]
class Retriever:
    def __init__(self,*args,**kwargs):self.trace=[];self.calls=0
    def close(self):pass
    def prepare(self,repo,revision,*args):return {'index_id':'f'*64,'repo_identity':repo,'indexed_revision':revision,'embedding_fingerprint':'fixture','splitter_version':'fixture','dimension':2}
    def search(self,manifest,query,top_k=8):
        self.calls+=1
        return [Hit(chunk_id='m',path='memory.ts',start_line=1,end_line=1,text=TEXT,content_hash=sha256(TEXT),rank=1,score=.8)]
    def reread(self,reader,manifest,hit):return reader.read_source(manifest['repo_identity'],manifest['indexed_revision'],hit.path,(hit.start_line,hit.end_line))
