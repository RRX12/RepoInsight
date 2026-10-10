# 项目简历写作契约

写作目标：清晰表达业务对象、具体机制、岗位价值及真实贡献。STAR是内在逻辑，不必打印S/T/A/R标题，也不强制四部分齐全。

ResumeDraft结构：output_mode、project_intro{text,claim_ids,contribution_ids,metric_ids}、bullets[{id,title,text,candidate_ids,claim_ids,contribution_ids,metric_ids}]、outcome（可null）、questions、limitations。

项目简介约60–130字，说明业务对象和核心任务，交代必要技术背景；亮点通常2–4条、每条1–2句，约60–140字。具体问题/约束→关键机制→代码支持的行为或有依据结果；动机、取舍没有材料就留空。成果仅在有独立信息时写，不重复简介。

两种产物：项目参考稿介绍上游，个人简历需要确认个人行动。可以同主题提及原有机制和个人改动，分别关联claims，不自动把上游归用户。未实现计划、预估和待核实问题不进入正文，放外部面板。

不强制指标，不复制其他简历的技术和数据。用户报告的指标必须明确测量口径、样本、环境和来源；没有报告可写“拒绝过期更新”等支持的行为，不能推导性能收益。删除重复、泛化价值、端口/文件名等低价值细节。

材料不足不等于能力不存在。角色记忆不等同用户记忆，词面召回不等同语义RAG；保留独立项目全貌，岗位只影响调查和选材，不改变技术栈或定位。

## 研究来源（借鉴原则，不照搬例句或数字）
- Harvard Mignone Center for Career Success：事实导向、展示结果、简洁易扫读：https://careerservices.fas.harvard.edu/resources/create-a-strong-resume/
- Yale Office of Career Strategy：动作、背景与结果组成成就条目：https://ocs.yale.edu/resources/writing-impactful-resume-bullets/
- University of Michigan-Dearborn：STAR与Power Verb + What you did + Results/Purpose：https://umdearborn.edu/career-services/job-and-internship-prep/resumes-and-cover-letters/how-create-strong-resume-bullet
- 公开project-resume-writer的选材与最终审查流程：https://github.com/oxygen914/project-resume-writer/blob/main/SKILL.md
