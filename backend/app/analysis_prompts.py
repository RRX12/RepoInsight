"""Closed role-task registry. Repository/user text cannot choose templates or tools."""
from dataclasses import dataclass
import json
from pathlib import Path
from .providers import ProviderError
from .analysis_harness import digest
from .analysis_contract import Analysis
from .architecture_schema import OptimizationDiscovery,OptimizationReportV2

PROMPT_ROOT = Path(__file__).resolve().parents[1] / 'prompts' / 'analysis'

@dataclass(frozen=True)
class TaskSpec:
    template: str
    schema: type
    fields: tuple[str, ...]
    allowed_tools: tuple[str, ...] = ()
    version: str = 'project-role-v1'

TASKS = {
    'optimization_discover':TaskSpec('optimization_discover',OptimizationDiscovery,('constraints','jd','role_origin','project','requirements','analysis','research','corrections'),version='optimization-discover-v1'),
    'optimization_synthesize':TaskSpec('optimization_synthesize',OptimizationReportV2,('constraints','jd','role_origin','project','requirements','analysis','research','corrections','discovery','previous','final_call','prepared_overview'),version='optimization-synthesize-v1'),
    'technical_investigation': TaskSpec('technical_investigation', Analysis, ('previous','sources','requirements','feedback','facts','product','paths','coverage','remaining_gaps','project_corrections'), version='project-technical-investigation-v1'),
}

def task_for_stage(stage):
    return {'OPTIMIZATION_DISCOVER':'optimization_discover','OPTIMIZATION_SYNTHESIZE':'optimization_synthesize','OPTIMIZATION_REFINE':'optimization_synthesize','INVESTIGATE':'technical_investigation','SYNTHESIZE':'technical_investigation'}.get(stage)

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
    prompt = stage+'\n'+common+'\n'+template+'\n'+instruction+'\n'+json.dumps(scoped,ensure_ascii=False)+'\nJSON schema:'+json.dumps(schema.model_json_schema(),ensure_ascii=False)
    return prompt, {'task':task,'template_version':spec.version,'template_hash':digest([common,template,instruction]),
                    'material_hash':digest(scoped),'input_fields':list(scoped),'allowed_tools':list(spec.allowed_tools)}
