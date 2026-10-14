"""Skill registry shared by production writing and explicit editing."""
from pathlib import Path

SKILLS = {
    'repo_discovery':'按兴趣、约束和可选 JD 搜索与解释候选',
    'repo_understanding':'固定快照、阅读链路与明确覆盖',
    'improvement_planning':'先核查必要性，再按岗位排序',
    'contribution_interview':'补充个人行动、尝试与取舍',
    'resume_composition':'事实不变的简历选材',
    'claim_review':'核查归属、状态、数字与依据',
}
def load_skill(name):
    if name not in SKILLS: raise ValueError('未知 Skill')
    return (Path(__file__).resolve().parents[1] / 'skills' / name / 'SKILL.md').read_text(encoding='utf-8')
