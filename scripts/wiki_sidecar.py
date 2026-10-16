"""Enhanced hooks for the supported DeepWiki task; legacy chat remains untouched."""
import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace
from fastapi import APIRouter,HTTPException,Request
from pydantic import Field
from api.repocareer_raw_index import Index,digest,publish
from api.repocareer_raw_routes import bound,git_files,archive_files,native_seed,Identity
from api.repocareer_wiki_chunks import StructureSplitter,tokens,PARSER_VERSION
from api.repocareer_wiki_contract import Budgets,FLOW_VERSION
from api.repocareer_wiki_rag import Chapter,TaskBudget,template,prompt_hash,Cancelled,Limit,review_tools,decode_review_calls

router=APIRouter(prefix='/repocareer/wiki')

def budgets(request):return Budgets.model_validate(request.wiki_options)
def enhanced_key(request):
    if not re.fullmatch(r'[0-9a-f]{40}',request.revision or '') or not request.workspace_id or not request.snapshot_id:raise ValueError('enhanced_requires_fixed_sha_workspace_snapshot')
    if request.type!='github' or request.repo_url.rstrip('/')!='https://github.com/'+request.owner+'/'+request.repo:raise ValueError('enhanced_github_identity')
    fields=request.model_dump(exclude={'token'});fields['wiki_options']=budgets(request).model_dump()
    from api.config import get_model_config
    cfg=get_model_config(request.provider,request.model)['model_kwargs']
    fields['resolved_model_configuration']={k:v for k,v in cfg.items() if k in ('model','temperature','top_p','max_tokens','num_ctx','context_window','max_input_tokens')}
    return 'enhanced_'+digest([fields,FLOW_VERSION,PARSER_VERSION,prompt_hash()])
def cache_root():
    from api.utils import deepwiki_root
    return Path(deepwiki_root())/'repoinsight-enhanced-wiki'
def read_cache(key,require_complete=False):
    if not re.fullmatch(r'enhanced_[0-9a-f]{64}',key):raise ValueError('invalid_enhanced_task_id')
    path=cache_root()/'completed'/(key+'.json')
    if not path.exists():return None
    stored=json.loads(path.read_text(encoding='utf-8'))
    if stored['hash']!=digest(stored['wiki']) or stored['wiki']['provenance']['task_id']!=key or stored['wiki']['provenance']['mode']!='enhanced':raise ValueError('enhanced_cache_corrupt')
    wiki=stored['wiki']
    if require_complete and any((p.get('retrieval') or {}).get('status')!='completed' for p in wiki['generated_pages'].values()):return None
    wiki['provenance']['current_usage']={'chapter_model_requests':0,'semantic_queries':0,'structure_requests':0,'reported_tokens':None}
    return wiki

class ExplicitModel:
    """Use existing stream adapters without research_chat, retrieval, or fallback."""
    def __init__(self,request):
        from api.config import get_model_config
        if request.provider!='deepseek':raise ValueError('enhanced_explicit_retry_control_requires_deepseek')
        self.request=request;self.config=dict(get_model_config(request.provider,request.model)['model_kwargs'])
        self.identity={k:v for k,v in self.config.items() if k in ('model','temperature','top_p','max_tokens','num_ctx','context_window','max_input_tokens')}
        self.input_limit=min(budgets(request).input,int(self.config.get('max_input_tokens',self.config.get('num_ctx',budgets(request).input))))
    native_review=True
    async def __call__(self,stage,prompt,max_output,before_extra_request=None):
        from api.chat import ChatStreamer
        config={**self.config,'max_tokens':max_output}
        streamer=ChatStreamer.create(provider=self.request.provider,model=self.request.model,model_config=config)
        if self.request.provider=='deepseek':streamer.client.max_retries=0
        if hasattr(streamer,'model_kwargs'):
            if self.request.provider=='ollama':streamer.model_kwargs['options']['num_predict']=max_output
            elif self.request.provider=='google':streamer.model_kwargs['generation_config']={**streamer.model_kwargs.get('generation_config',{}),'max_output_tokens':max_output}
            else:streamer.model_kwargs['max_tokens']=max_output
        elif self.request.provider!='deepseek':raise ValueError('explicit_output_limit_unsupported')
        if tokens(prompt)+512>self.input_limit:raise Limit('actual_model_input_budget')
        if stage=='coverage_review':
            tools=review_tools()
            instruction='只通过submit_review提交覆盖审查，不选择读取工具；工具选择由下一步负责。'
            if tokens(prompt+instruction+json.dumps(tools,ensure_ascii=False))+512>self.input_limit:
                await streamer.client.close()
                raise Limit('actual_model_input_budget_with_tools')
            try:
                result=await streamer.client.chat.completions.create(model=streamer.model,messages=[{'role':'user','content':prompt+'\n'+instruction}],tools=[tools[0]],tool_choice={'type':'function','function':{'name':'submit_review'}},stream=False,max_tokens=max_output,extra_body={'thinking':{'type':'disabled'}})
                calls=result.choices[0].message.tool_calls or []
                review=json.loads(decode_review_calls(calls))
                if not review['finish'] and any(g.get('status','open')=='open' for g in review['gaps']):
                    selection=prompt+'\n已提交审查：'+json.dumps(review,ensure_ascii=False)+'\n只选择最多三个注册补查工具，gap_id/question_id保持审查值；无需补查则不调用工具。'
                    if tokens(selection+json.dumps(tools[1:],ensure_ascii=False))+512>self.input_limit:raise Limit('actual_model_input_budget_with_tools')
                    if before_extra_request is None:raise Limit('tool_selection_budget_hook_required')
                    before_extra_request()
                    chosen=await streamer.client.chat.completions.create(model=streamer.model,messages=[{'role':'user','content':selection}],tools=tools[1:],tool_choice='auto',stream=False,max_tokens=max_output,extra_body={'thinking':{'type':'disabled'}})
                    calls=list(calls)+list(chosen.choices[0].message.tool_calls or [])
                return decode_review_calls(calls)
            finally:await streamer.client.close()
        response=''
        async for part in streamer.respond_stream(prompt):
            response+=part
            if tokens(response)>max_output*4:raise Limit('model_output_transport_budget')
        return response

def prepare_runtime(task):
    request=task.request;config=budgets(request);key=enhanced_key(request);frozen=digest(request.model_dump(exclude={'token'}))
    def check():
        if task.task is not None and (task.task.cancelled() or task.task.cancelling()):raise Cancelled('cancelled')
        if digest(task.request.model_dump(exclude={'token'}))!=frozen:raise Cancelled('task_input_changed')
        if enhanced_key(task.request)!=key:raise Cancelled('task_model_or_prompt_configuration_changed')
    check()
    body=Identity(repo_identity=request.owner+'/'+request.repo,snapshot_revision=request.revision)
    repo,folder,legacy_index=bound(SimpleNamespace(client=SimpleNamespace(host='127.0.0.1')),body)
    try:files,omitted=git_files(folder,request.revision)
    except (OSError,__import__('subprocess').SubprocessError):files,omitted=archive_files(body.repo_identity,request.revision)
    # Honor existing filters consistently for planning, indexing, retrieval and references.
    from fnmatch import fnmatch
    def included(path):
        directories=Path(path).parts[:-1]
        return not any(d in request.excluded_dirs for d in directories) and not any(fnmatch(path,p) or fnmatch(Path(path).name,p) for p in request.excluded_files) and (not request.included_dirs or any(d in request.included_dirs for d in directories)) and (not request.included_files or any(fnmatch(path,p) for p in request.included_files))
    omitted+= [p for p in files if not included(p)];files={p:t for p,t in files.items() if included(p)}
    splitter=StructureSplitter(config.chunk_target,config.chunk_max,config.chunk_overlap)
    index=Index(legacy_index.root,legacy_index.fingerprint,legacy_index.embed,splitter.version,splitter,legacy_index.ranker)
    seed=native_seed(repo,index);dry=index.dry_run(body.repo_identity,request.revision,files,seed)
    limit=config.auto_vector_limit if config.index_mode=='auto' else config.max_new_vectors
    dry.update(index_mode=config.index_mode,new_vector_limit=limit)
    state=SimpleNamespace(index_progress=dry);task.enhanced_state=state
    def on_progress(row):
        state.index_progress={**row,'index_mode':config.index_mode,'new_vector_limit':limit}
        publish(cache_root()/'index-progress'/(key+'.json'),state.index_progress)
    check()
    on_progress({**dry,'phase':'dry_run','new_completed':0,'remaining_new_vectors':dry['required_new_vectors']})
    if dry['required_new_vectors']>limit:raise ValueError('index_embedding_budget:'+json.dumps(dry))
    model=ExplicitModel(request)  # Validate adapter before any paid vector creation.
    # Guard each embedding call, not just the initial preparation.
    original=index.embed
    def checked_embed(text):
        from api.config import get_embedder_config
        cfg=get_embedder_config()
        current=digest({'model_kwargs':cfg.get('model_kwargs'),'client_class':cfg.get('client_class'),'base_url':cfg.get('initialize_kwargs',{}).get('base_url')})
        if current!=index.fingerprint:raise Cancelled('embedding_configuration_changed')
        check();vector=original(text);check();return vector
    index.embed=checked_embed
    prepared=index.prepare(body.repo_identity,request.revision,files,limit,seed,unread_paths=omitted,concurrency=config.index_concurrency if config.index_mode=='auto' else 1,batch_size=config.index_batch_size,check=check,progress=on_progress)
    check()
    publish(index.root/'wiki-ready'/(digest([body.repo_identity,request.revision,index.fingerprint])+'.json'),{'index_id':prepared['manifest']['index_id']})
    return SimpleNamespace(files=files,index=index,manifest=prepared['manifest'],model=model,config=config,task_budget=TaskBudget(config),identity=digest([key,model.identity,prepared['manifest']['index_id']]),check=check,index_usage=prepared['usage'],dry_run=dry,structure_calls=[],index_progress=state.index_progress)

async def determine_structure(task):
    from api.services.wiki.prompts import build_structure_prompt
    from api.services.wiki.structure import parse_wiki_structure
    state=task.enhanced_state;request=task.request;state.check()
    paths=[];size=0
    for path in sorted(state.files):
        if size+tokens(path)+1>2000:break
        paths.append(path);size+=tokens(path)+1
    tree='\n'.join(paths);readme=next((t for p,t in state.files.items() if p.lower()=='readme.md'),'')
    # README is a bounded planning clue, never a source fact.
    readme_bytes=tokens(readme);readme=readme.encode('utf-8')[:2000].decode('utf-8','ignore')
    state.planning_coverage={'file_paths_supplied':len(paths),'file_paths_omitted':len(state.files)-len(paths),'readme_bytes_supplied':tokens(readme),'readme_bytes_omitted':readme_bytes-tokens(readme)}
    tree+='\n[未提供目录项数量：'+str(len(state.files)-len(paths))+']'
    base=template('structure_plan')+'\n'+build_structure_prompt(request.owner,request.repo,tree,readme,request.comprehensive,request.language)
    last=None
    for attempt in range(state.config.structure_models):
        state.check();state.task_budget.spend('structure')
        prompt=base+ ('\n修复目录格式或页数：'+str(last)[:300] if last else '')
        if tokens(prompt)+512>min(state.config.input,state.model.input_limit):raise Limit('structure_input_budget')
        state.structure_calls.append({'stage':'structure_plan','input_hash':digest(prompt),'input_estimate':tokens(prompt)+512,'output_limit':state.config.output,'planning_coverage':state.planning_coverage,'usage':None})
        text=await state.model('structure_plan',prompt,state.config.output);state.check()
        try:
            structure=parse_wiki_structure(text,comprehensive=request.comprehensive)
            if len(structure.pages)>state.config.page_limit or not structure.pages or len({p.id for p in structure.pages})!=len(structure.pages):raise ValueError('wiki_page_limit_or_identity')
            return structure
        except ValueError as error:last=error
    raise ValueError('structure_plan_failed:'+str(last))

async def generate_page(task,page):
    state=task.enhanced_state
    chapter=Chapter(task.request.owner+'/'+task.request.repo,task.request.revision,state.files,state.index,state.manifest,state.model,cache_root(),state.identity,state.config,state.task_budget,state.check)
    result=await chapter.generate(page.model_dump())
    from api.schemas import WikiPage
    state.check();return WikiPage.model_validate(result)

async def save(task,pages):
    from api.schemas import WikiCacheData,RepoInfo
    state=task.enhanced_state;state.check()
    data=WikiCacheData(wiki_structure=task.wiki_structure,generated_pages=pages,repo=RepoInfo(owner=task.request.owner,repo=task.request.repo,type='github',token=None,repoUrl=task.request.repo_url),provider=task.request.provider,model=task.request.model,provenance={'mode':'enhanced','revision_status':'resolved','revision':task.request.revision,'flow_version':FLOW_VERSION,'task_id':task.repo_key,'index_id':state.manifest['index_id'],'workspace_id':task.request.workspace_id,'snapshot_id':task.request.snapshot_id,'budgets':state.config.model_dump(),'dry_run':state.dry_run,'index_usage':state.index_usage,'structure_requests':state.structure_calls,'task_usage':{'chapter_model_requests':state.task_budget.model_dispatches,'chapter_model_attempts':state.task_budget.models,'semantic_queries':state.task_budget.semantic,'structure_requests':len(state.structure_calls),'structure_attempts':state.task_budget.structure,'reported_tokens':None}}).model_dump()
    state.check();publish(cache_root()/'completed'/(task.repo_key+'.json'),{'wiki':data,'hash':digest(data)})
    state.check()

async def generate(task,pages_function,save_function):
    from api.schemas import TaskStatus
    try:
        task.status=TaskStatus.INDEXING
        task.enhanced_state=await asyncio.to_thread(prepare_runtime,task)
        task.status=TaskStatus.DETERMINING_STRUCTURE
        task.default_branch=task.request.revision
        task.wiki_structure=await determine_structure(task)
        task.status=TaskStatus.GENERATING
        pages=await pages_function(task,task.wiki_structure)
        task.enhanced_state.check();await save_function(task,pages);task.enhanced_state.check()
        task.status=TaskStatus.COMPLETED
    except asyncio.CancelledError:task.status=TaskStatus.FAILED;task.error='cancelled: upstream billing status unknown'
    except Exception as error:task.status=TaskStatus.FAILED;task.error=str(error)

def loopback(request):
    if request.client is None or request.client.host not in ('127.0.0.1','::1','testclient'):raise HTTPException(403,'loopback_only')
@router.get('/progress')
def index_progress(request:Request,task_id:str):
    loopback(request)
    if not re.fullmatch(r'enhanced_[0-9a-f]{64}',task_id):raise HTTPException(409,'invalid_enhanced_task_id')
    from api.services.wiki.tasks import registry
    task=registry.get(task_id)
    if task and task.enhanced_state:return getattr(task.enhanced_state,'index_progress',{})
    path=cache_root()/'index-progress'/(task_id+'.json')
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
@router.get('/cache')
def cache(request:Request,task_id:str):
    loopback(request)
    try:return read_cache(task_id)
    except ValueError as error:raise HTTPException(409,str(error))
@router.post('/tasks/{task_id}/cancel')
async def cancel(request:Request,task_id:str):
    loopback(request)
    from api.services.wiki.tasks import registry
    task=registry.get(task_id)
    if task is None:return {'cancelled':False,'reason':'not_active'}
    if task.request.retrieval_mode!='enhanced':raise HTTPException(409,'enhanced_task_required')
    if task.task and not task.task.done():task.task.cancel()
    return {'cancelled':True,'billing_stop':'unknown'}
