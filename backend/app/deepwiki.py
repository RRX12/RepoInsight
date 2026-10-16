"""DeepWiki-Open sidecar adapter: Wiki tasks and repository chat."""
import json
import os
import time
from urllib.parse import urlparse, quote
from pathlib import Path
import httpx
from pydantic import ValidationError
from .db import DATA
from .providers import ProviderError, repo_name, safe_path

class DeepWikiOpen:
    def __init__(self, transport=None, chat_call=None):
        base=os.getenv('DEEPWIKI_BASE_URL','').rstrip('/')
        u=urlparse(base)
        if not base: raise ProviderError('尚未配置 DeepWiki-Open。请配置 DEEPWIKI_BASE_URL 与生成/embedding模型服务后重试（GitHub链接模式无需共享源码目录）。不会用旧AST模板替代。','deepwiki_not_configured')
        if u.scheme not in ('http','https') or not u.netloc or u.username or u.password or u.query or u.fragment:
            raise ProviderError('DeepWiki-Open 服务地址配置无效','deepwiki_configuration')
        self.base=base;self.client=httpx.Client(base_url=base,timeout=30,transport=transport,follow_redirects=False)
        self.chat_call=chat_call;self.wiki_config=None;self.check_inputs=lambda:None
        self.provider=os.getenv('DEEPWIKI_PROVIDER','google')
        self.model=os.getenv('DEEPWIKI_MODEL','') or None
    def close(self): self.client.close()
    def call(self,method,path,**kwargs):
        # Only configured service endpoints; no model-provided URLs.
        for attempt in range(3):
            try: response=self.client.request(method,path,**kwargs)
            except httpx.HTTPError:
                if attempt<2: time.sleep(attempt+1);continue
                raise ProviderError('无法连接 DeepWiki-Open，请确认服务已启动、地址及共享目录配置正确','deepwiki_unavailable')
            if response.status_code in (429,502,503,504):
                delay=response.headers.get('Retry-After','1')
                seconds=int(delay) if delay.isdigit() else 1
                if attempt<2 and seconds<=5:time.sleep(max(1,seconds));continue
                raise ProviderError('DeepWiki-Open 暂不可用或限流，已有阶段保留，可稍后重试','deepwiki_rate_limited')
            if response.status_code>=400: raise ProviderError(f'DeepWiki-Open 接口返回HTTP {response.status_code}；请确认支持 /wiki/tasks 的版本','deepwiki_api_error')
            try:return response.json()
            except ValueError:raise ProviderError('DeepWiki-Open 返回格式无法解析','deepwiki_parse_error')
    def wiki_settings(self):
        from scripts.wiki_rag_contract import settings_from_env
        try:return self.wiki_config or settings_from_env()
        except ValueError as error:raise ProviderError('Wiki增强配置无效','wiki_configuration') from error
    def repo_payload(self,snapshot):
        if snapshot.metadata_json.get('source_kind')=='github_link':
            owner,repo=repo_name(snapshot.metadata_json['github_url'])
            payload={'repo_url':f'https://github.com/{owner}/{repo}','type':'github','owner':owner,'repo':repo,
                'comprehensive':True,'provider':self.provider,'model':self.model,'language':'zh'}
            settings=self.wiki_settings()
            if settings['mode']=='enhanced':
                from .source_reader import resolved
                if not resolved(snapshot.commit_sha):raise ProviderError('增强Wiki要求固定SHA','source_revision')
                payload.update(retrieval_mode='enhanced',revision=snapshot.commit_sha,workspace_id=snapshot.workspace_id,snapshot_id=snapshot.id,wiki_options=settings['budgets'])
            return payload
        if self.wiki_settings()['mode']=='enhanced':raise ProviderError('增强Wiki当前仅支持固定SHA的公开GitHub快照；上传路径继续使用legacy','wiki_configuration')
        relative=snapshot.metadata_json.get('local_relative_path')
        if not relative:raise ProviderError('请先上传仓库ZIP；架构分析不使用旧的受限GitHub快照','repository_required')
        folder=(DATA/relative).resolve()
        if not folder.is_relative_to(DATA) or not folder.is_dir():raise ProviderError('上传快照目录不存在或越界','repository_missing')
        shared=os.getenv('DEEPWIKI_SHARED_ROOT','').rstrip('/\\')
        remote_path=shared+'/'+folder.relative_to(DATA).as_posix() if shared else str(folder)
        return {'repo_url':remote_path,'type':'local','owner':snapshot.workspace_id,'repo':snapshot.id,'comprehensive':True,
            'provider':self.provider,'model':self.model,'language':'zh','excluded_dirs':['.git','node_modules','.venv','dist','build'],
            'excluded_files':['.env','.env.*','*.pem','*.key']}
    def cache(self,payload,task_id=None):
        if payload.get('retrieval_mode')=='enhanced':
            if not task_id:return None
            cached=self.call('GET','/repocareer/wiki/cache',params={'task_id':task_id})
            provenance=(cached or {}).get('provenance') or {}
            if cached and (provenance.get('task_id')!=task_id or provenance.get('mode')!='enhanced' or provenance.get('revision')!=payload['revision'] or provenance.get('workspace_id')!=payload['workspace_id'] or provenance.get('snapshot_id')!=payload['snapshot_id']):raise ProviderError('增强Wiki缓存版本或工作区身份不匹配','source_revision')
            return cached
        cached=self.call('GET','/api/wiki_cache',params={'owner':payload['owner'],'repo':payload['repo'],'repo_type':payload['type'],'language':'zh'})
        if isinstance(cached,dict) and cached:
            # Sidecar contract has no commit/ref field: never invent version binding.
            cached={**cached,'provenance':{'revision_status':'unknown' if payload['type']=='github' else 'uploaded_snapshot','cache_identity':{k:payload[k] for k in ('owner','repo','type')},'retrieved_at':time.time(),'note':'GitHub Wiki仅作定位线索；源码证据独立固定SHA'}}
        return cached
    def wiki(self,snapshot,progress,persist,cancelled,existing_task=None):
        payload=self.repo_payload(snapshot)
        self.check_inputs()
        if cancelled():raise ProviderError('已取消Wiki，未读取晚到结果','cancelled')
        # Cache is keyed by immutable uploaded snapshot and workspace, never repo display name.
        if existing_task:
            cached=self.cache(payload,existing_task)
            self.check_inputs()
            if cancelled():raise ProviderError('已取消Wiki，未读取晚到结果','cancelled')
            if cached:return cached
        result=self.call('POST','/wiki/tasks',json=payload)
        task_id=result.get('task_id')
        if not isinstance(task_id,str):raise ProviderError('DeepWiki-Open 未返回 task_id','deepwiki_parse_error')
        persist(task_id)
        auto=payload.get('retrieval_mode')=='enhanced' and payload.get('wiki_options',{}).get('index_mode')=='auto'
        timeout=int(os.getenv('DEEPWIKI_TIMEOUT_SECONDS','1200'))
        deadline=time.monotonic()+max(timeout,payload['wiki_options'].get('index_timeout',7200) if auto else timeout)
        last=None;last_index=None
        if not result.get('from_cache'):
            while time.monotonic()<deadline:
                if payload.get('retrieval_mode')=='enhanced':
                    try:
                        self.check_inputs()
                        if cancelled():raise ProviderError('已取消增强Wiki；外部计费是否停止未知','cancelled')
                    except ProviderError:
                        self.call('POST','/repocareer/wiki/tasks/'+quote(task_id,safe='')+'/cancel');raise
                elif cancelled():raise ProviderError('已取消本地等待；DeepWiki-Open服务任务可能仍在运行，下次可复用缓存','cancelled')
                status=self.call('GET','/wiki/tasks/'+quote(task_id,safe=''))
                if auto and status.get('status')=='indexing':
                    info=self.call('GET','/repocareer/wiki/progress',params={'task_id':task_id})
                    index_marker=(info.get('new_completed',0),info.get('remaining_new_vectors'),info.get('phase'))
                    if info and index_marker!=last_index:
                        progress('deepwiki_index',f"索引准备 · 缓存复用 {info.get('cached_vectors',0)} · 新向量 {info.get('new_completed',0)}/{info.get('required_new_vectors',0)} · 剩余 {info.get('remaining_new_vectors',info.get('required_new_vectors',0))}")
                        last_index=index_marker
                marker=(status.get('status'),status.get('pages_done'),status.get('pages_total'),status.get('pages_succeeded'))
                if marker!=last:
                    counts=f'{marker[0]} · 已处理页面 {marker[1] or 0}/{marker[2] or 0}'
                    if payload.get('retrieval_mode')=='enhanced':counts+=f' · 有效生成 {marker[3] or 0}（覆盖范围见各章）'
                    progress('deepwiki_wiki',counts);last=marker
                if status.get('status')=='failed':
                    detail=str(status.get('error','')).lower()
                    if detail.startswith('index_embedding_budget:'):
                        try:
                            dry=json.loads(str(status['error']).split(':',1)[1])
                            message=f"增强Wiki新向量预算不足：候选块 {int(dry['candidate_chunks'])}，缓存向量 {int(dry['cached_vectors'])}，所需新向量 {int(dry['required_new_vectors'])}。本阶段未调用embedding；请显式配置预算后重试。"
                            if dry.get('index_mode')=='auto':message=f"所需新向量 {int(dry['required_new_vectors'])} 超过自动构建安全上限 {int(dry['new_vector_limit'])}；本阶段未调用embedding，请缩小源码范围或调整统一上限。"
                        except (ValueError,TypeError,KeyError):message='增强Wiki新向量预算不足；本阶段未调用embedding，请查看sidecar dry-run报告。'
                    elif any(x in detail for x in ('git clone','git-upload-pack','connection was reset','could not connect','failed to connect','rpc failed')):
                        message='GitHub仓库下载失败（连接中断或超时）。已保存仓库链接与岗位JD；可安全重试。'
                    elif detail=='embedding_free_quota_exhausted':
                        message='Embedding服务免费额度不可用；已完成向量保留，请检查账户额度及仅免费调用设置后重试。'
                    elif any(x in detail for x in ('embedding','embedder','no valid documents')):
                        message='仓库索引/embedding失败，请检查可读取文件及向量模型；仓库链接与岗位JD已保留。'
                    else:
                        message='DeepWiki-Open Wiki生成失败，请检查模型服务及日志；仓库链接与岗位JD已保留。'
                    raise ProviderError(message,'deepwiki_generation_failed')
                if status.get('status')=='completed':break
                time.sleep(2)
            else:
                if auto:self.call('POST','/repocareer/wiki/tasks/'+quote(task_id,safe='')+'/cancel')
                raise ProviderError('分析等待超时；已完成向量保留，可安全重试继续。外部在途调用计费状态未知。' if auto else 'DeepWiki-Open 全面分析等待超时；保留任务引用，稍后安全重试','deepwiki_timeout')
        self.check_inputs()
        if cancelled():raise ProviderError('已取消Wiki，未读取晚到结果','cancelled')
        cached=self.cache(payload,task_id)
        self.check_inputs()
        if not cached or not isinstance(cached.get('generated_pages'),dict):raise ProviderError('DeepWiki-Open已完成，但没有可读取Wiki页面','deepwiki_empty')
        return cached
    def chat(self,snapshot,prompt,cancelled):
        payload=self.repo_payload(snapshot)
        for key in ('retrieval_mode','revision','workspace_id','snapshot_id','wiki_options'):payload.pop(key,None)
        payload.pop('owner');payload.pop('repo');payload.pop('comprehensive')
        payload['messages']=[{'role':'user','content':prompt,'mode':'normal'}]
        if self.chat_call:return self.chat_call(payload)
        from websockets.sync.client import connect
        url=self.base.replace('https://','wss://',1).replace('http://','ws://',1)+'/ws/chat'
        try:
            with connect(url,open_timeout=20,close_timeout=3,max_size=1024*1024,proxy=None) as ws:
                ws.send(json.dumps(payload,ensure_ascii=False));chunks=[];size=0
                deadline=time.monotonic()+int(os.getenv('DEEPWIKI_REVIEW_TIMEOUT_SECONDS','240'))
                while time.monotonic()<deadline:
                    if cancelled():raise ProviderError('已取消本地架构评审等待','cancelled')
                    try:chunk=ws.recv(timeout=1)
                    except TimeoutError:continue
                    except Exception as e:
                        from websockets.exceptions import ConnectionClosedOK
                        if isinstance(e,ConnectionClosedOK):break
                        raise
                    if not isinstance(chunk,str):raise ProviderError('DeepWiki-Open聊天返回二进制帧','deepwiki_parse_error')
                    size+=len(chunk)
                    if size>600000:raise ProviderError('DeepWiki-Open聊天输出超过预算','deepwiki_output_budget')
                    chunks.append(chunk)
                else:raise ProviderError('DeepWiki-Open架构评审超时，可稍后重试','deepwiki_timeout')
                text=''.join(chunks)
                if text.startswith('Error:') or text.startswith('Error preparing'):
                    raise ProviderError('DeepWiki-Open模型/检索失败，请检查服务配置；未生成替代建议','deepwiki_model_error')
                return text
        except ProviderError:raise
        except Exception:raise ProviderError('DeepWiki-Open聊天连接失败，请确认 /ws/chat 可用','deepwiki_unavailable')
