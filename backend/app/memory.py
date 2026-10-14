import hashlib
import re
from sqlalchemy import select, update
from fastapi import HTTPException
from .db import *
from .schemas import ContributionInput

def scoped(s, cls, wid): return list(s.scalars(select(cls).where(cls.workspace_id == wid).order_by(cls.created_at)))
def require(s, cls, ident, wid=None):
    row = s.get(cls, ident)
    if not row or (wid is not None and row.workspace_id != wid):
        raise HTTPException(404, '记录不存在或不属于当前工作区')
    return row
def latest_jd(s, wid): return next(iter(reversed(scoped(s, JD, wid))), None)
def jd_terms(text):
    return list(dict.fromkeys(re.findall(r'[A-Za-z][A-Za-z0-9+#._-]{1,30}|[\u4e00-\u9fff]{2,8}',text)))[:30]

def save_jd_version(s,wid,text):
    require(s,Workspace,wid);old=latest_jd(s,wid)
    if old and old.raw_text==text:return old
    jd=JD(workspace_id=wid,raw_text=text,requirements=jd_terms(text),version=old.version+1 if old else 1,supersedes_id=old.id if old else None)
    s.add(jd);s.flush();invalidate(s,wid)
    s.add(MemoryEvent(workspace_id=wid,entity_type='jd',entity_id=jd.id,operation='new_version',before=asdict(old) if old else {},after=asdict(jd)))
    return jd

def save_target(s,wid,role,jd_text):
    w=require(s,Workspace,wid)
    if not role.strip() or role=='待填写':raise HTTPException(422,'请填写岗位名称')
    changed=w.role!=role;w.role=role;old=latest_jd(s,wid)
    if (old.raw_text if old else '')!=jd_text:
        save_jd_version(s,wid,jd_text)
    if changed:invalidate(s,wid)
    return latest_jd(s,wid)

def invalidate(s, wid, ids=None):
    for artifact in scoped(s, Artifact, wid):
        if ids is None or set(ids) & set(artifact.dependency_ids): artifact.review_status = 'needs_review'
def check_evidence(s, wid, ids):
    return [require(s, Evidence, ident, wid) for ident in ids]
def attach(s, wid, kind, text, source='用户提交', **kwargs):
    evidence = Evidence(workspace_id=wid, type=kind, excerpt=text, source_ref=source,
        content_hash=hashlib.sha256(text.encode()).hexdigest(), provenance={'user_statement':'用户陈述','diff':'用户提交代码改动','test_report':'用户提交运行记录','external_analysis':'外部分析材料','source_code':'源码支持','readme':'源码支持'}[kind], **kwargs)
    s.add(evidence); s.flush()
    folder = DATA / 'workspaces' / wid / 'evidence'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f'{evidence.id}.txt').write_text(text, encoding='utf-8')
    return evidence
def validate_contribution(s, wid, data):
    evidences = check_evidence(s, wid, data['evidence_ids'])
    if data.get('improvement_id'): require(s, Improvement, data['improvement_id'], wid)
    if data['state'] == 'validated':
        v = data['verification']
        if not all(v.get(k) for k in ('scope','source','limitations')) or not any(e.type == 'test_report' for e in evidences):
            raise HTTPException(422, '已验证需关联测试报告，并说明验证范围、来源与限制；材料为用户提交，不代表本系统认证')
    if data['state'] in ('implemented','validated') and not data['personal_role'].strip():
        raise HTTPException(422, '请明确个人职责')
def save_contribution(s, wid, data, ident=None, expected=None, source_message=None):
    validate_contribution(s, wid, data)
    before = {}
    if ident:
        row = require(s, Contribution, ident, wid); before = asdict(row)
        result = s.execute(update(Contribution).where(Contribution.id==ident, Contribution.workspace_id==wid, Contribution.version==expected).values(**data, version=expected+1))
        if result.rowcount != 1: raise HTTPException(409, '版本已变化，请刷新后再更正')
        s.expire(row); invalidate(s, wid, [ident])
    else:
        row = Contribution(workspace_id=wid, **data); s.add(row); s.flush()
        # New facts can change selection and missing-material lists in previous drafts.
        invalidate(s, wid)
    events = [e for e in scoped(s, MemoryEvent, wid) if e.entity_id == row.id]
    s.add(MemoryEvent(workspace_id=wid, entity_type='contribution', entity_id=row.id,
        operation='correct' if ident else 'create', before=before, after=asdict(row), source_message_id=source_message,
        supersedes_event_id=events[-1].id if events else None))
    return row
