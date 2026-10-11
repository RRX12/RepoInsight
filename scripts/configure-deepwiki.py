"""Initialize an unconfigured local Ollama sidecar. Never overwrite an existing .env."""
from pathlib import Path
import argparse
import json

ENV = "OLLAMA_HOST=http://127.0.0.1:11434\nDEEPWIKI_EMBEDDER_TYPE=ollama\nNODE_ENV=production\nDEEPWIKI_MAX_CONCURRENT_WIKI_TASKS=1\nDEEPWIKI_WIKI_PAGE_CONCURRENCY=1\nDEEPWIKI_MAX_CONCURRENT_RAG=1\n"


def initialize(side):
    side = Path(side).resolve()
    env = side/'.env'
    if env.exists():
        raise ValueError('已有.env，拒绝初始化；现有模型、embedding和凭证配置保持不变')
    generator = side/'api/config/generator.json'
    embedder = side/'api/config/embedder.json'
    config = side/'api/config.py'
    # Validate and prepare every input before any mutation. These sources are text only.
    gen = json.loads(generator.read_text(encoding='utf-8'))
    emb = json.loads(embedder.read_text(encoding='utf-8'))
    source = config.read_text(encoding='utf-8')
    gen['providers']['ollama']['default_model']='qwen2.5:3b'
    gen['providers']['ollama']['models']['qwen2.5:3b']={'options':{'temperature':0.2,'num_gpu':0,'num_ctx':8192}}
    emb['embedder_ollama']['model_kwargs']={'model':'nomic-embed-text:latest','options':{'num_gpu':0}}
    source=source.replace('result["model_kwargs"] = {"model": model, **model_params["options"]}', 'result["model_kwargs"] = {"model": model, "options": model_params["options"]}')
    with env.open('x',encoding='utf-8') as f:f.write(ENV)
    generator.write_text(json.dumps(gen,indent=2),encoding='utf-8')
    embedder.write_text(json.dumps(emb,indent=2),encoding='utf-8')
    config.write_text(source,encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sidecar',type=Path,default=Path(__file__).resolve().parents[1]/'data/deepwiki-open')
    args=parser.parse_args()
    try:initialize(args.sidecar)
    except (ValueError,OSError,KeyError) as exc:parser.exit(1,str(exc)+'\n')
    print('Initialized local Ollama configuration; existing configurations are never overwritten')
