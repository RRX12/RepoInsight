# 同输入前后示例（离线契约，非质量证据）

输入指纹：69479824974c61e2e28a92650ea6e45609cad99d9bf252affb5b3c445fa891a4。输入是固定fixture的版本化记忆材料，不是CP Dance实测。两个模型响应均为fixture，实际调用旧/new生产writer。

## 旧版正文

**项目简介：** 角色记忆系统。

## 技术亮点
- **版本化记忆**：角色记忆按版本更新，拒绝过期写入。

**项目成果：** 保留角色经历。

## 新版正文

**项目简介：** 角色记忆按版本更新，过期更新被拒绝。

## 技术亮点

- **版本化记忆**：角色记忆按版本更新，过期更新被拒绝。

## 候选与证据差异

新流程有2候选，选['n1']，9请求。旧流程直接选题并写Markdown；新版保存候选、claim的独立状态、岗位覆盖和逐段映射。同一Wiki只支持文档陈述，validation_level=unknown，不冒充源码核验。成果无证据可省略。

## 改进与退化

已验证结构可追溯、契约运行和省略成果。表达优劣未评分；更多请求/源码读取增加时延，词面召回和同模型审查仍有遗漏风险。fixture文字重复是样例局限，不能拿作质量提升证明。

重新运行：`.venv/Scripts/python scripts/eval-resume-quality.py --compare-legacy --output data/resume-quality-offline.json`。真实评测失败与完成记录见resume-quality-progress.md；不将聊天中提供的项目描述当人工金标准。
