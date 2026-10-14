"""Raw sidecar retrieval transport; all hits are re-read at the frozen source revision."""
import os
import time
import math
from urllib.parse import urlparse
import httpx
from pydantic import BaseModel,Field,ConfigDict
from .providers import ProviderError,safe_path
from .source_reader import sha256

class Hit(BaseModel):
    model_config=ConfigDict(extra='forbid')
    chunk_id:str
    path:str
    start_line:int=Field(ge=1)
    end_line:int=Field(ge=1)
    text:str=Field(max_length=30000)
    content_hash:str
    rank:int=Field(ge=1)
    score:float
    vector_rank:int|None=None
    lexical_rank:int|None=None
    fusion_score:float|None=None

class SearchResult(BaseModel):
    index_id:str
    repo_identity:str
    indexed_revision:str
    embedding_fingerprint:str
    splitter_version:str
    dimension:int=Field(ge=1)
    ranking_method:str="unknown"
    coverage:dict
    hits:list[Hit]=Field(max_length=16)
    score_semantics:str
    warnings:list[str]=Field(default_factory=list)
    usage:dict=Field(default_factory=dict)
    cached:bool=False

class CodeRetrieval:
    def __init__(self,base=None,transport=None,check_active=None,max_queries=16):
        base=(base or os.getenv('DEEPWIKI_BASE_URL','')).rstrip('/')
        parsed=urlparse(base)
        if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:raise ProviderError('原始检索URL配置无效','index_configuration')
        if not base:raise ProviderError('原始代码检索服务未配置','index_unavailable')
        self.client=httpx.Client(base_url=base,transport=transport,timeout=60,follow_redirects=False)
        self.check_active=check_active or (lambda:None);self.max_queries=max_queries;self.calls=0;self.trace=[]
    def close(self):self.client.close()
    def request(self,path,body):
        self.check_active()
        try:
            r=self.client.post('/repocareer/code/'+path,json=body)
            self.check_active()
            if r.status_code!=200:
                try:reason=r.json().get('detail','')
                except ValueError:reason=''
                messages={'embedding_free_quota_exhausted':'Embedding 免费额度已耗尽且账户仅允许免费调用；请在模型服务控制台充值或关闭仅使用免费额度后重试','embedding_failed':'Embedding 服务调用失败，请检查模型账户额度与配置','archive_path':'源码归档含非法路径，无法准备索引','embedding_configuration_mismatch':'索引 embedding 配置与当前服务不一致','snapshot_unavailable':'无法读取目标版本源码，请检查仓库访问与网络'}
                if r.status_code==404:message='未找到原始检索接口，请安装扩展并重启 DeepWiki 服务'
                elif isinstance(reason,str) and 'budget' in reason:message='源码索引准备超出预算：'+reason+'；需检查缺失向量数量或源码读取范围后显式配置预算'
                else:message=messages.get(reason,'原始代码索引准备失败（HTTP '+str(r.status_code)+'）') if isinstance(reason,str) else '原始代码检索请求无效'
                raise ProviderError(message,'index_unavailable')
            return r.json()
        except (httpx.HTTPError,ValueError) as exc:raise ProviderError('原始代码检索连接或响应异常','index_unavailable') from exc
    def prepare(self,repo,revision,max_new_vectors=0,uploaded_files=None):
        started=time.monotonic()
        data=self.request('prepare',{'repo_identity':repo,'snapshot_revision':revision,'max_new_vectors':max_new_vectors,**({'uploaded_files':uploaded_files} if uploaded_files is not None else {})})
        m=data.get('manifest',{})
        if m.get('repo_identity')!=repo or m.get('indexed_revision')!=revision or not all(m.get(k) for k in ('index_id','embedding_fingerprint','splitter_version','dimension')):
            raise ProviderError('索引manifest身份不匹配','index_version_mismatch')
        self.trace.append({'stage':'INDEX_PREPARE','elapsed_seconds':round(time.monotonic()-started,3),'index_id':m['index_id'],'usage':data.get('usage'),'reused':data.get('reused',False),'unread_paths':data.get('unread_paths',[])})
        return m
    def search(self,manifest,query,top_k=8):
        self.check_active()
        if self.calls>=self.max_queries:raise ProviderError('原始检索查询预算耗尽','retrieval_budget')
        self.calls+=1;started=time.monotonic()
        body={'repo_identity':manifest['repo_identity'],'snapshot_revision':manifest['indexed_revision'],'index_id':manifest['index_id'],'expected_embedding_fingerprint':manifest['embedding_fingerprint'],'query':query,'top_k':top_k}
        try:result=SearchResult.model_validate(self.request('search',body))
        except ValueError as exc:raise ProviderError('原始检索返回契约无效','retrieval_contract') from exc
        for k in ('index_id','repo_identity','indexed_revision','embedding_fingerprint','splitter_version','dimension'):
            if getattr(result,k)!=manifest[k]:raise ProviderError('检索返回索引版本不匹配','index_version_mismatch')
        if len(result.hits)>top_k:raise ProviderError('检索超出top_k','retrieval_contract')
        for hit in result.hits:
            if not math.isfinite(hit.score) or not safe_path(hit.path) or hit.end_line<hit.start_line or sha256(hit.text)!=hit.content_hash:raise ProviderError('检索原文或路径校验失败','retrieval_contract')
        self.trace.append({'stage':'CODE_RETRIEVE','elapsed_seconds':round(time.monotonic()-started,3),'query':query,'index_id':result.index_id,'ranking_method':result.ranking_method,'score_semantics':result.score_semantics,'hits':[h.model_dump(exclude={'text'}) for h in result.hits],'status':'hits' if result.hits else 'empty','usage':result.usage,'cached':result.cached})
        return result.hits
    def reread(self,reader,manifest,hit):
        self.check_active()
        e=reader.read_source(manifest['repo_identity'],manifest['indexed_revision'],hit.path,(hit.start_line,hit.end_line))
        if hit.text not in e.excerpt:raise ProviderError('召回原文与目标SHA不一致，不能作为支持证据','source_revision')
        self.check_active();return e
