"""Shared local/CI entry: offline checks, isolated build, fail on every failed step."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def run(args,cwd,env):
    print('CHECK: '+' '.join(map(str,args)),flush=True)
    subprocess.run(list(map(str,args)),cwd=cwd,env=env,check=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--e2e',action='store_true',help='Also run offline Playwright; requires installed Chromium and free 8001/5173')
    parser.add_argument('--pnpm',default='pnpm',help='pnpm executable name or absolute path')
    args=parser.parse_args()
    pnpm=shutil.which(args.pnpm)
    if not pnpm:
        print('pnpm not found; install the packageManager version or pass --pnpm. No check was skipped.',file=sys.stderr)
        return 1
    try:
        with tempfile.TemporaryDirectory(prefix='repocareer-check-') as temp:
            env={**os.environ,'REPOINSIGHT_DATA':str(Path(temp)/'data'),'REPOINSIGHT_DEMO':'true','CI':'true'}
            run([sys.executable,ROOT/'scripts/check_architecture.py'],ROOT,env)
            run([sys.executable,'-m','pytest','backend/tests','-q'],ROOT,env)
            run([pnpm,'run','typecheck'],ROOT/'frontend',env)
            run([pnpm,'run','build','--outDir',str(Path(temp)/'frontend-build')],ROOT/'frontend',env)
            if args.e2e:run([pnpm,'run','test:e2e'],ROOT/'frontend',env)
        print('All requested checks passed; production data/dist were not replaced.')
        return 0
    except (OSError,subprocess.CalledProcessError) as exc:
        print(f'Checks failed: {exc}',file=sys.stderr)
        return exc.returncode if isinstance(exc,subprocess.CalledProcessError) else 1


if __name__=='__main__':sys.exit(main())
