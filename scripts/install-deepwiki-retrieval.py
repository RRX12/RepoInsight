"""Install the raw retrieval extension without starting services or invoking models."""
import argparse
import subprocess
from pathlib import Path

BASELINE='d92819a9c9f3b99416e3580ff235fc9d3adf8b89'
MARKER='\n# RepoCareer raw retrieval extension v1\nfrom api.repocareer_raw_routes import router as repocareer_raw_router\napp.include_router(repocareer_raw_router)\n'

def install(sidecar,wiki_rag=False):
    sidecar=Path(sidecar).resolve()
    actual=subprocess.check_output(['git','-C',str(sidecar),'rev-parse','HEAD'],text=True).strip()
    if actual!=BASELINE:raise ValueError('Unsupported sidecar revision; review compatibility before installation')
    target=sidecar/'api/main.py';source=target.read_text(encoding='utf-8')
    for relative,needle in [('api/rag/pipeline.py','def get_repo_db('),('api/config.py','def get_embedder(')]:
        if needle not in (sidecar/relative).read_text(encoding='utf-8'):raise ValueError('Sidecar API incompatible')
    if MARKER not in source and '# RepoCareer raw retrieval extension' in source:raise ValueError('Unknown installed extension; not overwriting')
    for name in ('index','routes'):
        text=Path(__file__).with_name('deepwiki_raw_'+name+'.py').read_text(encoding='utf-8')
        (sidecar/'api'/('repocareer_raw_'+name+'.py')).write_text(text,encoding='utf-8')
    if MARKER not in source:
        if '# RepoCareer raw retrieval extension' in source:raise ValueError('Unknown installed extension; not overwriting')
        target.write_text(source+MARKER,encoding='utf-8')

    if wiki_rag:
        import importlib.util
        spec=importlib.util.spec_from_file_location('install_wiki_rag',Path(__file__).with_name('install_wiki_rag.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.install_enhanced(sidecar)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sidecar',type=Path,required=True)
    p.add_argument('--wiki-rag',action='store_true');args=p.parse_args();install(args.sidecar,args.wiki_rag);print('Installed; restart is a separate explicit operation. No model called.')
