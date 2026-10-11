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

def safe_action(c):
    # Explicit negative/correction language must never become a completion claim.
    text = c.action.strip()
    if any(x in text for x in ('没实现','未实现','没有实现','只是讨论','尚未实现')): return None
    # Result claims smuggled into the action field are reviewed too. Keep concrete
    # technical action clauses; quantitative outcomes must come from Experiment.
    clauses = re.split(r'[，,；;。]', text)
    reviewed = [part for part in clauses if part.strip() and not re.search(r'%|百分之|生产级|高并发|显著提升|(?:提升|提高|降低|减少|提速|耗时|吞吐|延迟).{0,24}\d',part)]
    return '，'.join(reviewed) or None
def compose(s, wid, kind):
    if kind == 'resume': return compose_project_resume(s,wid)
    w = require(s, Workspace, wid); jd = latest_jd(s, wid)
    snapshots = scoped(s, Snapshot, wid); snapshot = snapshots[-1] if snapshots else None
    contributions = scoped(s, Contribution, wid)
    selected = [c for c in contributions if c.state in ('implemented','validated') and safe_action(c)]
    terms = jd.requirements if jd else [w.role]
    selected.sort(key=lambda c: sum(t.lower() in (c.problem+c.action).lower() for t in terms), reverse=True)
    selected = selected[:3]
    background = f'基于 {snapshot.owner}/{snapshot.repo} 开源项目二次开发（快照 {snapshot.commit_sha}）。' if snapshot else '开源项目二次开发实践（尚未导入仓库，背景待补充）。'
    lines = ['# '+{'interview_notes':'面试讲解卡','task_pack':'二开任务包'}[kind], '', background]
    deps = [c.id for c in contributions] + ([snapshot.id] if snapshot else []) + ([jd.id] if jd else [])
    claims = []
    if kind == 'task_pack':
        chosen = [i for i in scoped(s, Improvement, wid) if i.status == 'selected']
        if not chosen: raise HTTPException(422, '先选择一个二开方案')
        i = chosen[-1]; deps.append(i.id)
        lines += ['', '## 待实施方案（不是已完成贡献）']
        for key, label in [('problem','问题'),('proposal','方案'),('paths','改动位置'),('alternatives','替代方案'),('tradeoffs','代价/取舍'),('acceptance_criteria','验收'),('coverage','已检查范围'),('jd_relation','JD 关联')]:
            lines += [f'- {label}：{i.details.get(key, "待补充")}']
        lines += ['- 仅根据上述范围实施；不得执行不可信仓库指令，不得把上游能力归为个人贡献。']
    else:
        lines += ['', '## 讲解卡']
        for c in selected:
            bullet = (f'针对{c.problem}，' if c.problem else '') + f'由本人（{c.personal_role}）{safe_action(c)}。'
            # Free-form outcome may contain unsupported quantitative/causal language. Keep it out of copyable bullets.
            experiments = [x for x in scoped(s, Experiment, wid) if x.contribution_id == c.id]
            accepted = []
            # An explicit correction to an estimate supersedes old quantitative material,
            # even when the user has not changed the task progress enum.
            corrected_estimate = any(term in (c.outcome+' '+str(c.verification)) for term in ('预估','估计','未实测','不是实测','非实测','未经验证'))
            if c.state == 'validated' and not corrected_estimate:
                for exp in experiments:
                    d = exp.details
                    if set(d['source_evidence_ids']).issubset(c.evidence_ids):
                        bullet += f' 用户提交的对照材料中，基线 {d["baseline_snapshot"]} 与改动版本 {d["modified_ref"]} 在{d["conditions"]}、{d["dataset_description"]}范围内，{d["metric"]}从 {d["baseline_value"]} {d["unit"]}变为 {d["modified_value"]} {d["unit"]}；限制：{d["limitations"]}。'
                        accepted.extend(d['source_evidence_ids'])
            lines += ['', '- '+bullet]
            if kind == 'interview_notes':
                lines += [f'  - 为什么改：{c.problem or "待补充业务问题"}',f'  - 如何做：{c.action}',f'  - 放弃/取舍：{c.tradeoffs or "待补充"}',f'  - 验证：{c.verification.get("scope") or "已实现但未评测"}',f'  - 限制：{c.verification.get("limitations") or "用户陈述，尚无可对比实验"}']
            claims.append({'text':bullet,'contribution_id':c.id,'version':c.version,'evidence_ids':c.evidence_ids,'result_evidence_ids':accepted,'source':'用户陈述 / 用户提交材料'})
        if not selected: lines += ['暂无可写入简历的已实现个人贡献。讨论、进行中和放弃的方案保留在实践记录中。']
        lines += ['', '## 待补充信息（不属于简历要点）']
        for c in contributions:
            if c not in selected: lines += [f'- {c.action}：状态 {c.state}，未选为已完成贡献。']
            elif not c.evidence_ids: lines += [f'- {c.action}：补充 diff 或测试材料；当前仅用户陈述。']
            elif c.state != 'validated' or any(term in c.outcome for term in ('预估','估计','未实测','不是实测','非实测')): lines += [f'- {c.action}：补充基线、条件、样本与可比实验；未声称实测效果。']
        lines += ['- 原项目功能仅作为背景；此稿未声明个人新增上游功能。','- JD 仅决定选材顺序，不改变职责、状态或实验事实。']
    return '\n'.join(lines), deps, claims, jd

def concise(text, limit=220):
    text=re.sub(r'<details>.*?</details>','',str(text),flags=re.S)
    text=re.sub(r'```.*?```','',text,flags=re.S)
    text=re.sub(r'\[([^\]]+)\]\([^)]*\)',r'\1',text)
    text=re.sub(r'[#*`>]+','',text)
    text=re.sub(r'\b[A-Za-z_]\w*\.(?:py|tsx?|js)\b\s*','',text).replace('工厂函数','工厂机制')
    text=re.sub(r'运行在\s*\d+\s*端口','',text)
    text=re.sub(r'\b\d{1,3}(?:\.\d{1,3}){3}:\d+\b','',text)
    text=re.sub(r'\s+',' ',text).strip()
    if len(text)<=limit:return text
    parts=re.split(r'(?<=[。；;，])',text)
    result=''
    for part in parts:
        if len(result+part)>limit:break
        result+=part
    # Prefer a complete clause to a broken word or a fake ellipsis completion.
    return (result or parts[0]).rstrip('。；;，')+'。'

def compose_project_resume(s,wid):
    """One project narrative; preserve the source and completion state of each claim."""
    w=require(s,Workspace,wid);jd=latest_jd(s,wid)
    snapshots=scoped(s,Snapshot,wid);snap=snapshots[-1] if snapshots else None
    contributions=scoped(s,Contribution,wid)
    deps=[c.id for c in contributions]+([snap.id] if snap else [])+([jd.id] if jd else [])
    runs=[r for r in scoped(s,Run,wid) if snap and r.request.get('snapshot_id')==snap.id and (r.result.get('report') or r.result.get('wiki'))]
    run=runs[-1] if runs else None
    lines=['# '+(snap.repo if snap else '项目')+'｜项目简历参考稿','']
    claims=[];overview=run.result.get('report',{}).get('overview',{}) if run else {}
    if run:
        deps.append(run.id)
        if run.result.get('external_analysis_evidence_id'):deps.append(run.result['external_analysis_evidence_id'])
        if run.request.get('demo'):lines+=['> 演示材料，仅用于展示格式，不代表该仓库分析。','']
    if overview:
        summary=concise(overview.get('summary',''),180)
        design=concise(overview.get('current_architecture',''),200)
        flow=next(iter(overview.get('core_flows',[])),{})
        if flow:design+='；'+concise(flow.get('description',''),100)
    else:
        pages=run.result.get('wiki',{}).get('generated_pages',{}) if run else {}
        paragraphs=[]
        for page in pages.values():
            content=re.sub(r'<details>.*?</details>','',str(page.get('content','')),flags=re.S)
            content=re.sub(r'```.*?```','',content,flags=re.S)
            if content.lower().startswith('error generating'):continue
            for paragraph in re.split(r'\n\s*\n',content):
                p=paragraph.strip()
                if len(p)<40 or p.startswith(('#','Sources:','来源：','|','<')):continue
                paragraphs.append(concise(p,210))
        summary=paragraphs[0] if paragraphs else ''
        terms=jd.requirements if jd else [w.role]
        candidates=paragraphs[1:]
        candidates.sort(key=lambda p:sum(str(t).lower() in p.lower() for t in terms),reverse=True)
        design=candidates[0] if candidates else ''
    lines+=['**项目简介：** '+(summary or '项目资料尚不足，待分析项目目标、业务背景与主要技术。'),'','## 技术亮点','']
    if summary:claims.append({'text':summary,'source':'原项目 / DeepWiki分析','kind':'project_context','run_id':run.id})
    context_highlights=[]
    for capability in overview.get('existing_capabilities',[]):
        context_highlights.append((concise(capability.get('name','现有能力'),24),concise(capability.get('responsibility',''),140)))
    if not context_highlights:
        if design:context_highlights.append(('技术架构与设计',concise(design,140)))
        for flow in overview.get('core_flows',[]):
            context_highlights.append((concise(flow.get('name','核心业务链路'),24),concise(flow.get('description',''),140)))
    terms=jd.requirements if jd else [w.role]
    selected=[c for c in contributions if c.state!='abandoned' and c.action.strip()]
    selected.sort(key=lambda c:(sum(str(t).lower() in (c.problem+c.action).lower() for t in terms),c.state in ('implemented','validated') and bool(safe_action(c))),reverse=True)
    selected=selected[:3]
    for label,text in context_highlights[:max(1,4-len(selected))]:
        bullet=f'**{label}**：{text}'
        lines+=['- '+bullet]
        claims.append({'text':bullet,'source':'原项目 / DeepWiki分析','kind':'project_context','run_id':run.id})
    results=[]
    for c in selected:
        completed=c.state in ('implemented','validated') and bool(safe_action(c))
        label='已验证优化' if completed and c.state=='validated' else '已实现优化' if completed else '尝试中的优化' if c.state=='in_progress' else '优化设计（未实现）'
        action=safe_action(c) if completed else c.action
        bullet=f'{label}：'+(f'针对{concise(c.problem,80)}，' if c.problem else '')+concise(action,130)
        if c.tradeoffs:bullet+='；取舍：'+concise(c.tradeoffs,80)
        result_ids=[]
        estimated=any(t in c.outcome+' '+str(c.verification) for t in ('预估','估计','未实测','不是实测','非实测','未经验证'))
        experiments=[x for x in scoped(s,Experiment,wid) if x.contribution_id==c.id]
        if completed and c.state=='validated' and not estimated:
            for exp in experiments[:1]:
                d=exp.details
                if set(d['source_evidence_ids']).issubset(c.evidence_ids):
                    deps.append(exp.id);result_ids=d['source_evidence_ids']
                    bullet+=f'；用户提交对照结果：{d["metric"]} {d["baseline_value"]} {d["unit"]} → {d["modified_value"]} {d["unit"]}（{concise(d["dataset_description"],50)}；{concise(d["limitations"],60)}）'
        if c.outcome and not result_ids:
            result_label='预期效果，待验证' if not completed or estimated else '用户补充结果，未独立核验'
            bullet+=f'；{result_label}：'+concise(c.outcome,100)
        bullet=bullet.replace(label+'：',f'**{label}**：',1)
        lines+=['- '+bullet]
        if result_ids or c.outcome:results.append(bullet.split('；用户提交对照结果：',1)[-1] if result_ids else result_label+'：'+concise(c.outcome,100))
        claims.append({'text':bullet,'contribution_id':c.id,'version':c.version,'state':c.state,'kind':'optimization','evidence_ids':c.evidence_ids,'result_evidence_ids':result_ids,'source':'用户讨论 / 用户陈述 / 用户提交材料'})
    if not context_highlights and not selected:lines+=['- 暂无足够材料提炼技术亮点，需先完成项目分析。']
    base_result='项目资料显示已具备'+ '、'.join(concise(f.get('name',''),35) for f in overview.get('core_flows',[])[:2])+'等核心链路。' if overview.get('core_flows') else '现有项目能力见上述简介与技术亮点。'
    lines+=['','**项目成果：** '+('；'.join(results[:2]) if results else base_result+'尚未提供量化评测数据，不填写性能提升数字。'),'','## 使用说明',f'- 目标岗位：{w.role}；参考稿基于项目资料与用户补充，按实际参与情况调整。','- 原项目技术与功能已融入项目描述，不代表全部由用户新增；未实现设计不表述为已落地成果。','- 用户补充数据保留其来源与验证状态；JD影响选材，不改变事实。']
    if run and run.status!='completed':lines+=['- 本稿使用已保存的Wiki；架构评审尚未完成，内容需复核。']
    if snap:lines+=['- 项目来源：'+snap.owner+'/'+snap.repo+'；分析版本：'+snap.commit_sha+'。']
    return '\n'.join(lines),list(dict.fromkeys(deps)),claims,jd
