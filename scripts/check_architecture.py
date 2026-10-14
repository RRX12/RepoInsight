"""Two repository-specific import boundaries, using Python AST only (no app import)."""
import ast
from pathlib import Path
import sys
from importlib.util import resolve_name

CONTRACTS = {'schemas', 'architecture_schema', 'resume_contract', 'interaction_contract','discussion_contract'}
ORCHESTRATION = {'main', 'artifact_service', 'analysis', 'agent', 'memory',
                 'task_lifecycle', 'resume_writer', 'resume_quality', 'interaction_service','shared_analysis','optimization_review','discussion_service','discussion_memory','discussion_context'}
BASELINE = 'backend.app.resume_legacy'


def imports(tree, package='backend.app'):
    """Include function-local imports and literal dynamic imports; retain scope."""
    found = []
    dynamic_names={'__import__','import_module'}
    for node in ast.walk(tree):
        if isinstance(node,ast.ImportFrom) and node.module=='importlib':
            dynamic_names.update(a.asname or a.name for a in node.names if a.name=='import_module')
    class Visitor(ast.NodeVisitor):
        scope = ()
        def visit_FunctionDef(self, node):
            previous = self.scope
            self.scope += (node.name,)
            self.generic_visit(node)
            self.scope = previous
        visit_AsyncFunctionDef = visit_FunctionDef
        def visit_ClassDef(self, node):
            previous = self.scope
            self.scope += (node.name,)
            self.generic_visit(node)
            self.scope = previous
        def visit_Import(self, node):
            for alias in node.names:found.append((alias.name, '', node.lineno, self.scope))
        def visit_ImportFrom(self, node):
            module = resolve_name('.'*node.level+(node.module or ''), package) if node.level else node.module or ''
            for alias in node.names:
                target = module+'.'+alias.name if module=='backend.app' or not node.module else module
                found.append((target, alias.name, node.lineno, self.scope))
        def visit_Call(self, node):
            func = node.func
            dynamic = isinstance(func,ast.Name) and func.id in dynamic_names or isinstance(func,ast.Attribute) and func.attr=='import_module'
            if dynamic and node.args and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str):
                name=node.args[0].value
                if name.startswith('.'):name=resolve_name(name,package)
                found.append((name,'',node.lineno,self.scope))
            if isinstance(func,ast.Attribute) and func.attr=='write_legacy':
                found.append(('backend.app.resume_writer','write_legacy',node.lineno,self.scope))
            self.generic_visit(node)
    Visitor().visit(tree)
    return found


def check(root):
    app = Path(root)/'backend/app'
    paths = sorted(app.rglob('*.py'))
    if not paths:raise ValueError('No backend/app Python modules found')
    graph, errors = {}, []
    known={'.'.join(p.relative_to(app).with_suffix('').parts) for p in paths}
    for path in paths:
        name='.'.join(path.relative_to(app).with_suffix('').parts)
        package='backend.app'+('.'+name.rsplit('.',1)[0] if '.' in name else '')
        if path.name=='__init__.py':package='backend.app'+('.'+name.removesuffix('.__init__') if name!='__init__' else '')
        records=imports(ast.parse(path.read_text(encoding='utf-8-sig'),filename=str(path)),package)
        graph[name]=[]
        for target,symbol,line,scope in records:
            local=target.removeprefix('backend.app.') if target.startswith('backend.app.') else None
            if local and local not in known and local+'.'+symbol in known:local+='.'+symbol
            if local:graph[name].append((local,line))
            # The retired executable baseline has no compatibility exception.
            legacy=target==BASELINE or target.startswith(BASELINE+'.') or target=='backend.app.resume_writer' and symbol in ('write_legacy','*')
            if legacy:
                errors.append(f'{path.relative_to(root)}:{line}: A01 production cannot depend on evaluation baseline ({target}.{symbol})')
    for start in sorted(CONTRACTS & graph.keys()):
        def walk(node, chain, visited):
            for target,line in graph.get(node,[]):
                if target in ORCHESTRATION:
                    errors.append(f'backend/app/{node.replace(".","/")}.py:{line}: A02 contract depends on orchestration: '+ ' -> '.join(chain+[target]))
                elif target not in visited:walk(target,chain+[target],visited|{target})
        walk(start,[start],{start})
    return sorted(set(errors))


def main():
    root=Path(__file__).resolve().parents[1]
    try:errors=check(root)
    except (OSError,ValueError,SyntaxError) as exc:
        print(f'Architecture check failed: {exc}',file=sys.stderr)
        return 1
    if errors:
        print('\n'.join(errors),file=sys.stderr)
        return 1
    print('Architecture boundaries passed (A01/A02)')
    return 0


if __name__=='__main__':sys.exit(main())
