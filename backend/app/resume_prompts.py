"""Closed role-task registry. Repository/user text cannot choose templates or tools."""
from dataclasses import dataclass
import json
from pathlib import Path
from .providers import ProviderError
from .resume_harness import digest
from .resume_contract import Choice, Discovery, QualityReview, Analysis

PROMPT_ROOT = Path(__file__).resolve().parents[1] / 'prompts' / 'resume'

@dataclass(frozen=True)
class TaskSpec:
    template: str
    schema: type
    fields: tuple[str, ...]
    allowed_tools: tuple[str, ...] = ()
    version: str = 'resume-role-v1'

TASKS = {
    'hr_selection': TaskSpec('hr_selection', Choice, ('eligible_ids','project_spine','candidates','claims','requirements','output_mode','selection_policy'), version='resume-hr-selection-v2'),
    'technical_investigation': TaskSpec('technical_investigation', Analysis, ('previous','sources','requirements','feedback','facts','product','paths','coverage','remaining_gaps','project_corrections'), version='resume-technical-investigation-v2'),
    'hr_review': TaskSpec('hr_review', QualityReview, ('draft','candidates','choice','requirements','claim_limits','claims')),
    'technical_review': TaskSpec('technical_review', QualityReview, ('draft','claims','claim_limits','candidates','requirements','evidence')),
}

def task_for_stage(stage):
    return {'SELECT':'hr_selection','RESELECT':'hr_selection','RESELECT_FACT':'hr_selection',
            'INVESTIGATE':'technical_investigation','SYNTHESIZE':'technical_investigation',
            'REVIEW_HR':'hr_review','REVIEW_TECHNICAL':'technical_review'}.get(stage)

def validate_configuration():
    for task,spec in TASKS.items():
        compose(task,'CONFIG_CHECK',spec.schema,{},'')

def compose(task, stage, schema, data, instruction):
    if task not in TASKS or TASKS[task].schema is not schema:
        raise ProviderError('未知角色任务或输出契约不匹配', 'resume_prompt_config')
    spec = TASKS[task]
    try:
        common = (PROMPT_ROOT / 'common.md').read_text(encoding='utf-8')
        template = (PROMPT_ROOT / (spec.template+'.md')).read_text(encoding='utf-8')
        if not common.strip() or not template.startswith(f'<!-- {spec.version} -->'):
            raise ValueError('missing version header')
    except (OSError, ValueError) as exc:
        raise ProviderError('角色模板缺失或版本无效：'+spec.template, 'resume_prompt_config') from exc
    scoped = {key:data[key] for key in spec.fields if key in data}
    if task == 'hr_review':
        # HR sees factual boundaries, not raw code or an implied code-verification task.
        scoped['claims'] = [{k:v for k,v in c.items() if k in ('id','statement','implementation_state','attribution','contribution_id')} for c in scoped.get('claims',[])]
    prompt = stage+'\n'+common+'\n'+template+'\n'+instruction+'\n'+json.dumps(scoped,ensure_ascii=False)+'\nJSON schema:'+json.dumps(schema.model_json_schema(),ensure_ascii=False)
    return prompt, {'task':task,'template_version':spec.version,'template_hash':digest([common,template,instruction]),
                    'material_hash':digest(scoped),'input_fields':list(scoped),'allowed_tools':list(spec.allowed_tools)}
