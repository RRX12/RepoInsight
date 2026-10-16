import json
from backend.tests.test_shared_analysis import report as old_report

def data(prompt):return json.loads(prompt.split('\nJSON schema:')[0].split('\n')[-1])
def plan(prompt):
    d=data(prompt);ref=next(s['source_id'] for s in d['research']['sources'] if s['path']=='memory.ts')
    return {'candidates':[{'candidate_id':'c','title':'记忆评测','kind':'capability_deepening','current_state':{'statement':'已有版本化状态','source_refs':[ref]},'opportunity':'补充评测','expected_value':'检查一致性','preliminary_decision':'validate_first','decision_reason':'先测量','research_actions':[]}]}
def report_v2(prompt):
    d=data(prompt);ref=next(s['source_id'] for s in d['research']['sources'] if s['path']=='memory.ts')
    return {'schema_version':'optimization-v2','overview':old_report()['overview'],'candidate_assessments':[{'candidate_id':'c','title':'记忆评测','kind':'capability_deepening','decision':'validate_first','project_value':'回归','jd_relation':'状态','fit':'局部','effort':'低','verifiability':'测试','evidence_sufficiency':'partial','rationale':'先验证','source_refs':[ref]}],'directions':[],'no_change_reason':'先测量再决定'}
def response(prompt):
    return json.dumps(plan(prompt) if prompt.startswith('OPTIMIZATION_DISCOVER') else report_v2(prompt),ensure_ascii=False)


def detailed(report):
    ref=report['candidate_assessments'][0]['source_refs'][0]
    return {'candidate_id':'c','title':'记忆评测','kind':'capability_deepening','current_design':{'statement':'已有版本化记忆','source_refs':[ref]},'goal':'检验状态一致性','scenario':'回归测试','why_now':'有明确验收需求','jd_relation':'记忆能力深化','technical_options':[{'name':'现状','mechanism':'保留当前实现','prerequisites':'无','benefits_expected':'无新增复杂性','costs':'未新增评测','tradeoffs':'覆盖不足','source_refs':[ref]},{'name':'局部评测','mechanism':'新增测试场景','prerequisites':'可运行测试','benefits_expected':'可复现回归','costs':'维护用例','tradeoffs':'静态测试非线上验证','source_refs':[ref]}],'recommended_design':{'chosen_option':'局部评测','rationale':'局部可验证','components':['测试用例'],'execution_steps':['建立基线'],'failure_handling':'保留失败结果'},'code_changes':[{'change_type':'add','path':'memory-eval.test.ts','responsibility':'回归用例','change_description':'新增测试','source_refs':[]}],'implementation_steps':[{'step_id':'s1','action':'建立基线','dependencies':[],'deliverable':'测试记录'}],'validation_plan':[{'scenario':'过期更新','baseline':'现有行为','method':'离线运行','metric_or_acceptance':'拒绝过期更新','measurement_status':'not_measured'}],'assumptions':[]}
