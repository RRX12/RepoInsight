"""Offline E2E server: the production app and database run only in the test process."""
from backend.app.main import app
from backend.app.source_reader import SourceReader

SourceReader.resolve_revision = lambda self, repo, ref=None: {
    'commit_sha':'a'*40, 'status':'resolved', 'note':'synthetic offline E2E revision'}

# Explicit model transport fixtures; these never exercise a paid model.
from backend.app import interaction_service
from backend.app.interaction_contract import ReviewResult

def offline_interaction(stage,schema,payload,instruction):
    if stage=='EDITOR_REVIEW':
        return ReviewResult(suggested_text=payload['editor_text']+'\n（离线审查建议示例）',issues=[{'category':'fact_metric_attribution','issue':'离线模拟：请核对新增能力的源码证据，未验证真实模型判断'}])
    raise RuntimeError('Unexpected model stage in offline fixture')
interaction_service.ask_json=offline_interaction
