"""One source-structure layer. Offsets are parser bytes, never substring guesses."""
import hashlib
import importlib
import re
from pathlib import PurePosixPath

VERSION='wiki-structure-v1'
PARSER_VERSION='tree-sitter-0.25.2/python-0.25.0/javascript-0.25.0/typescript-0.23.2'
TOKEN_VERSION='utf8-byte-upper-v1'

def tokens(value):
    return len(value.encode('utf-8')) if isinstance(value,str) else len(value)

def hashed(value):return hashlib.sha256(value.encode('utf-8')).hexdigest()

class StructureSplitter:
    def __init__(self,target=600,maximum=1200,overlap=80):
        if not 1<=target<=maximum or not 0<=overlap<maximum:raise ValueError('split_budget')
        self.target=target;self.maximum=maximum;self.overlap=overlap
        self.version=f'{VERSION}/{PARSER_VERSION}/{TOKEN_VERSION}/{target}/{maximum}/{overlap}'

    def __call__(self,path,text):
        raw=text.encode('utf-8');suffix=PurePosixPath(path).suffix.lower()
        language={'.py':'python','.js':'javascript','.jsx':'javascript','.mjs':'javascript','.ts':'typescript','.tsx':'tsx','.md':'markdown'}.get(suffix,'unknown')
        rows=[];symbols=[]
        def add(start,end,kind,symbol='',qualified='',parent=None,status='parsed',reason='',complete=True,headings=None):
            if end<=start or not raw[start:end].strip():return
            piece=raw[start:end].decode('utf-8')
            rows.append({'start_byte':start,'end_byte':end,'start_line':raw[:start].count(b'\n')+1,
                         'end_line':raw[:end].count(b'\n')+int(not raw[:end].endswith(b'\n')),
                         'text':piece,'embedding_text':piece,'embedding_input_hash':hashed(piece),'content_hash':hashed(piece),
                         'language':language,'kind':kind,'symbol':symbol,'qualified_name':qualified,
                         'parent_symbol_id':hashed(path+':'+parent['qualified']) if parent else None,
                         'parent_start':parent['start'] if parent else start,'parent_end':parent['end'] if parent else end,
                         'parse_status':status,'parser_version':PARSER_VERSION if language not in ('markdown','unknown') else language+'-v1',
                         'splitter_version':self.version,'token_estimator':TOKEN_VERSION,'tokens_estimated':True,
                         'complete':complete,'fallback_reason':reason,'heading_path':headings or []})
        def window(start,end,kind='fallback',parent=None,status='fallback',reason='unsupported_language',overlap=False):
            cursor=start
            while cursor<end:
                finish=min(end,cursor+self.maximum)
                while finish>cursor:
                    try:raw[cursor:finish].decode('utf-8');break
                    except UnicodeDecodeError:finish-=1
                if finish<end:
                    boundary=raw.rfind(b'\n',cursor+1,finish)
                    if boundary>cursor:finish=boundary+1
                add(cursor,finish,kind,parent=parent,status=status,reason=reason,complete=False)
                next_cursor=finish
                if overlap and finish<end:
                    next_cursor=max(cursor+1,finish-self.overlap)
                    while next_cursor<finish and raw[next_cursor]&0xc0==0x80:next_cursor+=1
                cursor=next_cursor
        if not raw.strip():return []
        if language=='markdown':
            starts=[(0,[])];stack=[];offset=0;fence=None
            for line in raw.splitlines(keepends=True):
                decoded=line.decode('utf-8');mark=re.match(r'^\s*(`{3,}|~{3,})',decoded)
                if mark:
                    if fence is None:fence=mark[1][0]
                    elif fence==mark[1][0]:fence=None
                heading=re.match(r'^(#{1,6})\s+(.+?)\s*#*\s*$',decoded.rstrip('\r\n')) if fence is None else None
                if heading:
                    depth=len(heading[1]);stack=stack[:depth-1]+[heading[2]]
                    if offset==0:starts[0]=(0,list(stack))
                    else:starts.append((offset,list(stack)))
                offset+=len(line)
            for i,(start,headings) in enumerate(starts):
                end=starts[i+1][0] if i+1<len(starts) else len(raw)
                before=len(rows)
                if end-start<=self.maximum:add(start,end,'document',status='markdown',headings=headings)
                else:window(start,end,'document',status='markdown',reason='oversized_markdown_section')
                for row in rows[before:]:row['heading_path']=headings
            return rows
        if language=='unknown':window(0,len(raw),overlap=True);return rows
        from tree_sitter import Language,Parser
        module=importlib.import_module('tree_sitter_'+('typescript' if language in ('typescript','tsx') else language))
        capsule=getattr(module,'language_'+language)() if language in ('typescript','tsx') else module.language()
        tree=Parser(Language(capsule)).parse(raw)
        if tree.root_node.has_error:window(0,len(raw),status='parse_error',reason='syntax_error',overlap=True);return rows
        functions={'function_definition','function_declaration','generator_function_declaration','method_definition','arrow_function','function_expression'}
        classes={'class_definition','class_declaration','class'}
        def name(node):
            n=node.child_by_field_name('name')
            if n is None and node.type=='arrow_function':
                n=node.parent.child_by_field_name('name') if node.parent else None
            return raw[n.start_byte:n.end_byte].decode('utf-8') if n else '<anonymous>'
        def collect(node,prefix='',parent=None):
            current=parent;scope=prefix
            if node.type in functions|classes:
                scope=(prefix+'.' if prefix else '')+name(node)
                wrapper=node.parent if node.parent and node.parent.type in ('decorated_definition','export_statement') else node
                if node.type in ('arrow_function','function_expression') and node.parent and node.parent.type=='variable_declarator':
                    wrapper=node.parent
                    if wrapper.parent and len(wrapper.parent.named_children)==1:wrapper=wrapper.parent
                    if wrapper.parent and wrapper.parent.type=='export_statement':wrapper=wrapper.parent
                current={'start':wrapper.start_byte,'end':wrapper.end_byte,'qualified':scope,'symbol':name(node),'kind':'class_header' if node.type in classes else 'method' if parent and parent['kind']=='class_header' else 'function'}
                symbols.append(current)
            for child in node.named_children:collect(child,scope,current)
        collect(tree.root_node)
        def emit(node,parent=None,prefix=''):
            wrapper=node
            if node.type in ('decorated_definition','export_statement'):
                definition=next((n for n in node.named_children if n.type in functions|classes),None)
                if definition is not None:node=definition
                elif len(node.named_children)==1 and node.named_children[0].type in ('lexical_declaration','variable_declaration'):node=node.named_children[0]
            if node.type in ('lexical_declaration','variable_declaration') and len(node.named_children)==1:
                value=node.named_children[0].child_by_field_name('value')
                if value and value.type in ('arrow_function','function_expression'):node=value
            symbol=name(node) if node.type in functions|classes else ''
            qualified=(prefix+'.' if prefix else '')+symbol if symbol else prefix
            own={'start':wrapper.start_byte,'end':wrapper.end_byte,'qualified':qualified,'kind':'class_header' if node.type in classes else 'function'}
            start=wrapper.start_byte
            previous=wrapper.prev_named_sibling
            while previous and previous.type=='comment' and raw[previous.end_byte:start].count(b'\n')<=2:
                start=previous.start_byte;previous=previous.prev_named_sibling
            if node.type in classes:
                body=node.child_by_field_name('body')
                children=list(body.named_children) if body else []
                first=children[0].start_byte if children else wrapper.end_byte
                if first-start<=self.maximum:add(start,first,'class_header',symbol,qualified,own)
                else:window(start,first,'class_header',own,reason='oversized_class_header')
                for child in children:emit(child,own,qualified)
                return
            kind='method' if parent and parent['kind']=='class_header' and node.type in functions else 'function' if node.type in functions else 'top_level'
            if wrapper.end_byte-start<=self.maximum:
                add(start,wrapper.end_byte,kind,symbol,qualified,own if node.type in functions else parent);return
            body=node.child_by_field_name('body')
            if body and body.named_children:
                cursor=start;group_start=start
                for child in body.named_children:
                    if child.end_byte-group_start>self.target and cursor>group_start:
                        if cursor-group_start<=self.maximum:add(group_start,cursor,kind,symbol,qualified,own,complete=False)
                        else:window(group_start,cursor,kind,own,reason='oversized_syntax_subblock')
                        group_start=cursor
                    cursor=child.end_byte
                if wrapper.end_byte-group_start<=self.maximum:add(group_start,wrapper.end_byte,kind,symbol,qualified,own,complete=False)
                else:window(group_start,wrapper.end_byte,kind,own,reason='oversized_syntax_subblock')
            else:window(start,wrapper.end_byte,kind,parent or own,reason='oversized_syntax_subblock')
        for node in tree.root_node.named_children:emit(node)
        # Cover every nonempty region not covered by structures, including braces/registrations.
        cursor=0
        for row in sorted(list(rows),key=lambda r:r['start_byte']):
            if cursor<row['start_byte']:window(cursor,row['start_byte'],'top_level',status='parsed',reason='uncovered_region')
            cursor=max(cursor,row['end_byte'])
        if cursor<len(raw):window(cursor,len(raw),'top_level',status='parsed',reason='uncovered_region')
        for row in rows:
            row['symbol_spans']=[s for s in symbols if s['start']>=row['start_byte'] and s['start']<row['end_byte']]
        return sorted(rows,key=lambda r:(r['start_byte'],r['end_byte']))
