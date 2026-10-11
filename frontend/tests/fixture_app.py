"""Offline E2E server: the production app and database run only in the test process."""
from backend.app.main import app
from backend.app.source_reader import SourceReader

SourceReader.resolve_revision = lambda self, repo, ref=None: {
    'commit_sha':'unresolved:github', 'status':'unresolved', 'error':'offline E2E fixture'}

# Explicit model transport fixtures; these never exercise a paid model.
from backend.app import interaction_service
from backend.app.interaction_contract import DiscussionResult, ReviewResult

def offline_interaction(stage,schema,payload,instruction):
    if stage=='EDITOR_REVIEW':
        return ReviewResult(suggested_text=payload['editor_text']+'\n（离线审查建议示例）',issues=[{'category':'fact_metric_attribution','issue':'离线模拟：请核对新增能力的源码证据，未验证真实模型判断'}])
    if stage=='DISCUSS':
        message=payload['message'];operations=[];intent='discussion'
        if message=='把幻觉率下降改成80%':
            matches=[m for m in payload['state']['metrics'] if m['name']=='幻觉率下降']
            if len(matches)==1:
                operations=[{'op':'update_metric','target_id':matches[0]['id'],'data':{'value':80}}];intent='explicit_update'
        return DiscussionResult(known_facts='离线模拟返回，仅验证交互状态；不代表真实模型判断。',advice_and_tradeoffs='应先核查角色隔离与独立决策证据，比较统一执行器和合并上下文的风险。',missing_information='当前缺少运行成本与隔离测试。',intent=intent,operations=operations)
    raise RuntimeError('Unexpected model stage in offline fixture')
interaction_service.ask_json=offline_interaction
