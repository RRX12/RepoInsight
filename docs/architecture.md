# 当前架构与开发定位

当前为单后端进程、本地单用户 MVP。开发规则统一在 AGENTS.md；本文件记录当前结构，历史取舍见 DECISIONS，验证与恢复见 STATUS。

## 生产入口与核心调用链

| 入口 | 实际调用链 |
|---|---|
| 用户页面 | frontend/index.html → main.tsx → architecture-entry.tsx；项目设置、WikiOverview项目全貌/向项目提问、OptimizationDirections、ProjectIteration编辑器；过程后台复用ResumeHarness |
| GitHub快照 | main.repository-link → SourceReader.resolve_revision → Snapshot，绑定实际SHA；解析失败明确unresolved |
| 架构任务 | architecture-runs → analysis.execute_architecture → DeepWikiOpen.wiki（立即保存）→ project_inputs.collect_project → optimization_review → shared_analysis → 原ArchitectureReport/Improvement |
| 共享调查 | PROJECT_CONTEXT（README/目录）→ JD_PLAN → CodeRetrieval → 目标版本SourceReader补读 → INVESTIGATE → 可选一次SYNTHESIZE → CLAIM_VERIFY → 不可变SharedAnalysisPack |
| 模型简历 | main.new_artifact → artifact_service.create_artifact → collect/GenerationContext → resume_writer.write → resume_quality.generate → 共享包/贡献关联 → SELECT → WRITE → 独立REVIEW_HR/TECHNICAL → 最多一次修订和双审 → render → 保存前指纹/CAS核对 → Artifact/Run |
| 交互重新生成 | interaction_service.generate → 同一artifact_service → 待接受proposal → decide → 新正文版本；不自动覆盖编辑器 |
| 规则参考 | writing_mode=reference → memory.compose_project_resume；明确演示/参考，无模型失败降级 |
| 项目问答/讨论 | WikiOverview / ProjectIteration → DiscussionChat → conversations API → 单主LangGraph plan/source → discussion_context → wiki_chat流接口 → revision核对/存储；无业务写权限 |

优化请求不运行简历写作；简历请求无需等待一个ArchitectureReport。架构入口可先生成学习Wiki，但共享服务没有这个依赖。原始检索绝不使用/ws/chat或生成式回答代替代码片段。

## 职责和依赖

- project_inputs：项目概况契约及纯项目输入快照，只收集仓库/JD/明确标注的项目事实更正。无Run、编辑正文、贡献、报告依赖。当前更正来源为`用户确认的项目分析更正`；一般用户口述保留在简历贡献材料，不自动改变源码事实。
- code_retrieval：原始HTTP契约、身份/哈希检查、固定版本重读。source_reader继续负责只读GitHub/上传快照、路径安全、缓存、范围搜索；不执行代码。
- shared_analysis：一次有界调查、事实核验、共享包缓存；已确认执行流程、证据池和未知共同传递。候选主题可关联多个JD，合并按机制链而非同名关键词。它不导入analysis执行器或resume_quality。
- optimization_review：只消费共享事实，生成建议并独立检查必要性/既有解法/证据；允许零建议。最多一次修复；未经再次语义审查的修复报告标pending，推荐降为conditional。建议绝不回填为已实现Claim。
- resume_quality：贡献绑定、全局选材、写作、独立双审/反馈路由；resume_contract是契约/确定性校验/render；resume_revision保留引用补丁、候选演进、事实门禁和评分。
- resume_support：简历材料收集/账本、WritingModel/缓存配置；共享概况类型从project_inputs导入兼容旧消费者。resume_harness只有通用预算/阶段缓存/用量日志，不再负责Wiki映射。
- resume_prompts：固定角色白名单、模板版本/哈希、输入投影，技术调查使用Analysis含next_reads，但无自主工具权限；程序执行验证后的读取。写作Skill只供WRITE。
- main负责HTTP；artifact_service负责准入和原子保存；analysis负责架构任务生命周期；memory负责贡献/JD/Evidence/历史及依赖失效。公共契约不能经本地导入回到这些业务编排。

## 缓存、版本和预算

原始索引manifest包含仓库、SHA或上传内容哈希、embedding配置指纹、维度、分块配置、文件哈希、原文范围。同文本/配置向量可复用，不凭文件名复用。匹配配置命名空间中的原生LocalDB向量按原文复用；无可靠命名空间时不追认旧向量，需显式新向量预算。使用sidecar现有FAISS，归一化点积为cosine；与词面排名用RRF(60)融合，保留原cosine及各自rank，融合分不是事实置信度。读取命中后仍校验目标SHA原文。

显式prepare与只读search分离；search不会重建。Git对象不存在或原缓存仅为archive时，prepare可读取固定SHA的官方codeload压缩包，内存限额、不解压执行、不覆盖sidecar工作树。索引只覆盖允许文本类型/大小，遗漏路径保留。历史上传快照走既有只读哈希验证，传入显式prepare；无用户贡献也可形成项目分析。

共享包按工作区/快照/索引身份/JD/岗位/调查维度/项目更正/角色模板/模型及schema版本区分，内容哈希校验，原子发布。下游失败不损毁已核验包。个人贡献、指标、手工编辑、所选未来计划不失效纯项目包；但都进入简历材料指纹。缓存命中仍检查取消及契约。补读派生新包带parent_id，不原地改变已消费包。

- 简历总请求默认20，配置8–24；优化总请求12。格式/引用修复每请求合计最多一次，不为各阶段重置。
- 写作+双审预留3次；修订必须还有3次。默认JD最多6项，每项2短查询；初次12，补查最多4，补读全程共一轮。
- 源码工具32调用，12文件（RESUME_SOURCE_FILES最大16）、摘录30000字符；不同JD轮转取命中，记录未读。单阶段160000 UTF-8字节；过限失败，不截掉尾部冒充完整。
- `CODE_INDEX_NEW_VECTOR_BUDGET=0`默认只复用；显式提高允许准备新向量，查询embedding另外计数。LLM/代码embedding/query embedding分列；未知token为null，不把历史缓存用量算成本次消耗。
- 同源双审不是独立人工认证；首稿/修订稿评分绑定draft_hash，安全过滤后不能沿用过滤前认证。不得以分数覆盖事实、归属和指标错误。

## 任务状态与历史兼容

架构Wiki先保存，优化失败重试沿用Wiki和有效共享包；保存报告前比对纯项目指纹，排除报告自身而不自我失效。source_paths限定本次已读源码；临时code ID在保存时登记为工作区/快照Evidence，Improvement保存数据库source_evidence_ids及analysis_pack_ref。原external_analysis_evidence_id仍指向Wiki，不能冒充源码认证。

简历继续同步请求占用工作区准入、短事务、幂等键与材料指纹；取消在后续阶段/保存前生效，已发HTTP无法撤回。/retry不重投同步简历；原产物命令可重试，材料变化用新标识。启动恢复标interrupted，不自动重放付费请求。无Wiki时run_id可null，但不会写入依赖ID集合。

交互仍使用InteractionState revision+材料哈希CAS、mutation_id回执与MemoryEvent；接受/拒绝proposal、人工保存、恢复版本、指标口径、贡献撤销保持原语义。前端本地未保存正文不被服务器覆盖。当前用户只选择自己保存的完整优化方向；系统建议只读提供思路，选择不代表实现。

| 保留项 | 用途及退出条件 |
|---|---|
| 历史Artifact/Run/audit | 只读显示/导出；v6显示共享索引与分析包，旧版保留原映射展示，不补认证；确认迁移后再退役 |
| 缺省writing_mode=reference、规则/AST演示 | 明确兼容API/离线参考，不是模型降级；另行确认外部消费者退役 |
| repository-upload、archive SourceReader | 旧API/快照；不删除历史文件，确认API退役与迁移后再删 |
| 旧/messages、单选select及管理工具 | 历史客户端；select委托统一mutation，不能形成第二套状态 |
| ReferencePatch候选claim_ids→refs | 现有模型同义字段兼容，冲突/未知字段仍拒绝；真实回归证明可移除再清理 |
| DeepWikiOpen.chat | 无当前讨论调用方；上游适配器历史方法不作为新的生产入口，源码检索不得调用生成式chat |

已删除resume_legacy、write_legacy桥、resume_index、Harness.map_wiki及DeepWikiOpen.review大段Wiki拼接。旧评测只读文件比较，无第二条可执行模型链路。

## 原始检索扩展安装

受支持sidecar提交：`d92819a9c9f3b99416e3580ff235fc9d3adf8b89`。先按原`deepwiki-requirements.lock.txt`和`deepwiki-local.patch`恢复本地DeepWiki（不覆盖服务.env）。新增依赖为零；原生FAISS/numpy/adalflow由sidecar已有锁文件提供。

```powershell
.venv/Scripts/python scripts/install-deepwiki-retrieval.py --sidecar data/deepwiki-open
```

脚本校验Git基线/必要函数、复制两个受版本管理模块并注册路由，重复执行幂等；不启动服务，不调用模型。基线不符需先审查适配，不跳过校验。新接口：POST `/repocareer/code/prepare`、`/repocareer/code/search`，仅loopback。之后在明确部署时重启sidecar，应用配置DEEPWIKI_BASE_URL指向API端口（本机8002），不使用网页3000端口。

默认新向量预算0；现有原生块不能全复用时，prepare会明确失败。查明覆盖/缺块后再给`CODE_INDEX_NEW_VECTOR_BUDGET`设置本次允许的块数，可能产生embedding费用；不要靠search隐式重建。未知SHA的历史快照需重新保存仓库链接解析版本，不能使用旧Wiki冒充当前源码。

隔离真实扩展验证（不安装、不改现有索引、不调用付费模型）：

```powershell
data/deepwiki-venv/Scripts/python scripts/test-deepwiki-retrieval.py --sidecar data/deepwiki-open
```

该检查使用实际LineTrackingTextSplitter、LocalDB、FAISS和ASGI路由，临时自建Git仓库+假embedding。未安装sidecar依赖时明确失败，不把普通MockTransport测试当作此项通过。

## 常见修改与验证

| 修改场景 | 修改位置及消费者 |
|---|---|
| 主题数量/格式 | resume_contract、resume_quality、Skill和ResumePreview；更新公共契约回归，不机械绑定文件位置 |
| 模型客户端/预算 | resume_support.WritingModel、resume_harness及配置示例；两分支共用；wiki-chat是不同协议 |
| 新证据来源 | SourceEvidence/CodeRetrieval或SourceReader、共享证据校验、账本/Evidence映射、前端审计；不能直接当用户贡献 |
| 取消/重试/轮询 | task_lifecycle/analysis/artifact_service、main公共API、前端轮询；保留CAS/幂等/停止后不可落稿回归 |

启动：`.venv/Scripts/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`（单进程）；前端`pnpm --dir frontend run dev`。使用backend/requirements.lock.txt与frontend/pnpm-lock.yaml，不引入第二套锁文件。

统一本地/CI：`.venv/Scripts/python scripts/check.py --e2e`；可用`--pnpm <路径>`。包括标准库架构检查、后端pytest、前端类型/临时构建及8001/5173离线Playwright，不替换生产dist/数据。小改可定向pytest；sidecar集成用上面独立命令。CI远端保护未变更，实际远端执行不能用本地结果代替。

A01禁止生产依赖旧legacy/桥（无例外）；A02公共契约沿导入图不得抵达编排（含shared_analysis/optimization_review）。测试制造违规并验证识别。动态反射、源码语义、质量和架构必要性仍靠人工判断，不能为了通过检查弱化规则。

实际使用的Codex已注入根AGENTS，本轮主动重读。其他AI工具不假定自动读取：新任务要求先读根AGENTS，按范围定位实现/消费者，报告复用、新增理由、旧实现处置、影响及验证。维护规则只保留在统一入口，不复制多份Skill或审批流程。

### JD来源绑定
JD_PLAN使用程序生成的逐行jd_sources，模型选择jd_source_ids，程序回填original_excerpt/origin；编号仅对应当前冻结JD，缓存键包含jd_plan_version。旧精确摘录仅在唯一行匹配时兼容，不做模糊匹配。未知编号走既有一次修复，不能自动补成事实。

参考稿评审：contribution_gap独立于fact_attribution；project_reference缺少个人贡献仅提示，不能阻断项目亮点。真实错误归属仍走事实核验，不因参考稿模式豁免。


## 讨论记忆边界（2026-10-14）
- `discussion_contract`只含公共数据契约；`discussion_memory`使用原Message/MemoryEvent和新增Conversation；`discussion_context`只组装/搜索，`discussion_service`持有单主LangGraph和外部调用。不依赖interaction业务mutation，也不调用简历入口。
- Conversation.data保存主题、当前记忆投影、幂等回执和限量源码缓存。Message.proposal.discussion保存turn/request/状态/来源/加载记录。独立SQLite FTS5 trigram存全文检索索引；不可用时显式关键词回退，不引入新依赖。当前实现扫描工作区Message后按会话筛选，适合本地单用户；数据量扩大后再以实测升级索引列。
- 只有短写事务受进程锁+revision CAS保护；模型/HTTP在事务外。pending阻止同会话并发发送，更正使旧结果失效。取消可主动关闭异步问答HTTP，源码/解析的同步请求可能先返回，但不能提交旧结果；上游是否停止计费未知。启动把pending标失败，不自动重试。
- 不再用每消息LangGraph checkpoint复制历史；数据库是唯一会话真源。删除清理旧workspace:message检查点、FTS、派生事件及缓存；旧业务审计含相关消息时脱敏。项目无现成删除API，因此提供`DELETE discussion-memory`清理本模块，不伪装为项目业务删除。
- 旧`POST messages`、`POST wiki-chat`、`POST interaction/chat`返回410引导刷新，不保留第二条聊天生产路径；GET messages只读兼容。旧DiscussionResult/自动mutation提示和旧Agent工具循环移除，agent.py保留Skill注册表供原写作/编辑入口复用。410占位供旧网页诊断；下次确认旧客户端不再使用时可移除。
- 改讨论展示：DiscussionChat；改记忆规则/删除：discussion_memory；改预算/召回：discussion_context；改解析与源码策略：discussion_service；改API公共字段时同步两个前端入口和M01–M20。继续使用统一`scripts/check.py --e2e`，离线上下文比较另运行`scripts/eval-discussion-memory.py`。
- Alembic003仅在隔离数据验证，本次不迁移生产库；将来获准启动新版时由现有migrate自动执行。旧数据不丢弃、明确legacy；旧记录不当作完整成功轮次。
