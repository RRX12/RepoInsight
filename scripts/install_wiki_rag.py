"""Reproducible, guarded Wiki hooks. Only an explicit install changes the sidecar."""
import hashlib
import json
import subprocess
from pathlib import Path

BASELINE='d92819a9c9f3b99416e3580ff235fc9d3adf8b89'
VERSION='wiki-rag-install-v1'
def sha(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()
def replace_once(text,needle,replacement):
    if text.count(needle)!=1:raise ValueError('Sidecar hook changed: '+needle[:80])
    return text.replace(needle,replacement,1)
def install_enhanced(sidecar):
    sidecar=Path(sidecar).resolve();root=Path(__file__).resolve().parents[1]
    if subprocess.check_output(['git','-C',str(sidecar),'rev-parse','HEAD'],text=True).strip()!=BASELINE:raise ValueError('Unsupported Wiki sidecar revision')
    record_path=sidecar/'api/repocareer_wiki_install.json'
    targets=['api/schemas/repo.py','api/schemas/wiki.py','api/services/wiki/tasks.py','api/chat/_stream.py','api/main.py']
    original={name:(sidecar/name).read_text(encoding='utf-8') for name in targets}
    if record_path.exists():
        record=json.loads(record_path.read_text(encoding='utf-8'))
        if record['version']!=VERSION or any(sha(original[name])!=record['patched_hashes'][name] for name in targets):raise ValueError('Installed Wiki hooks changed; review before reinstalling')
        patched=original
    else:
        if any('repoinsight_enhanced' in text for text in original.values()):raise ValueError('Untracked enhanced hook; not overwriting')
        patched=dict(original)
        text=patched['api/schemas/repo.py']
        text=replace_once(text,'    comprehensive: bool = Field(True, description="Comprehensive vs concise wiki")','''    comprehensive: bool = Field(True, description="Comprehensive vs concise wiki")
    # repoinsight_enhanced: additive request fields; legacy callers keep defaults.
    retrieval_mode: str = "legacy"
    revision: str | None = None
    workspace_id: str | None = None
    snapshot_id: str | None = None
    wiki_options: dict = Field(default_factory=dict)''')
        text=replace_once(text,'        return f"{self.type}_{self.owner}_{self.repo}"','''        if self.retrieval_mode == "enhanced":
            from api.repocareer_wiki_sidecar import enhanced_key
            return enhanced_key(self)
        if self.retrieval_mode != "legacy":
            raise ValueError("invalid_wiki_retrieval_mode")
        return f"{self.type}_{self.owner}_{self.repo}"''');patched['api/schemas/repo.py']=text
        text=patched['api/schemas/wiki.py']
        text=replace_once(text,'    relatedPages: list[str]','    relatedPages: list[str]\n    retrieval: dict | None = None  # repoinsight_enhanced')
        text=replace_once(text,'    wiki_structure: WikiStructureModel\n    generated_pages: dict[str, WikiPage]\n    repo_url:', '    provenance: dict | None = None\n    wiki_structure: WikiStructureModel\n    generated_pages: dict[str, WikiPage]\n    repo_url:')
        text=replace_once(text,'    pages_done: int = Field(default=0, ge=0)','    pages_done: int = Field(default=0, ge=0)\n    pages_succeeded: int = Field(default=0, ge=0)');patched['api/schemas/wiki.py']=text
        text=patched['api/services/wiki/tasks.py']
        text=replace_once(text,'    pages_done: int = 0','    pages_done: int = 0\n    pages_succeeded: int = 0\n    enhanced_state: Any = Field(default=None, exclude=True)  # repoinsight_enhanced')
        text=text.replace('            pages_done=self.pages_done,','            pages_done=self.pages_done,\n            pages_succeeded=self.pages_succeeded,')
        text=replace_once(text,'            if wiki_cache_exists(','            if task.request.retrieval_mode == "enhanced":\n                from api.repocareer_wiki_sidecar import read_cache\n                if read_cache(key, require_complete=True):\n                    return WikiTaskSubmitResult(task_id=key, status=TaskStatus.COMPLETED, from_cache=True)\n\n            if task.request.retrieval_mode == "legacy" and wiki_cache_exists(')
        text=replace_once(text,'    r = task.request\n    try:\n        repo = Repo', '''    r = task.request
    if r.retrieval_mode == "enhanced":
        from api.repocareer_wiki_sidecar import generate
        return await generate(task, _generate_pages, _save)
    try:
        repo = Repo''')
        text=replace_once(text,'    assert task.wiki_structure is not None','''    if task.request.retrieval_mode == "enhanced":
        from api.repocareer_wiki_sidecar import save
        return await save(task, pages)
    assert task.wiki_structure is not None''')
        text=replace_once(text,'    last_error: Exception | None = None','''    if task.request.retrieval_mode == "enhanced":
        return await _generate_page(task, page)  # shared chapter repair budget, no outer retry
    last_error: Exception | None = None''')
        text=replace_once(text,'                pages[page.id] = await _generate_page_with_retry(task, page)','                pages[page.id] = await _generate_page_with_retry(task, page)\n                task.pages_succeeded += 1')
        text=replace_once(text,'    await asyncio.gather(*(one(page) for page in structure.pages))','''    if task.request.retrieval_mode == "enhanced":
        children = [asyncio.create_task(one(page)) for page in structure.pages]
        try:
            await asyncio.gather(*children)
        except BaseException:
            for child in children:
                if not child.done(): child.cancel()
            await asyncio.gather(*children, return_exceptions=True)
            raise
    else:
        await asyncio.gather(*(one(page) for page in structure.pages))''')
        text=replace_once(text,'    file_links = "\\n".join(','    if r.retrieval_mode == "enhanced":\n        from api.repocareer_wiki_sidecar import generate_page\n        return await generate_page(task, page)\n    file_links = "\\n".join(')
        patched['api/services/wiki/tasks.py']=text
        text=patched['api/chat/_stream.py']
        # The existing local DeepSeek adapter lacks output limits. Add only when explicitly supplied.
        needle='stream=True, extra_body={"thinking":{"type":"disabled"}}'
        text=replace_once(text,needle,needle+',\n                **({"max_tokens":self.model_config["max_tokens"]} if "max_tokens" in self.model_config else {})')
        patched['api/chat/_stream.py']=text
        patched['api/main.py']+='\n# repoinsight_enhanced Wiki context extension v1\nfrom api.repocareer_wiki_sidecar import router as repoinsight_wiki_router\napp.include_router(repoinsight_wiki_router)\n'
        for name,text in patched.items():compile(text,name,'exec')
    modules={'wiki_chunks':'repocareer_wiki_chunks','wiki_rag_contract':'repocareer_wiki_contract','wiki_rag':'repocareer_wiki_rag','wiki_sidecar':'repocareer_wiki_sidecar'}
    for source,destination in modules.items():(sidecar/'api'/(destination+'.py')).write_text((root/'scripts'/(source+'.py')).read_text(encoding='utf-8'),encoding='utf-8')
    templates=sidecar/'api/repocareer_wiki_prompts';templates.mkdir(exist_ok=True)
    for p in (root/'backend/prompts/wiki').glob('*.md'):(templates/p.name).write_text(p.read_text(encoding='utf-8'),encoding='utf-8')
    if not record_path.exists():
        for name,text in patched.items():(sidecar/name).write_text(text,encoding='utf-8')
        record_path.write_text(json.dumps({'version':VERSION,'baseline':BASELINE,'original_hashes':{n:sha(t) for n,t in original.items()},'patched_hashes':{n:sha(t) for n,t in patched.items()}},indent=2),encoding='utf-8')
