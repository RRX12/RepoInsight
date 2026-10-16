"""Inspect structural vector migration at a fixed local Git SHA; no network or embedding.
Run with the sidecar Python after installing its locked dependencies.
Does not require installing the Wiki hooks, change .env, or modify any index.
"""
import argparse,importlib.util,json,os,re,sys
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sidecar',type=Path,required=True);p.add_argument('--repo',required=True);p.add_argument('--revision',required=True);p.add_argument('--source',type=Path,help='Explicit existing local Git checkout; reads objects only')
    args=p.parse_args();sys.path.insert(0,str(args.sidecar.resolve()));sys.path.insert(1,str(ROOT))
    os.environ['DEEPWIKI_CONFIG_DIR']=str(args.sidecar.resolve()/'api/config')
    from scripts.deepwiki_raw_index import Index
    from scripts.wiki_chunks import StructureSplitter
    for name in ('index','routes'):
        spec=importlib.util.spec_from_file_location('api.repocareer_raw_'+name,ROOT/'scripts'/('deepwiki_raw_'+name+'.py'));module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    from api.repocareer_raw_routes import Identity,bound,git_files,native_seed
    body=Identity(repo_identity=args.repo,snapshot_revision=args.revision)
    if not re.fullmatch('[0-9a-f]{40}',args.revision):raise ValueError('fixed_git_SHA_required')
    repo,folder,native=bound(SimpleNamespace(client=SimpleNamespace(host='127.0.0.1')),body)
    files,omitted=git_files(args.source.resolve() if args.source else folder,args.revision)
    split=StructureSplitter();index=Index(native.root,native.fingerprint,lambda text:(_ for _ in ()).throw(AssertionError('dry-run must not embed')),split.version,split)
    print(json.dumps({'repo':args.repo,'revision':args.revision,'embedding_fingerprint':native.fingerprint,'splitter_version':split.version,'unread_paths':omitted,**index.dry_run(args.repo,args.revision,files,native_seed(repo,index))},ensure_ascii=False))
if __name__=='__main__':main()
