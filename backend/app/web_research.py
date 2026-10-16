"""Non-generative Tavily search and public-only, DNS-pinned page reads."""
import http.client
import ipaddress
import json
import os
import socket
import ssl
import time
import re
from html import unescape
from urllib.parse import urlsplit, urljoin
import httpx
from .analysis_harness import digest

MAX_BYTES=500000

def public_url(url):
    u=urlsplit(url)
    if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or u.port not in (None,80,443):raise ValueError('unsafe_url')
    host=u.hostname.rstrip('.').lower()
    if host in ('localhost','localhost.localdomain') or host.endswith(('.local','.internal','.localhost')):raise ValueError('unsafe_url')
    try:
        if not ipaddress.ip_address(host).is_global:raise ValueError('unsafe_url')
    except ValueError as exc:
        if str(exc)=='unsafe_url':raise
    return u


def public_addresses(host,port):
    rows=socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)
    addresses=list(dict.fromkeys(r[4][0] for r in rows))
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):raise ValueError('unsafe_dns')
    return addresses

class PublicTransport(httpx.BaseTransport):
    def handle_request(self,request):
        u=public_url(str(request.url));port=u.port or (443 if u.scheme=='https' else 80)
        address=public_addresses(u.hostname,port)[0]
        # Connect the validated IP directly. TLS still verifies the original hostname.
        conn=http.client.HTTPConnection(u.hostname,port,timeout=12)
        conn.sock=socket.create_connection((address,port),timeout=12)
        if u.scheme=='https':conn.sock=ssl.create_default_context().wrap_socket(conn.sock,server_hostname=u.hostname)
        try:
            headers=dict(request.headers);headers['accept-encoding']='identity'
            conn.request(request.method,request.url.raw_path.decode(),body=request.content,headers=headers)
            response=conn.getresponse();data=response.read(MAX_BYTES+1)
            if len(data)>MAX_BYTES:raise ValueError('response_too_large')
            return httpx.Response(response.status,headers=list(response.getheaders()),content=data,request=request)
        finally:conn.close()

class WebResearch:
    def __init__(self,*,enabled=None,key=None,transport=None,cache_dir=None,check=None,refresh=False):
        self.enabled=(os.getenv('OPTIMIZATION_WEB_ENABLED','false').lower()=='true') if enabled is None else enabled
        self.key=key if key is not None else os.getenv('TAVILY_API_KEY','')
        self.client=httpx.Client(transport=transport or PublicTransport(),timeout=12,follow_redirects=False,trust_env=False)
        self.check=check or (lambda:None);self.known={};self.trace=[];self.cache_dir=cache_dir;self.refresh=refresh
    def close(self):self.client.close()
    def _cache(self,kind,value,load):
        path=self.cache_dir/(digest([kind,value])+'.json') if self.cache_dir else None
        if path and path.exists() and not self.refresh:
            stored=json.loads(path.read_text(encoding='utf-8'))
            if time.time()-stored['time']<86400:return {**stored['value'],'cached':True}
        result=load();self.check()
        if path and result['status'] in ('ok','empty'):
            path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix('.tmp');temp.write_text(json.dumps({'time':time.time(),'value':result},ensure_ascii=False),encoding='utf-8');self.check();temp.replace(path)
        return result
    def search(self,query):
        self.check();start=time.monotonic()
        if not self.enabled:return self._record('search',{'status':'disabled','hits':[]},start)
        if not self.key:return self._record('search',{'status':'not_configured','hits':[]},start)
        def load():
            with self.client.stream('POST','https://api.tavily.com/search',headers={'Authorization':'Bearer '+self.key},json={'query':query,'search_depth':'basic','topic':'general','max_results':5,'include_answer':False,'include_raw_content':'text','auto_parameters':False,'include_usage':True}) as r:
                data=self._body(r);r.raise_for_status();body=json.loads(data)
            hits=[]
            for item in body.get('results',[]):
                try:public_url(item['url'])
                except ValueError:continue
                hits.append({'title':item.get('title',''),'url':item['url'],'snippet':item.get('content',''),'raw_content':item.get('raw_content'),'source_version':item.get('published_date'),'fetched_at':time.time()})
            return {'status':'ok' if hits else 'empty','hits':hits,'usage':body.get('usage')}
        try:result=self._cache('search',query,load)
        except (httpx.HTTPError,OSError,ValueError) as e:result={'status':self._status(e),'hits':[],'usage':None}
        self.check()
        for hit in result['hits']:self.known[hit['url']]=hit
        return self._record('search',result,start)
    def _body(self,response):
        chunks=[];size=0
        for data in response.iter_bytes():
            size+=len(data)
            if size>MAX_BYTES:raise ValueError('response_too_large')
            chunks.append(data)
        return b''.join(chunks)
    def read(self,url):
        self.check();start=time.monotonic()
        if url not in self.known:return self._record('read',{'status':'not_searched'},start)
        def load():
            public_url(url);hit=self.known[url];content=hit.get('raw_content')
            if not content:
                target=url
                for _ in range(4):
                    public_url(target)
                    with self.client.stream('GET',target,headers={'Accept':'text/html,text/plain'}) as r:
                        if r.is_redirect:
                            target=urljoin(target,r.headers['location']);public_url(target);continue
                        r.raise_for_status()
                        if not any(t in r.headers.get('content-type','') for t in ('text/html','text/plain','application/xhtml')):raise ValueError('unsupported_content')
                        content=self._body(r).decode('utf-8',errors='replace');break
                else:raise ValueError('redirect_limit')
                content=re.sub(r'(?is)<(script|style|nav).*?</\1>','',content)
                content=re.sub(r'(?i)</(?:p|div|section|article|h[1-6]|li)>','\n\n',content)
                content=unescape(re.sub('<[^>]+>',' ',content))
            if not content.strip():return {'status':'empty'}
            # Whole paragraphs only; explicitly identify unread remainder.
            selected=[];size=0
            for paragraph in re.split(r'\n\s*\n',content):
                if size+len(paragraph)>12000:break
                selected.append(paragraph);size+=len(paragraph)
            if not selected:return {'status':'paragraph_too_large'}
            excerpt='\n\n'.join(selected)
            return {'status':'ok','url':url,'title':hit['title'],'excerpt':excerpt,'content_hash':digest(content),'source_version':hit.get('source_version'),'retrieved_at':hit['fetched_at'],'partial':len(excerpt)<len(content)}
        try:result=self._cache('read',url,load)
        except (httpx.HTTPError,OSError,ValueError) as e:result={'status':self._status(e)}
        self.check();return self._record('read',result,start)
    def _status(self,e):
        if isinstance(e,httpx.TimeoutException) or isinstance(e,TimeoutError):return 'timeout'
        if isinstance(e,httpx.HTTPStatusError):return 'http_'+str(e.response.status_code)
        return str(e) if isinstance(e,ValueError) else 'network_error'
    def _record(self,kind,result,start):
        self.trace.append({'tool':kind,'status':result['status'],'elapsed_seconds':round(time.monotonic()-start,3),'cached':result.get('cached',False),'usage':result.get('usage')})
        return result
