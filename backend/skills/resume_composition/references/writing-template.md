# 项目简历写作契约

写作目标：清晰表达业务对象、具体机制、岗位价值及真实贡献。STAR是内在逻辑，不必打印S/T/A/R标题，也不强制四部分齐全。

ResumeDraft结构：output_mode、project_intro{text,claim_ids,contribution_ids,metric_ids}、bullets[{id,title,text,candidate_ids,claim_ids,contribution_ids,metric_ids}]、outcome（可null）、questions、limitations。

项目简介约60–130字，说明业务对象和核心任务，交代必要技术背景；亮点通常2–4条、每条1–2句，约60–140字。具体问题/约束→关键机制→代码支持的行为或有依据结果；动机、取舍没有材料就留空。成果仅在有独立信息时写，不重复简介。

两种产物：项目参考稿介绍上游，个人简历需要确认个人行动。可以同主题提及原有机制和个人改动，分别关联claims，不自动把上游归用户。未实现计划、预估和待核实问题不进入正文，放外部面板。

不强制指标，不复制其他简历的技术和数据。用户报告的指标必须明确测量口径、样本、环境和来源；没有报告可写“拒绝过期更新”等支持的行为，不能推导性能收益。删除重复、泛化价值、端口/文件名等低价值细节。

材料不足不等于能力不存在。角色记忆不等同用户记忆，词面召回不等同语义RAG；保留独立项目全貌，岗位只影响调查和选材，不改变技术栈或定位。

机制卡片：优先用已支持的业务约束、处理步骤与异常边界组成亮点。类型、接口或函数存在不等于链路已接通；只有这类证据时不能补写拒绝、恢复、调度或收益机制，可在正文外说明缺口。选题大纲、候选理由和未映射的问题不能充当事实；不为补齐STAR编造背景或结果。参考稿描述项目已有能力，仓库地址不证明个人实现；个人行动只能来自当前确认贡献。

## 研究来源（借鉴原则，不照搬例句或数字）
- Harvard Mignone Center for Career Success：事实导向、展示结果、简洁易扫读：https://careerservices.fas.harvard.edu/resources/create-a-strong-resume/
- Yale Office of Career Strategy：动作、背景与结果组成成就条目：https://ocs.yale.edu/resources/writing-impactful-resume-bullets/
- University of Michigan-Dearborn：STAR与Power Verb + What you did + Results/Purpose：https://umdearborn.edu/career-services/job-and-internship-prep/resumes-and-cover-letters/how-create-strong-resume-bullet
- 公开project-resume-writer的选材与最终审查流程：https://github.com/oxygen914/project-resume-writer/blob/main/SKILL.md


### 项目主线与机制表达（当前生产）
- project_spine中的已支持、已实现上游事实可用于简介；不得将未选主题扩展成技术亮点或成果。原作者目标、行业普遍痛点和用户动机没有事实映射时不补写。
- 技术亮点以业务约束→触发/输入→处理步骤→状态或权限边界→输出作用组织；仅写材料确认的连接，不以模块或类型名称补全调用链。
- JD指导重点，不制造项目能力。不同仓库根据实际业务选择主题，不强套Agent、RAG或记忆模板。
- 同一机制的原能力与用户优化可合并一条，分别保留归属、实现状态和指标来源。
- 项目参考稿可选上游能力，不因缺个人贡献或数字而删光；个人稿亮点仍必须关联确认贡献。


### 写作结构示例（仅表达参考，禁止迁移事实）
结构：技术主题 → 具体约束 → 处理机制 → 异常/权限边界 → 有依据时补充结果。
假设材料明确支持“订单事件重复到达、唯一键拒绝重复写入”，可写“针对订单事件重复投递，通过唯一键约束限制重复入库”。不能据此添加吞吐提升或分布式事务。
假设材料仅支持“按角色过滤私有信息”，可写“按角色隔离可见信息”；只有运行时按事件重新选择上下文的证据，才能写动态上下文组装。
反向核查：动态对应什么条件？并行在哪里启动和汇合？长期记忆是否持久化、检索、更新？权限由程序执行还是仅Prompt要求？词语必须与证据强度一致。
