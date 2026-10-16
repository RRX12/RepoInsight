# 当前架构与开发定位

2026-10-14：中文本地单用户、单进程；仓库理解与优化讨论，简历生产链路已移除。开发规则见 AGENTS.md，预算见 PRODUCT.md，讨论存储见 memory/README.md。

## 优化规划 V2（2026-10-16，取代旧 PLAN→CHECK 流程）

生产入口保持architecture-runs → execute_architecture → optimization_review.generate。新增职责仅optimization_research（候选轮转调研／共享工具预算）及web_research（普通Tavily传输／公网正文），不增加调度或Agent。复用Harness、SharedAnalysisPack、SourceReader、CodeRetrieval、Run、Improvement及讨论记忆。准备完整匹配缓存复用；冷构建的PROJECT_CONTEXT/JD_PLAN/INVESTIGATE/SYNTHESIZE/CLAIM_VERIFY仍独立核验。优化不调用extend_analysis，不隐含追加事实模型阶段。

OPTIMIZATION_DISCOVER一次批量候选及动作 → 工具 → OPTIMIZATION_SYNTHESIZE → 必要时一次工具补查＋OPTIMIZATION_REFINE。语义上限3、优化尝试4、共享一次格式修复，单Harness保留全Run12次／250000已报告Token及160000字节单阶段保护。准备与优化按stage明确分账，failed也记请求；规划4000、综合／修订及其修复10000输出，创建Run时冻结OPTIMIZATION配置，ProjectModel最终传实际max_tokens并拒绝length截断。没有独立OPTIMIZATION_CHECK自动调用，历史trace继续只读。

V2契约在architecture_schema中与旧ArchitectureReport共存。legacy_direction只投影已验证V2方案到现有Improvement／讨论字段，不把旧报告标V2。源码source_id由宿主生成并绑定SHA／path／range／hash；重叠读取合并内容，保留稳定source_id和新hash。外部source独立kind，不经过source_map伪装Evidence.source_code。修改路径须已读，新增路径不得已存在，未知引用拒绝。候选全覆盖／合并、条件触发、路线及步骤无环、未验证测量均程序校验；不能证明语义真实性。

Tavily普通search使用固定https://api.tavily.com/search，basic、include_answer=false、auto_parameters=false、include_raw_content=text。已按[Tavily官方API](https://docs.tavily.com/documentation/api-reference/endpoint/search)核对，不假设搜索免费；credit usage未知留null。读取raw_content或仅已搜索URL；PublicTransport解析并核对全部DNS地址后直接连接已验证IP、TLS使用原hostname验签，无代理／二次DNS解析。逐跳校验、12秒、500KB、3次重定向，不执行JS。HTTP transport注入仅用于离线测试。搜索query拒绝URL／疑似凭证／资料原文片段，提示只用通用技术问题；不存在自动发送JD或完整源码的路径。

缓存位于既有cache_directory下advisor/工作区，成功规划可复用，最终报告24小时有效（含工具计划及实际来源hash记录），草稿不对外发布；advisor-web独立24小时缓存，可OPTIMIZATION_WEB_REFRESH=true强制刷新。不修改SharedAnalysisPack。check_active在每模型／工具前后及缓存发布／数据库保存前执行；用户约束随collect_project指纹，取消／更正拒绝旧结果。无数据库事务等待网络。Wiki先保存及中断／显式重试／占用释放沿用原任务。

前端AdvisorReport仅负责V2展示，OptimizationDirections仍负责原方案操作与浮窗。讨论只送有界目标／技术／取舍和引用摘要，proposal_hash覆盖完整details以检查晚到结果。旧schema兼容用途是历史报告与用户方向读取，只有历史消费者迁移后才考虑删除。

配置与启动见README；本次不重启或部署服务。回退此优化实现需恢复本轮相关源码／模板后重启后端，V2历史报告需保留读取器，不能删库恢复旧schema。真实模型／搜索召回和推荐质量未验证。

## 生产调用链

2026-10-15进度／历史：RunTiming复用Run.result.elapsed_seconds，新增analysis_started_at／analysis_finished_at／queued_at记录本轮时钟，无数据库迁移。worker启动和finally终态写入计时；取消即时冻结，finally不覆盖取消时间；重试清除旧计时但保留可重用Wiki。DELETE /api/analysis-history本地单用户全项目清理终态项目Run，逐项检查queued/running与still_executing，避免worker晚到写回已删除记录；不删除其余业务表或sidecar索引／缓存。前端清理后重新拉取当前工作区，目录和浮窗按当前Run消失正常卸载；原会话内容保留。删除后的旧run_id不再可用，幂等历史同步删除，新的分析应使用新幂等键。删除历史不意味着删除已独立保存的方向或其源码证据。

- frontend/index.html → main.tsx → architecture-entry.tsx：项目设置（仓库→可选岗位JD两步）、WikiOverview、OptimizationDirections；过程后台仅分析报告与 ProcessPanel，不再挂载简历/编辑/贡献生成工具。
- repository-link → SourceReader.resolve_revision → Snapshot：实际固定 SHA；解析失败不保存，不覆盖旧快照。
- architecture-runs → analysis.execute_architecture → DeepWikiOpen.wiki（先保存）→ project_inputs.collect_project → optimization_review.generate → shared_analysis → 原 ArchitectureReport/Improvement。岗位/JD可选，不增加第二套任务调度。
- shared_analysis：PROJECT_CONTEXT → JD_PLAN → 原始 CodeRetrieval → 固定版本 SourceReader 补读 → INVESTIGATE → 可选一次 SYNTHESIZE → CLAIM_VERIFY → SharedAnalysisPack。范围、证据、未知和索引身份一起传递，不依赖个人贡献或历史简历。
- FloatingChat → DiscussionChat → conversations API → 单主 LangGraph → discussion_context → wiki_chat 流接口 → finish CAS。复用原会话、停止、持久化、约束/笔记管理，聊天不能调用业务 mutation。
- OptimizationDirections → interaction state/mutations：版本化方向表单及原历史。讨论通过 Question.improvement_id 指向同工作区方案，begin 冻结服务端方向摘要及指纹，finish 再读并比较；更正/删除拒绝旧答案。方向上下文进入原 evidence 信封和预算，不作为已实现源码证据。

## 当前职责

### 动态向量准备（2026-10-15）

复用Index.prepare／vectors及内容缓存，增加有界调度窗口和ThreadPoolExecutor。先dry-run检查unique缺失数，auto使用WIKI_RAG_AUTO_VECTOR_LIMIT（默认10000，契约上限100000），reuse_only仍使用max_new_vectors。同输入跨位置只派发一次、跨快照复用向量；每键弱引用锁避免并发重复请求而不串行化不同输入。每窗口默认32、并发2（最多8），单输入请求复用原native embedder，每次get_embedder建立独立实例；没有引入未经验证的供应商批量API。失败／取消先停止排队动作并回收线程，已完成向量可继续复用，取消晚到向量不发布，整索引不会以半成品成功。查询／来源规则及FP/SHA守卫保持。

已有manifest会重新核对向量缓存，缺失时按同规则恢复；相同完整索引直接复用。新增loopback GET /repocareer/wiki/progress?task_id读取TaskRegistry同一任务的进度，或独立无正文checkpoint；主服务轮询时记录deepwiki_index摘要，用户页显示计数。checkpoint记录输入数／剩余数和成功持久化数量，失败调用计费未知，usage不报零。auto主等待上限默认7200秒，超时使用原取消句柄；服务重启无自动付费恢复，重试利用已有向量。

结构索引完整后发布repo+SHA+embedding FP的wiki-ready指针。原 /repocareer/code/prepare优先验证并复用该manifest，原search由index_id选择对应splitter版本并将结构元数据投影回既有严格Hit协议，优化CodeRetrieval不用更换接口、不重复创建旧line splitter向量；旧raw-code-v2仍支持，未知ID／错SHA／错FP明确拒绝。ready只指向完整manifest，依赖文件hash及来源校验不放宽。

配置WIKI_RAG_INDEX_MODE=auto、AUTO_VECTOR_LIMIT=10000、INDEX_CONCURRENCY=2、INDEX_BATCH_SIZE=32、INDEX_TIMEOUT=7200冻结到Run及sidecar键；本机在用户授权动态补齐后已持久启用。原WIKI_RAG_MAX_NEW_VECTORS=0在reuse_only模式才控制新向量，auto使用独立统一上限。历史reuse_only任务不能以安全重试继续旧策略，提示新分析；同auto任务则可利用缓存继续。回退index_mode=reuse_only并重启8000恢复只复用缓存，旧新索引和进度文件保留。免费额度／限流／真实吞吐未验证，默认离线仍不调用真实服务。

### Wiki RAG 增强接线（2026-10-15）

原生产链实际为 `DeepWikiOpen.wiki → POST /wiki/tasks → generate_repo_wiki → _determine_structure / _generate_page → research_chat`；页面完整写作Prompt被research_chat作为隐式RAG查询。保留legacy链用于兼容／对照，不删除unknown版本Wiki。增强沿用TaskRegistry、原目录XML解析、并发页面任务及取消句柄，在原generate_repo_wiki与_generate_page内分支，写作仅接收显式证据包，不再调用research_chat。增强失败不生成旧错误占位页，pages_done与pages_succeeded分别计处理结束和有效页面；有效但有限的页面仍标limited，不称覆盖完整。页面并发失败会取消并回收其他子任务。

新增结构解析、严格契约、章节有界循环和sidecar钩子分别解决准确偏移／工具权限／证据补查／实际生产接线四个问题，没有第二套调度、Agent框架或数据库。复用原raw Index内容哈希缓存、native LocalDB同配置同完整输入向量、FAISS、RRF60、过滤器及固定Git对象／官方SHA archive读取；未引入BM25。旧raw-code-v2消费者保留，新结构配置进入manifest身份并独立不可变保存，原索引不就地改写。每段记录repo/SHA/file hash、精确UTF-8字节和行号、parser/splitter版本／fallback，未知解析语言显式退化。

`scripts/wiki_rag_contract.py`纯数据契约供后端冻结环境配置、sidecar及离线测试复用；安装时复制到sidecar api命名空间。四个白名单模板在backend/prompts/wiki，实际模型加载，模板哈希进入缓存。`wiki_rag.py`负责章节内计划／检索／区间去重／父结构补齐／覆盖／最多两轮补查／直接写作；read_range、read_symbol、search_exact、search_semantic是唯一工具，源码是数据。不同版本不合并；长父函数只补独立头部与局部片段并标不完整。readme／目录规划线索有截断数量记录。

后端Run冻结mode、版本和预算；取Wiki前后及落库事务内检查当前项目指纹。增强请求追加revision、workspace_id、snapshot_id、wiki_options，不改变旧chat字段。sidecar任务键含配置／模板／parser／model，索引另绑定embedding指纹及文件hash，章节绑定index/plan/page/model/prompts/budgets/工作区快照。全Wiki和章节缓存位于DeepWikiRoot/repoinsight-enhanced-wiki，与旧wikicache分离；新loopback `/repocareer/wiki/cache?task_id=...` 和 `/repocareer/wiki/tasks/{id}/cancel`复用TaskRegistry。服务重启仍由主Run原interrupted机制恢复；内存任务不跨进程恢复，重试重建目录并复用已经完整核对的章节。旧无版本缓存不能命中增强。新字段generated_pages和retrieval保持旧UI读取兼容；WikiOverview显示limited及语义验证边界。

增强ExplicitModel暂仅DeepSeek：复用ChatStreamer，设置SDK max_retries=0和实际max_tokens，每次请求／修复计预算，无隐式无证据fallback。其他adapter现有隐式重试与参数差异未逐一验证，因此增强显式拒绝；legacy照常支持。GitHub公开SHA可用，上传local/archive身份当前显式不支持增强。原问答及优化调查未改为这套Wiki循环。Token估算用UTF-8字节上界，API usage未知保留null；索引／查询输入计数不能当作服务实际计费Token，native embedder内部重试计费仍需服务观测。

安装只支持DeepWiki基线 `d92819a9c9f3b99416e3580ff235fc9d3adf8b89` 与已有deepwiki-local.patch；版本、精确钩子锚点、编译、安装hash记录防止覆盖未知钩子变更。raw-only安装保持可用。P0–P5实现阶段只在临时克隆验证；2026-10-15用户随后明确授权启用，本机补丁／解析依赖已安装，.env显式设置enhanced与新向量预算0，两个服务已重启、前端已构建。具体恢复记录见STATUS。

模式切换后，历史Run仍保留原冻结配置；retry接口拒绝不同模式的旧任务，返回409并提示在项目设置发起新分析，避免安全重试仍调用legacy。不改写历史请求或复用旧Wiki冒充增强。新任务由当前enhanced配置创建。默认离线检查与legacy测试fixture显式隔离到legacy，增强测试自行指定enhanced，不随用户本地.env改变；这是测试环境隔离，未放宽增强门禁。

操作员启用步骤（需准备服务依赖及明确向量预算）：

```powershell
data/deepwiki-venv/Scripts/python -m pip install -r scripts/deepwiki-requirements.lock.txt
.venv/Scripts/python scripts/install-deepwiki-retrieval.py --sidecar data/deepwiki-open --wiki-rag
# 在已有本地Git缓存或显式源码checkout上dry-run，不下载、不调用embedding：
data/deepwiki-venv/Scripts/python scripts/wiki-index-dry-run.py --sidecar data/deepwiki-open --repo OWNER/REPO --revision FULL_SHA --source C:/path/to/existing/checkout
```

确认dry-run所需新向量后，显式设置WIKI_RETRIEVAL_MODE=enhanced、DEEPWIKI_PROVIDER=deepseek、允许的新向量数WIKI_RAG_MAX_NEW_VECTORS（默认沿用CODE_INDEX_NEW_VECTOR_BUDGET=0）。需分别按现有单进程命令重启sidecar和后端，使新代码／配置生效；前端需正常构建才显示范围提示。切换会产生新任务身份，不能用旧幂等键冒充同输入重试。模型／embedding实际可收费，预算0遇到缺失会在任何embedding前失败。

回退：设置WIKI_RETRIEVAL_MODE=legacy并重启后端，保留sidecar加法钩子、旧新索引及历史Wiki，不删除数据库或撤销源码；旧索引格式不变。旧Wiki兼容路径只有在真实固定SHA样本评估通过、其他adapter与上传迁移完成且所有调用方确认后才能删除；此次不切默认、不移除legacy。完整安装依赖锁定Tree-sitter 0.25.2、Python 0.25.0、JS 0.25.0、TS 0.23.2，沿用现有锁文件，不增加第二份。

离线额外验证：`data/deepwiki-venv/Scripts/python scripts/test-wiki-rag-sidecar.py --sidecar data/deepwiki-open`，`scripts/test-deepwiki-retrieval.py`同参数，评估命令见evaluations/wiki-rag-offline.md。侧车测试只复制临时克隆，模型／embedding外部I/O为fake；默认check.py含纯契约／行为测试，sidecar依赖验证单独执行，不伪称安装服务已验证。

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

新建工作区与保存岗位JD使用function作用域事务依赖，响应发送前提交；避免客户端随即保存仓库或刷新目标时读不到刚保存的数据。repository-link和方向mutation保持原先提交语义。


2026-10-15章节补查改原生tool calling：ExplicitModel在coverage_review单次非流式DeepSeek请求传tools与tool_choice=required，注册submit_review及四个读取／检索工具。同响应必须一份审查、最多三个动作，decode_review_calls转换到原Review／Action契约，再经Chapter.validate_review与tool路径／SHA／预算检查执行，下一轮输入执行证据。拒绝未知工具及非法参数；不放宽guard，不增加模型轮次，SDK重试0、finally关闭client；工具schema计入实际输入预算。正文仍原流式写作，图示与引用逻辑保留。提示hash隔离旧章节缓存。仅增强DeepSeek生产支持；离线注入文本模型保留用于基线测试，不作为生产fallback。

覆盖审查中的gap.importance由宿主按冻结问题question_id继承；模型不拥有修改问题优先级的权力。未知问题、重复缺口及错误动作关联继续由原校验拒绝。

正文引用列表允许宿主移除已知且未在正文使用的冗余ID并记录处理；不新增引用、不改正文，不接受未知ID／正文漏列／无引用。


原生工具流程v2：coverage_review先仅注册submit_review并指定函数tool_choice，验证唯一审查；有开放缺口且未finish时以独立请求注册四个补查工具、tool_choice=auto。工具参数再经原Review／Action／身份／路径guard。额外请求由Chapter回调单独扣本章及任务模型预算、记录extra_tool_selection_requests、预留正文一次调用；取消检查在第二请求前执行，client finally关闭。实际工具schema和审查结果计入输入预算；不存在隐式额外无预算请求。两步增加开销，预算不足时按既有限定输出处理，不承诺质量不变。


启动脚本：scripts/start.ps1首次创建venv并使用既有锁文件安装应用依赖、构建前端；-Install用于更新依赖与产物，-SetupOnly不启动服务。.env仅缺失时复制；DeepWiki独立首次安装及系统依赖步骤见README，不隐式安装系统软件或调用模型。

V2允许仅候选取舍报告：无prioritize、每项rationale完整时可由宿主汇总no_change_reason；不替代模型取舍，不为缺方案的优先项放行。

优化报告Overview由prepared_overview从既有ProjectValue与当前已读来源映射，不再在综合调用中重复生成；空关系明确未知，方向源码引用仍严格核验，不把目录提及路径作为已读依据。

优化页按当前Run的improvement_ids／run_id展示系统建议，历史系统项默认隐藏并须显式展开，用户保存方向不受轮次过滤。页面展示当前分析编号、时间与报告发布状态，避免最新失败时旧摘要冒充新报告。缺触发条件的conditional保守降为validate_first并列入未确认项，不猜测条件或视为可执行推荐。
