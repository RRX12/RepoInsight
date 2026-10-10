from pathlib import Path
import json
root=Path(__file__).resolve().parents[1]
side=root/'data/deepwiki-open'
p=side/'api/config/generator.json'
d=json.loads(p.read_text(encoding='utf-8'));d['providers']['ollama']['default_model']='qwen2.5:3b';d['providers']['ollama']['models']['qwen2.5:3b']={'options':{'temperature':0.2,'num_gpu':0,'num_ctx':8192}};p.write_text(json.dumps(d,indent=2),encoding='utf-8')
p=side/'api/config/embedder.json';d=json.loads(p.read_text(encoding='utf-8'));d['embedder_ollama']['model_kwargs']={'model':'nomic-embed-text:latest','options':{'num_gpu':0}};p.write_text(json.dumps(d,indent=2),encoding='utf-8')
# Upstream flattened Ollama options into unsupported chat kwargs. Preserve nesting.
p=side/'api/config.py';s=p.read_text(encoding='utf-8');s=s.replace('result["model_kwargs"] = {"model": model, **model_params["options"]}','result["model_kwargs"] = {"model": model, "options": model_params["options"]}');p.write_text(s,encoding='utf-8')
(side/'.env').write_text('OLLAMA_HOST=http://127.0.0.1:11434\nDEEPWIKI_EMBEDDER_TYPE=ollama\nNODE_ENV=production\nDEEPWIKI_MAX_CONCURRENT_WIKI_TASKS=1\nDEEPWIKI_WIKI_PAGE_CONCURRENCY=1\nDEEPWIKI_MAX_CONCURRENT_RAG=1\n',encoding='utf-8')
print('DeepWiki configured for local Ollama, CPU generation and embeddings')

