<!-- chapter_plan-v1 -->
只规划本章调查，不写正文。根据章节标题、候选路径和有界定位材料提出1–4个互补问题，至少一个core，每问题最多一条短semantic_query。路径和符号只是定位线索，README功能和目录名称不是源码事实；假设明确标为待验证。检索查询不能含语言、Mermaid、表格、字数或写作指令。重复问题合并，不自动生成同义查询列表。Chapter身份保持输入值。

输出必须为可直接交给ChapterPlan校验的纯JSON对象，严格遵循附带JSON schema。不要输出```json或任何Markdown围栏，不要解释。chapter_id与title逐字保持输入值；不得添加schema之外的字段。
