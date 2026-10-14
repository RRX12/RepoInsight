# 当前架构与开发定位

2026-10-14：中文本地单用户、单进程；仓库理解与优化讨论，简历生产链路已移除。开发规则见 AGENTS.md，预算见 PRODUCT.md，讨论存储见 memory/README.md。

## 生产调用链

- frontend/index.html → main.tsx → architecture-entry.tsx：项目设置（仓库→可选岗位JD两步）、WikiOverview、OptimizationDirections；过程后台仅分析报告与 ProcessPanel，不再挂载简历/编辑/贡献生成工具。
- repository-link → SourceReader.resolve_revision → Snapshot：实际固定 SHA；解析失败不保存，不覆盖旧快照。
- architecture-runs → analysis.execute_architecture → DeepWikiOpen.wiki（先保存）→ project_inputs.collect_project → optimization_review.generate → shared_analysis → 原 ArchitectureReport/Improvement。岗位/JD可选，不增加第二套任务调度。
- shared_analysis：PROJECT_CONTEXT → JD_PLAN → 原始 CodeRetrieval → 固定版本 SourceReader 补读 → INVESTIGATE → 可选一次 SYNTHESIZE → CLAIM_VERIFY → SharedAnalysisPack。范围、证据、未知和索引身份一起传递，不依赖个人贡献或历史简历。
- FloatingChat → DiscussionChat → conversations API → 单主 LangGraph → discussion_context → wiki_chat 流接口 → finish CAS。复用原会话、停止、持久化、约束/笔记管理，聊天不能调用业务 mutation。
- OptimizationDirections → interaction state/mutations：版本化方向表单及原历史。讨论通过 Question.improvement_id 指向同工作区方案，begin 冻结服务端方向摘要及指纹，finish 再读并比较；更正/删除拒绝旧答案。方向上下文进入原 evidence 信封和预算，不作为已实现源码证据。

## 当前职责

保留并按职责重命名原共用实现：resume_support → model_support（模型 HTTP/配置），resume_harness → analysis_harness（请求预算/用量/阶段缓存），resume_contract → analysis_contract（事实、候选与核验契约），resume_revision → analysis_revision（不可变候选演进与引用修复），resume_prompts → analysis_prompts（技术调查白名单模板）。技术模板从 prompts/resume 移到 prompts/analysis；写作、HR和简历评分契约移除，项目分析包版本改为 project-analysis-v1，旧缓存不追认新身份。

删除 resume_writer、resume_quality、artifact_service、规则 compose/compose_project_resume、简历专属同步 admission/task_lifecycle、写作 Skill/HR选题及双审模板、编辑/生成/审查/接受 API、前端 Discussion/ProjectIteration/ResumeHarness/ResumePreview 和简历评测脚本。未删除 Artifact/Contribution/Experiment/InteractionState 数据模型与 Alembic 历史；业务更正继续使历史记录待复核。历史简历任务只读，retry 拒绝执行，GET Artifact/export 保留直到用户明确要求数据迁移或删除。

FloatingChat 是本轮唯一新 UI 职责：统一两页的窗口拖动、调整尺寸、收起与视口约束。无需新聊天服务/框架/依赖，DiscussionChat 仍负责会话与流。WikiOverview 左侧目录和当前章节使用现有 Wiki 数据。离开页/切换工作区的组件卸载主动 abort 并发送 cancel；收起不卸载。

## 配置兼容

优先 PROJECT_MODEL_ENV_FILE/API_KEY/BASE_URL、PROJECT_MODEL，默认复用 data/deepwiki-open/.env 的 DeepSeek 配置，默认 deepseek-v4-pro，与 DeepWiki 问答模型独立。PROJECT_ANALYSIS_CACHE_DIR、PROJECT_MAX_REPORTED_TOKENS、PROJECT_DISCOVERY_MAX_TOKENS、PROJECT_SOURCE_FILES 控制共享分析。原 RESUME_同名字段仅作本地配置兼容，避免已有 .env 失去服务；不保留简历调用入口。删除条件：用户完成配置迁移并确认旧脚本/部署配置无消费者。原错误 code 暂保留，中文错误已改为项目分析，避免未知 API 客户端错误处理失效。

原始索引 manifest 继续包含仓库/SHA、embedding配置、维度、分块及文件哈希。原生 FAISS/词面 RRF、固定版本重读、源码路径安全、默认0新向量预算不变。prepare 和 search 分离，未知 Wiki 版本不能替代源码。共享包按工作区/快照/索引/JD/关注点/更正/模板/模型/schema 键分离，已核验包下游失败仍保留。

## 任务与讨论边界

单工作区 queued/running 架构任务互斥，ThreadPoolExecutor 单工人；取消后必须等待执行释放才可重试。服务重启恢复 interrupted，不自动重复模型请求。旧 resume_generation 标记仅供阻止历史任务重试，不再创建新简历 Run。

Conversation/Message/MemoryEvent 和 SQLite FTS5 是讨论真源，pending 防同会话并发，短事务进程锁/revision CAS，不在模型 HTTP 中持有事务锁。会话删除、项目记忆清理、约束更正、方向版本变化和 late result 均保持隔离。DeepWiki 内部token/索引版本/取消计费未知，详见 memory/README.md。旧 POST messages/wiki-chat/interaction/chat 的410诊断保留，不构成第二条生产路径。

## 命令与验证

后端：`.venv/Scripts/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`；前端：`pnpm --dir frontend run dev`。依赖使用 backend/requirements.lock.txt 与 frontend/pnpm-lock.yaml，pnpm 版本见 packageManager。

统一离线隔离检查：`.venv/Scripts/python scripts/check.py --e2e`，含 A01/A02 架构、全部后端、类型、临时构建和 Playwright（8001/5173）。现存源码安全、事实核验、候选演进、缓存、幂等、隔离、取消/更正/删除/晚到结果测试迁移到项目入口；仅简历专属写作/评分/编辑测试随功能退役，不通过放宽事实 guard 换取通过。旧历史数据测试直接插入历史 fixture，不调用已退役生成 API。

DeepWiki 原始检索扩展仍用 scripts/install-deepwiki-retrieval.py --sidecar data/deepwiki-open，支持 sidecar d92819a9c9f3b99416e3580ff235fc9d3adf8b89；既有锁文件/配置不变。隔离实集成：data/deepwiki-venv/Scripts/python scripts/test-deepwiki-retrieval.py --sidecar data/deepwiki-open。未经授权不扩大向量预算、不调用付费模型。

### 分步设置与岗位JD修改（2026-10-14）

复用原repository-link、target及architecture-runs，不新增API/模块。仓库保存成功才进入JD步骤；跳过通过target明确保存空JD与通用关注点，再调用同一分析入口。头部修改窗口保存仅调用target，历史JD及旧报告保留；切换项目和新建时清理修改窗口，运行中禁止修改。用户页不显示过程后台链接，/?view=admin仅留直接排查路径。

### RepoInsight命名兼容（2026-10-14）

当前品牌、包名、文档、启动提示和新本地根目录改为RepoInsight。新SQLite文件为repoinsight.db，旧repocareer.db存在且新文件不存在时兼容读取，避免创建空库；本地旧数据经SQLite backup迁移到新名。浏览器优先repoinsight.workspace，兼容旧repocareer.workspace，用户选择后写新键，新项目清理两键。REPOINSIGHT_DATA/DEMO/API_TARGET优先，REPOCAREER字段只用于旧配置迁移。

既有DeepWiki扩展的/repocareer/code路由、repocareer_raw_index/routes模块及缓存目录属于独立安装协议，继续保留，不因显示品牌改变而破坏已装sidecar。确认旧安装全部迁移后再协同改协议；不是另一个产品或生产链路。历史文档、快照来源、日志及Git记录保留原品牌出处。
