"""Official GitHub archive fallback; bounded extraction and no project execution."""
import io,re,stat,tempfile,zipfile
from pathlib import Path,PurePosixPath
from urllib.parse import urlparse
import httpx

def download_github_archive(url,target,root):
    u=urlparse(url)
    if u.scheme!='https' or u.netloc!='github.com' or u.query or u.fragment:raise ValueError('Invalid GitHub URL')
    match=re.fullmatch(r'/([A-Za-z0-9-]+)/([A-Za-z0-9_.-]+)/?',u.path)
    if not match:raise ValueError('Invalid repository URL')
    dest=Path(target).resolve();base=Path(root).resolve()
    if not dest.is_relative_to(base) or dest==base:raise ValueError('Archive destination outside repository root')
    with httpx.Client(timeout=90,follow_redirects=False) as c:
        content=bytearray()
        with c.stream('GET',f'https://codeload.github.com/{match[1]}/{match[2]}/zip/HEAD') as r:
            r.raise_for_status()
            for chunk in r.iter_bytes():
                content.extend(chunk)
                if len(content)>100*1024*1024:raise ValueError('GitHub archive exceeds 100MB')
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        entries=z.infolist()
        if len(entries)>50000 or sum(e.file_size for e in entries)>300*1024*1024:raise ValueError('Expanded archive exceeds budget')
        seen=set()
        for e in entries:
            name=e.filename.rstrip('/')
            parts=PurePosixPath(name).parts
            if not parts or name.startswith('/') or '\\' in name or ':' in name or '..' in parts or stat.S_ISLNK(e.external_attr>>16):raise ValueError('Unsafe archive path')
            for part in parts:
                if part.endswith(('.', ' ')) or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',part,re.I):raise ValueError('Unsafe Windows path')
            if name.casefold() in seen:raise ValueError('Duplicate archive path')
            seen.add(name.casefold())
        roots={PurePosixPath(e.filename).parts[0] for e in entries}
        if len(roots)!=1:raise ValueError('Archive root is ambiguous')
        dest.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=dest.parent,prefix='archive-') as tmp:
            stage=Path(tmp)/'source';stage.mkdir()
            for e in entries:
                parts=PurePosixPath(e.filename).parts[1:]
                if not parts or e.is_dir():continue
                out=stage.joinpath(*parts);out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(z.read(e))
            if dest.exists():
                if any(dest.iterdir()):raise ValueError('Existing repository directory preserved; cannot replace it')
                dest.rmdir()
            stage.rename(dest)
