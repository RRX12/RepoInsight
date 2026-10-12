"""Lossless Markdown source index and bounded lexical retrieval; no model calls."""
import re
from .resume_harness import digest

ALIASES={'agent':['智能体','orchestrator','编排','runtime'], 'memory':['记忆','上下文','context','召回','history'], '多轮':['session','历史','history','dialogue'], '恢复':['checkpoint','重试','retry','version','版本'], 'tool':['工具','capability','调用'], '记忆':['memory','context','history','compaction'], '编排':['agent','orchestrator','runtime','director'], '边界':['boundary','consent','permission'], '评测':['eval','test','monitor','log']}

def section_index(material, size=2400):
    """Offsets are Python character offsets, hashes bind IDs to the exact page revision.

    Prefer paragraph/heading/fenced-code boundaries. Oversized blocks split explicitly;
    no character disappears, including blank lines and the final suffix.
    """
    if size < 1: raise ValueError('section size must be positive')
    result=[]
    for page_no,page in enumerate(material.get('_full_wiki_pages',material.get('wiki_pages',[]))):
        text=page['content'];revision=digest([page.get('page_id',page_no),text]);boundaries=[0]
        offset=0;fence=None;headings=[];heading_at={0:[]}
        for line in text.splitlines(keepends=True):
            stripped=line.lstrip()
            mark=re.match(r'(`{3,}|~{3,})',stripped)
            if mark:
                if fence is None: fence=mark.group(1)[0]
                elif mark.group(1)[0]==fence: fence=None
            elif fence is None:
                heading=re.match(r'^(#{1,6})\s+(.+)',line)
                if heading:
                    level=len(heading.group(1));headings=[h for h in headings if h[0]<level]+[(level,heading.group(2).strip())]
                    boundaries.append(offset);heading_at[offset]=[h[1] for h in headings]
                if not line.strip():boundaries.append(offset+len(line))
            offset+=len(line)
        boundaries=sorted(set([*boundaries,len(text)]));blocks=[];start=0
        for end in boundaries[1:]:
            while end-start>size:
                prior=[b for b in boundaries if start<b<=start+size]
                cut=prior[-1] if prior else start+size
                blocks.append((start,cut));start=cut
            # Finish on each structural boundary; neighbors can be read together.
            if end>start:blocks.append((start,end));start=end
        page_rows=[]
        for start,end in blocks:
            hierarchy=heading_at[max(o for o in heading_at if o<=start)]
            ident=f'wiki:{page_no}:section:{revision[:12]}:{start}:{end}'
            page_rows.append({'id':ident,'source_ref':ident,'page_ref':f'wiki:{page_no}',
                'title':page.get('title',''),'heading_path':hierarchy,'section':' / '.join(hierarchy),
                'start':start,'end':end,'content':text[start:end],'content_hash':digest(text[start:end]),
                'revision_hash':revision,'revision_status':'unknown','file_paths':page.get('filePaths',[]),
                'parent':f'wiki:{page_no}', 'oversize_split':end-start==size})
        for n,row in enumerate(page_rows):
            row['previous_id']=page_rows[n-1]['id'] if n else None
            row['next_id']=page_rows[n+1]['id'] if n+1<len(page_rows) else None
        result.extend(page_rows)
    return result

def retrieve(material,requirements,budget=18000):
    rows=section_index(material);results=[];per=budget//max(1,len(requirements));total=0
    for requirement in requirements:
        terms={t.lower() for t in requirement.search_terms if t.strip()}
        for key,aliases in ALIASES.items():
            if any(key in t for t in terms):terms.update(aliases)
        ranked=[]
        for n,row in enumerate(rows):
            title=(row['title']+' '+row['section']).lower();body=(row['content']+' '+' '.join(row['file_paths'])).lower()
            score=sum(2*(t in title)+(t in body) for t in terms)
            if score:ranked.append((-score,n))
        selected=[];used=set();spent=0;omitted=[]
        for _,n in sorted(ranked):
            if n in used:continue
            group=[k for k in range(max(0,n-1),min(len(rows),n+2)) if rows[k]['page_ref']==rows[n]['page_ref'] and k not in used]
            amount=sum(len(rows[k]['content']) for k in group)
            if spent+amount>per or total+amount>budget:group=[n];amount=len(rows[n]['content'])
            if spent+amount>per or total+amount>budget or len(selected)>=6:
                omitted.append(rows[n]['id']);continue
            # Each source ID continues to refer to one exact, immutable source range.
            for k in group:
                if len(selected)>=6:break
                selected.append(rows[k]);used.add(k);spent+=len(rows[k]['content']);total+=len(rows[k]['content'])
        results.append({'requirement_id':requirement.requirement_id,'question':requirement.question,
            'candidate_evidence':selected,'status':'candidates_need_verification' if selected else 'unknown',
            'read_ids':[r['id'] for r in selected], 'budget_omitted_ids':omitted,
            'unread_ids':[r['id'] for n,r in enumerate(rows) if n not in used],
            'budget_chars':per,'read_chars':spent,'token_estimate_kind':'utf8_bytes_upper_estimate',
            'input_token_upper_estimate':sum(len(r['content'].encode('utf-8')) for r in selected)})
    return results
