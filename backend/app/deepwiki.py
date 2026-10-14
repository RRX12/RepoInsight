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
        self.chat_call=chat_call
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
    def repo_payload(self,snapshot):
        if snapshot.metadata_json.get('source_kind')=='github_link':
            owner,repo=repo_name(snapshot.metadata_json['github_url'])
            return {'repo_url':f'https://github.com/{owner}/{repo}','type':'github','owner':owner,'repo':repo,
                'comprehensive':True,'provider':self.provider,'model':self.model,'language':'zh'}
        relative=snapshot.metadata_json.get('local_relative_path')
        if not relative:raise ProviderError('请先上传仓库ZIP；架构分析不使用旧的受限GitHub快照','repository_required')
        folder=(DATA/relative).resolve()
        if not folder.is_relative_to(DATA) or not folder.is_dir():raise ProviderError('上传快照目录不存在或越界','repository_missing')
        shared=os.getenv('DEEPWIKI_SHARED_ROOT','').rstrip('/\\')
        remote_path=shared+'/'+folder.relative_to(DATA).as_posix() if shared else str(folder)
        return {'repo_url':remote_path,'type':'local','owner':snapshot.workspace_id,'repo':snapshot.id,'comprehensive':True,
            'provider':self.provider,'model':self.model,'language':'zh','excluded_dirs':['.git','node_modules','.venv','dist','build'],
            'excluded_files':['.env','.env.*','*.pem','*.key']}
    def cache(self,payload):
        cached=self.call('GET','/api/wiki_cache',params={'owner':payload['owner'],'repo':payload['repo'],'repo_type':payload['type'],'language':'zh'})
        if isinstance(cached,dict) and cached:
            # Sidecar contract has no commit/ref field: never invent version binding.
            cached={**cached,'provenance':{'revision_status':'unknown' if payload['type']=='github' else 'uploaded_snapshot','cache_identity':{k:payload[k] for k in ('owner','repo','type')},'retrieved_at':time.time(),'note':'GitHub Wiki仅作定位线索；源码证据独立固定SHA'}}
        return cached
    def wiki(self,snapshot,progress,persist,cancelled,existing_task=None):
        payload=self.repo_payload(snapshot)
        # Cache is keyed by immutable uploaded snapshot and workspace, never repo display name.
        if existing_task:
            cached=self.cache(payload)
            if cached:return cached
        result=self.call('POST','/wiki/tasks',json=payload)
        task_id=result.get('task_id')
        if not isinstance(task_id,str):raise ProviderError('DeepWiki-Open 未返回 task_id','deepwiki_parse_error')
        persist(task_id)
        deadline=time.monotonic()+int(os.getenv('DEEPWIKI_TIMEOUT_SECONDS','1200'))
        last=None
        if not result.get('from_cache'):
            while time.monotonic()<deadline:
                if cancelled():raise ProviderError('已取消本地等待；DeepWiki-Open服务任务可能仍在运行，下次可复用缓存','cancelled')
                status=self.call('GET','/wiki/tasks/'+quote(task_id,safe=''))
                marker=(status.get('status'),status.get('pages_done'),status.get('pages_total'))
                if marker!=last:
                    progress('deepwiki_wiki',f'{marker[0]} · 页面 {marker[1] or 0}/{marker[2] or 0}');last=marker
                if status.get('status')=='failed':
                    detail=str(status.get('error','')).lower()
                    if any(x in detail for x in ('git clone','git-upload-pack','connection was reset','could not connect','failed to connect','rpc failed')):
                        message='GitHub仓库下载失败（连接中断或超时）。已保存仓库链接与岗位JD；可安全重试。'
                    elif any(x in detail for x in ('embedding','embedder','no valid documents')):
                        message='仓库索引/embedding失败，请检查可读取文件及向量模型；仓库链接与岗位JD已保留。'
                    else:
                        message='DeepWiki-Open Wiki生成失败，请检查模型服务及日志；仓库链接与岗位JD已保留。'
                    raise ProviderError(message,'deepwiki_generation_failed')
                if status.get('status')=='completed':break
                time.sleep(2)
            else:raise ProviderError('DeepWiki-Open 全面分析等待超时；保留任务引用，稍后安全重试','deepwiki_timeout')
        cached=self.cache(payload)
        if not cached or not isinstance(cached.get('generated_pages'),dict):raise ProviderError('DeepWiki-Open已完成，但没有可读取Wiki页面','deepwiki_empty')
        return cached
    def chat(self,snapshot,prompt,cancelled):
        payload=self.repo_payload(snapshot);payload.pop('owner');payload.pop('repo');payload.pop('comprehensive')
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
