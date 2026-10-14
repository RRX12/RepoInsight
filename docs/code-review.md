# 2026-10-13 实施补记：JD 共享源码调查

本轮按新的明确任务书替换，旧审查历史保留；以下表取代历史表中对应路径的当前处置。

| 实现 | 当前处置及证据 |
|---|---|
| resume_writer.write/resume_quality | 保留唯一公共入口和下游事实/归属/选材/写作/双审；上游接shared_analysis；首次和交互生成共用 |
| resume_legacy/write_legacy/compare-legacy | 删除执行代码、桥和CLI；旧输出文件只读，A01无桥例外 |
| Harness.map_wiki/Fact/Mapping/chunks/spans | 删除旧专用逻辑，保留预算、JSON、阶段缓存、usage |
| resume_index | 删除全Wiki词面召回；原始代码检索由版本manifest+原生分块/FAISS/RRF负责 |
| DeepWikiOpen.review/PROMPT | 删除Wiki大段拼接；优化消费共享包。wiki/chat有实际消费者，保留 |
| ProjectValue/项目输入 | 中性project_inputs被两分支复用；原support类型导入兼容，无第二套实现 |
| 规则参考、旧ZIP/讨论、历史audit | 有真实消费者，保留既有作用；未删历史数据或exports |

测试处置：退休旧Markdown正则选题、Wiki字符分块/词面邻居与旧review两次重发专用测试；不是把失败断言改为通过。原Skill传入、独立双审、修订上限、未知引用、指标/计划/归属、生命周期/CAS/幂等有效保护迁至或继续由test_resume_quality/mechanisms/shared_analysis/interaction/cleanup_lifecycle覆盖。新增检索版本/原文/预算/缓存、无Wiki、双分支复用、架构任务失败重试、生产Evidence映射及安装幂等回归；真实原生splitter/LocalDB/FAISS/路由使用独立离线脚本验证。

最小依赖边界：公共契约不依赖业务编排；共享调查不依赖简历/优化输出；优化入口不得调用简历collect；同一产物保存只走artifact_service。后续需人工判断语义质量、调查遗漏和架构必要性，不能用模型评分或mock通过替代。

验证结果及未部署限制见STATUS；本轮未推送、未改生产数据，保留初始exports/。

---
# RepoCareer 长期维护代码审查

原始审查日期：2026-10-11（下列基线描述保留用于对照，当前整理状态见第8节）。分支 `codex/resume-quality`；提交 `eea4c314fd3b2104ca77b18eea2d9ab606719840`；开始时工作区干净。适用规则为根目录 AGENTS.md，未发现仓库内其他 AGENTS.md。本轮仅新增本报告，不修改业务代码、依赖、配置或开发规则，不提交/推送，不执行外部仓库，不调用付费模型。

结论基于当前源代码、调用方、测试和脚本交叉追踪；此前报告只作为文档检查对象，不作为正确性证据。P0表示当前正确性/数据/任务风险，P1表示重复维护或明显变更扩散，P2表示可延后整理。标为“已确认”的静态事实不等于已经通过真实模型验证；并发时序等未复现部分另行标注。

## 1. 实际架构与调用链

### 1.1 生产入口

- `frontend/index.html` → `src/main.tsx:1` 仅导入 `architecture-entry` → `architecture-entry.tsx:78` 挂载 App。`LegacyWorkbench.tsx`不是当前网页入口。
- 同域部署：`scripts/start.ps1`启动 uvicorn；`backend/app/main.py`末尾挂载构建后的 `frontend/dist`。开发模式：Vite代理 `/api`，目标由 `REPOCAREER_API_TARGET`决定。
- App负责仓库/岗位/JD表单、架构报告选择、工作区恢复和架构Run轮询；Discussion负责对话、贡献录入、更正、材料和简历生成/展示，具有独立busy状态及轮询。

### 1.2 核心链路

| 链路 | 实际调用关系 | 执行与持久化边界 |
|---|---|---|
| 保存仓库 | App.saveRepository → POST repository-link → SourceReader.resolve_revision → GitHub REST | main创建Snapshot，标记旧Finding/Improvement与Artifact失效；解析失败显式unresolved |
| 岗位目标 | App.saveTarget → POST target → main.save_target | 原子修改role/JD并invalidate；另有jd-versions和PATCH workspace入口 |
| 当前架构分析 | App.start → POST architecture-runs → analysis.submit → execute → execute_architecture → DeepWikiOpen.wiki/review/chat | 单线程ThreadPoolExecutor；Run.steps/result保存进度/Wiki/报告；DeepWiki任务独立运行，本地取消只停止等待 |
| 当前对话 | Discussion → POST messages → agent.chat → LangGraph plan/tool/respond → DeepWikiOpen.chat（真实报告）或ModelProvider.complete | agent只读上下文/提出候选；main保存Message；用户另行确认后save_contribution写Contribution/MemoryEvent |
| 模型简历 | Discussion → POST artifacts → main.new_artifact → memory.compose（先构造规则源账本）→ resume_writer.collect/write → resume_quality.generate | HTTP同步线程执行；Run是进度账本，未进入analysis executor；写作前提交SQLite事务，结束再检查指纹并保存Artifact |
| 简历内部 | Harness.map_wiki → PRODUCT → JD_PLAN → retrieve/source_investigation → DISCOVER → CLAIM_VERIFY → SELECT → WRITE → 独立HR/TECHNICAL → 有界修复/一次补证重选 → render | SourceReader读取固定SHA文本；WritingModel直接HTTP请求云模型；SourceEvidence/Claim/Metric/Draft及trace存在audit JSON |
| 规则参考稿 | artifacts writing_mode=reference → memory.compose → compose_project_resume | 无模型；与模型稿有必要的生成/证据差异，不是失败时自动降级 |
| 兼容分析 | analysis-runs/repo-snapshots → analysis.execute非architecture分支 → GitHub.snapshot或fixture → analyze_snapshot AST模板 | API仍注册、被旧演示及测试调用；不是当前DeepWiki分析失败时的回退 |

LangGraph当前只编排对话，并不编排DeepWiki任务或简历写作。单主Agent约定不能理解为全项目所有工作都已进入同一个状态机；不建议仅为统一框架而改写这些顺序流程。

### 1.3 状态与依赖

`db.py`提供全局DATA、engine、Session及ORM，import时加载dotenv和创建数据目录；main/analysis/agent分别开会话。memory提供工作区范围查询、贡献乐观版本、更正事件、草稿失效，同时也负责规则文案。SourceReader缓存和证据txt在文件系统，业务行和审计在SQLite，LangGraph checkpoints在另一SQLite文件。

依赖环：`resume_writer.write:400`延迟导入`resume_quality.generate`，后者`generate:119`又延迟导入WritingModel、ProjectValue、ROOT、validate_product。当前延迟导入避免了初始化异常，但形成了真实双向依赖；不是声称已发生Python循环导入崩溃。`from .db import *`还隐式带入os/Path/now等，如main.config使用的os来自db，而非显式导入。

## 2. 重要发现（按优先级排序）

### R01 — P0：当前表单与实际简历目标脱节（已确认，静态调用链）

**本轮整理状态（2026-10-11）：** 已修复：当前编辑role/JD传至Discussion，空值不回退旧岗位；入口E2E验证。 具体修改与验证关联见第8节。

**位置/符号**：`frontend/src/architecture-entry.tsx:72` App渲染Discussion；`Discussion.tsx:7,23`可选targetRole/targetJD及生成payload；`main.py:213,217` new_artifact/save_target。

**证据**：父组件维护role/JD草稿，却只传`w`和`refresh`。子组件生成时fallback到`w.role`和已保存JD。因此用户编辑目标后直接点击生成，发送的是旧保存目标，而不是屏幕上的内容。后端原子保存和GenerationContext保护的是请求中旧值，不能修复缺失的前端连接。

**影响**：选材和岗位覆盖可能针对旧目标；“当前表单冻结”的设计在真实UI入口失效。后端test_generate_saves_current_target...直接传新值，未覆盖父子连接。

**最小修复**：明确目标保存责任，父组件传当前草稿或共享一次生成命令；保留后端原子保存。连接props时还需避免targetRole || w.role把空岗位悄悄恢复为旧岗位，应明确校验空值。不要通过另一套全局状态库解决。

**风险/验证**：注意空JD必须传空字符串以清除旧JD、角色必填、切换工作区不串值。用请求拦截E2E：保存JD-A→编辑JD-B但不点保存→生成，断言payload和ctx为B；再检查清空JD及role_inferred。无需真实模型。

### R02 — P0：简历Run共用错误的取消/重试协议（已确认，隔离复现）

**本轮整理状态（2026-10-11）：** 已修复：简历Run拒绝分析队列重试，阶段取消与保存检查，停止期间准入占用；回归覆盖取消后不落稿及原请求重试。 具体修改与验证关联见第8节。

**位置/符号**：`main.py:165–177` cancel/retry，`:233–269`简历生成；`analysis.py:10–17,81–95,138` futures/still_executing/execute/submit；`resume_quality.py:118–274` generate。

**证据**：简历Run直接在HTTP请求里写作，不注册futures；cancel只改DB状态，generate没有取消callback，最终直接写completed；retry无任务类型检查，一律submit进入只识别architecture/旧快照任务的execute。简历request没有demo/url。

**本轮隔离检查结果**：临时DB、Mock源码解析、阻塞stub writer；生成中`still_executing=False` → cancel返回cancelled → retry HTTP200 → 旧worker报`KeyError: 'demo'`并将Run写failed → 原HTTP生成继续，HTTP200且最终Run又是completed。没有付费调用、没有访问生产数据库。网页目前不提供简历取消按钮，但API仍可调用，且失败简历Run复用同一retry入口也不受支持。

**影响**：取消/重试承诺失真，两个执行路径争写同一Run；可能继续消耗API、保存用户已取消的产物。重启recover_runs对所有Run标interrupted是合理保护，但恢复路由必须按类型处理。

**最小修复**：先让cancel/retry按Run.kind/request类型分派；不支持的动作明确拒绝。为简历增加合作式取消检查（请求间、补证前、落稿前）与条件状态迁移；如仍同步执行，明确记录其在途句柄/租约，不让旧executor接管。无需引入消息队列。

**风险/验证**：在途HTTP无法保证立刻停止远端推理，需准确区别停止本地后续步骤与远端取消。隔离测试覆盖取消后不落稿、取消后重试拒绝直到停止、失败简历重试不走AST、旧分析及重启恢复不退化。

### R03 — P1：运行准入和事务编排散在API，跨入口并发策略不一致（静态事实已确认，版本竞争后果待复现）

**本轮整理状态（2026-10-11）：** 已修复准入与职责集中：artifact_service持有按工作区租约至事务完成；重复版本属于未复现风险，不声称已有数据损坏或多进程支持。 具体修改与验证关联见第8节。

**位置**：`main.py:71,100,152`旧/架构/换仓库检查工作区运行任务；`:213–274` new_artifact仅检查同一个gen幂等键；`db.py:117–136` Artifact/Run唯一键；`analysis.py:10–17`内存执行表。

**证据/影响**：不同幂等键的两次简历生成没有工作区准入检查；两标签页可并行调用模型。架构任务与简历任务也采用不同准入规则。Artifact.version使用`sum+1`，DB仅约束workspace/idempotency_key，不约束workspace/type/version；不同任务竞争版本的具体结果依赖SQLite时序，尚未复现，不能断言已存在重复版本数据。API函数同时承担目标保存、源账本生成、Run创建、progress回调、提交/重读、指纹检查和Artifact写入，新增任务类型需要修改大量状态分支。

**最小修复**：抽一个小型生成应用服务，统一准入/Run迁移/最终落稿；保留短事务、指纹与幂等键。先决定单工作区是否允许双生成；若不允许，采用事务内条件准入，而不是仅增加按钮disabled。需要唯一版本时增加约束并处理已有数据，不盲目迁移。

**风险/验证**：抽取时容易丢失当前错误落库和更正检查。不同幂等键并发、相同键重复、材料变化、SQLite冲突、取消/重启测试；先静态等价抽取再改变并发语义。

### R04 — P1：旧writer同时是基线实现和新生产依赖，不能整体删除（已确认）

**本轮整理状态（2026-10-11）：** 已合并生产共享边界、隔离旧基线：resume_support + resume_legacy，元数据账本替代被丢弃的规则正文；旧基线明确保留评测用途。 具体修改与验证关联见第8节。

**位置**：`resume_writer.py:20–47,110–157,159–188,296–402`；`resume_quality.py:119,202`；`test_resume_writer.py:3`；`scripts/eval-resume-quality.py:8,45`。

**证据**：新writer是转发器，但新generate从同文件取客户端、ProjectValue、校验和Skill路径；旧文件又持有旧检索、选题、Markdown检查、双审。测试把write_legacy别名为write；评测compare-legacy明确调用旧实现。main模型分支还先调用memory.compose取得源账本，再collect材料；这是账本兼容用途，不能仅凭重复文本函数就删。

**影响**：修改共享客户端影响新旧流程；删除“legacy文件”会破坏生产。两套检索/稿件校验并行维护，读者难以从模块名判断生产边界。

**最小修复**：先移共享客户端、项目全貌契约、材料收集到中性模块；新流程直接依赖它们，resume_writer保留薄入口。旧写作实现移明确基线模块，冻结非必要新增；源账本独立于规则正文生成，避免模型流程先生成一遍不用的规则稿。

**风险/验证**：保持main/脚本/测试patch入口兼容，金丝雀对比fixture正文、audit结构、缓存键、预算与错误；不能把旧测试机械搬到新流程后认为语义等价。

### R05 — P1：同一JD由两个入口产生不同的requirements语义（已确认）

**本轮整理状态（2026-10-11）：** 已修复：save_jd_version被两个写入口复用；新版本词项/历史/失效一致，不修改历史生产数据。 具体修改与验证关联见第8节。

**位置**：`main.py:123–141` add_jd/save_target；`memory.py:69,163,176`规则选材；`providers.py:search`；`analysis.py:analyze_snapshot`；`agent.py:tool` raw_text。

**证据**：jd-versions提取关键词并保存requirements；target保存同样文本时requirements=[]。规则稿、旧搜索/AST排序读取requirements，而新模型调查和对话读取raw_text。同一JD经新入口创建后，兼容路径排序失去关键词；文本不变去重还意味着切换入口不会修复空requirements。

**影响/修复**：这是重复维护产生的实际语义差异。共享JD版本创建与词项派生函数，原子target编排调用它；raw_text是权威值，词项是派生索引。不要要求JD关键词与模型调查问题共用同一语义。

**风险/验证**：保留空JD、版本去重、MemoryEvent、invalidate和diff响应；两个入口相同文本得到同样派生值且不重复版本，规则排序/旧搜索回归。历史空requirements是否回填需要另定范围，不能默默改写历史。

### R06 — P1：前端仍按旧audit字段读取新评审/检索对象（已确认）

**本轮整理状态（2026-10-11）：** 已修复：新版requirement_id/status/feedback适配与旧audit保留；E2E验证未知不冒充已检索及独立反馈显示。 具体修改与验证关联见第8节。

**位置**：`ResumeHarness.tsx:10,12`；`resume_quality.py:45,208–227,256`；`resume_contract.py:104–114`；`Discussion.tsx:23`兼容展示。

**证据**：新job_evidence含requirement_id和candidates_need_verification/unknown，组件读q.requirement并只识别unconfirmed；unknown也显示“候选证据已检索”。新双审返回feedback（category/issue/...），组件却只显示r.issues；意见存在但折叠结果可能只展示通过/未通过。Record<string,any>使tsc无法发现这一协议断裂。当前E2E第二例使用旧audit fixture，不是新结构。

**最小修复/影响**：前端边界把旧audit显式适配为统一展示模型，再用精简TS类型；保留历史预览，不在每个组件继续叠optional字段分支。真实核验限制/评审理由更容易被用户遗漏，不是模型质量本身的缺陷。

**风险/验证**：新旧artifact快照、unknown/缺省数组/feedback、两种output_mode展示测试；保证unknown不显示成已找到证据。类型检查不能替代历史兼容测试。

### R07 — P1：配置与流程名称耦合，已有配置在新入口失效（已确认）

**本轮整理状态（2026-10-11）：** 已修复：共享缓存路径、独立RESUME_MODEL默认、显式阶段/JSON协议；旧Markdown模式仅基线使用，配置/request mock通过。 具体修改与验证关联见第8节。

**位置**：`resume_writer.py:23–36,302`；`resume_quality.py:119–123,130`；`README.md:50,55`；`providers.py:97–112`；`deepwiki.py:25–35`。

**证据**：RESUME_ANALYSIS_CACHE_DIR仅旧writer使用，新generate固定DATA/resume-analysis-cache；README却称可覆盖。WritingModel以prompt开头判断JSON/Markdown和输出上限，重命名/新增阶段必须同步修改客户端。model还fallback到DEEPWIKI_MODEL，base/key却默认来自DeepSeek，切换DeepWiki到其他provider可能把另一家的模型名发给DeepSeek（是否发生取决于配置，未实际调用）。

**最小修复**：统一写作配置解析/预算对象并显式传stage/output_format/max_output，而不是协议猜prompt；新旧入口复用cache设置或明确废弃配置。保留GitHub、DeepWiki websocket、写作HTTP三种适配器的合理差异，不强行合成一个万能客户端。

**风险/验证**：配置优先级、默认值、mock transport请求体、stage预算/截断、缓存隔离回归；不要在移动客户端时误开启HTTP自动重试导致重复付费或改掉thinking协议。

### R08 — P1：旧恢复脚本能覆盖现有模型凭证和云配置（条件风险已确认，未执行）

**本轮整理状态（2026-10-11）：** 已安全化并保留：init-only、已有.env立即拒绝，测试只用临时虚构配置；没有运行真实sidecar初始化。 具体修改与验证关联见第8节。

**位置**：`scripts/configure-deepwiki.py:6–10`顶层代码；`README.md:43–47`；`docs/STATUS.md`历史恢复段。

**证据**：脚本直接修改generator/embedder/config.py并用write_text重写sidecar .env，不合并已有内容；现有DEEPSEEK_API_KEY/QWEN等键会被移除。README较新段明确说不要运行覆盖云配置，但旧段/历史恢复仍提供该脚本。当前启动脚本不调用它，所以不是每次启动都会丢密钥。

**最小修复**：确认是否还需本地初始化；若需要，明确init-only、已有配置时拒绝或保留未知键并备份；若不需要，归档并移除现行恢复指引。不要运行该脚本来验证风险。

**风险/验证**：用临时sidecar和虚构键验证保留/拒绝策略、重复运行幂等；不得拿真实.env测试，也不自动恢复用户密钥。

### R09 — P1：现行文档内存在相互冲突的行为说明（已确认）

**本轮整理状态（2026-10-11）：** 已修正文档：README/PRODUCT以现行结构化流程和预算为准；DECISIONS沿革及STATUS历史保留，不改AGENTS/Skill规则。 具体修改与验证关联见第8节。

**位置**：`README.md:25,29,39–61`，`AGENTS.md:8`，`docs/PRODUCT.md`最新首节及旧段；`docs/STATUS.md`最新与明确历史分界。

**证据**：README同文件说正文Markdown/8请求、D018最多9请求，当前代码却结构化Draft且默认16后续请求、范围8–20；AGENTS已写16。README缓存覆盖与R07不符；“当前界面上传入口”与实际GitHub入口不符；新建快照尝试固定SHA与README未固定提交混写；本机Ollama与当前云embedding描述并列。STATUS标注后文历史，历史记录不是自动错误，但正文README缺清晰现行/历史界线。

**最小修复/影响**：整理一份现行运行/配置/流程说明，旧沿革指向DECISIONS/明确历史段；不删决定历史。错误说明会诱导维护者改错流程、预算或运行恢复脚本。

**风险/验证**：逐条与API/schema/config读取位置对照，fixture示例检查；不改AGENTS中的产品政策来迎合实现缺陷。本轮未改任何现有文档。

### R10 — P2：轮询与详情返回绑定全工作区，扩展后会放大耦合（结构事实已确认，实际性能幅度待测）

**本轮整理状态（2026-10-11）：** 部分整理、其余延后：简历轮询限于生成/活跃resume Run、串行请求并显示错误；全量summary瘦身/共享状态轮询不在本轮扩展，性能幅度未测。 具体修改与验证关联见第8节。

**位置**：`main.py:64–69` workspace(summary)；`architecture-entry.tsx:25,29`；`Discussion.tsx:11`；`resume_quality.py:127,256`输出结构trace/audit。

**证据**：summary仅截断Evidence.excerpt，仍返回所有历史Run.result/steps、Wiki、Artifact.audit/正文；两个组件各自1500ms轮询整工作区，Discussion按所有busy操作轮询且吞错误，不只简历Run。audit又包含trace、段落、来源和映射，增长后同一份大材料反复传输。没有测量本机数据量或宣称已造成性能故障。

**最小修复**：一个共享小型API/轮询hook，先轮询已有run状态接口或精简摘要，结果完成时刷新详情；详情按需加载。无需React Query等新增依赖。区分网络错误、取消、过期请求，保留activeId防串工作区。

**风险/验证**：切换/刷新/断线后重新接管轮询、终态停止、请求不重叠、历史仍可查看；以fixture负载量和实际字节数测收益，不能仅按文件数量判断问题。

## 3. 测试与验证边界

本轮运行 `.venv/Scripts/python -m pytest backend/tests -q`：**89 passed（5.07s）**；fixture在导入app前把REPOCAREER_DATA指向临时目录，并mock源码解析，清理的也是临时DB。另运行依赖Node的 `tsc --noEmit -p tsconfig.json`：通过，不构建/更新dist。上述R02临时DB复现成功。未运行E2E（其现有用例仍可能为示例仓库做GitHub解析）、demo.py、configure脚本、真实评测或外部代码；未主动打开或输出生产.env内容；应用import保留现有dotenv默认加载行为，因此不能声称完全隔离生产配置。数据目录已在导入前切至临时目录，模型及源码请求采用stub/mock，未产生真实服务调用。

不能说“测试主要只有旧流程”：test_resume_quality.py实际调用生产write并覆盖目标保存/Run、状态/指标/来源/重选等。test_resume_writer.py第一行把write_legacy别名write，很多单测保护旧基线；其中API指纹/幂等/失败测试仍patch生产入口，不能整体归类废测试。test_providers_runs保护旧分析任务取消/重试，未保护简历Run。前端两项E2E分别是规则演示和旧audit恢复，没覆盖R01的未保存表单、R02同步生成生命周期和R06新版评审数据。检查新流程的mock通过不证明模型理解/文案质量；本轮没有新增真实质量结论。

## 4. 旧代码处置表

| 对象 | 当前证据与分类 | 处置建议 |
|---|---|---|
| resume_writer.write_legacy、旧Selection/Review/Markdown checks、job_evidence/enrich_material | test_resume_writer、eval-resume-quality --compare-legacy明确使用 | **保留基线**，从生产共享模块分离后冻结；并非直接删除 |
| WritingModel、ProjectValue/validate_product、collect、ROOT | 新generate/main生产直接依赖 | **保留并合并共享边界**，不能随legacy删除 |
| memory.compose_project_resume | 当前reference入口，显式演示/离线用途 | **保留**，不用模型生成逻辑强行替换 |
| memory.compose内kind==resume后续分支字样 | :65已提前返回；其余分支仍支持task_pack/interview_notes | **局部删除候选**（不可达的resume特例），不是删除整函数 |
| analysis.analyze_snapshot / GitHub.snapshot / analysis-runs / repo-snapshots | API注册，demo.py与test_providers_runs使用；当前UI未走 | **兼容保留/需要确认退役范围**；没有外部调用统计，不能宣称无人使用 |
| repository-upload / import_zip / DeepWiki local payload | API、archive测试及SourceReader archive兼容存在 | **兼容保留**；可单独标明非当前UI，需用户确认再退役 |
| LegacyWorkbench.tsx | main仅import architecture-entry；全库未发现当前import/动态入口，但tsconfig include src仍检查该文件；自身有createRoot副作用 | **删除候选**或归档，先确认是否需旧工作台；不能为复用直接import导致重复挂载 |
| scripts/ui-smoke.mjs | 等待旧“创建实践工作区”标题，当前网页无此标题；未发现现行调用 | **删除候选/更新现行烟测**，按需要选择，不能当当前E2E结果 |
| scripts/demo.py | 仍会调用有效旧API，默认8000写工作区与贡献 | **保留但需明确隔离/用途**；审查不运行；不是安全的只读检查 |
| scripts/eval.py | ModelProvider旧三种记忆输入评测；非实际新resume writer，check-fixtures仅检查格式 | **保留研究基线/需确认**，不合并为生产质量证据 |
| scripts/eval-resume-quality.py | 当前真实writer及显式旧基线评测 | **保留**；真实模式会收费，只读业务记录不等于零成本 |
| scripts/compare-resumes.py | 已存Artifact人工对比、工作区/指纹检查，README有命令 | **保留**，和实际生成评测职责不同 |
| configure-deepwiki.py | 有历史文档引用，覆盖配置风险R08 | **需要确认/归档或安全化**，不因名称旧直接删除 |
| start-deepwiki.ps1、deepwiki-local.patch、deepwiki_archive_fallback.py、lock文件 | sidecar启动/补丁恢复配套；独立于主app发布 | **保留**，上游升级时核对补丁与固定版本，审查未执行sidecar代码 |
| Claim.supersedes_claim_id、SourceReader.trace | 声明但当前业务未形成读写链路（Contribution历史由MemoryEvent提供） | **需要确认**是否预留；不据此宣称已有claim版本事件系统 |

## 5. 四个修改场景的静态影响范围

### 5.1 调整亮点数量/输出格式

**合理改动**：ResumeDraft/Choice字段上限（resume_contract:69,97）、generate选题/写作约束与预算、render/ResumePreview展示、Skill模板与当前验收及fixture。改变数据契约、内容规则、渲染和测试本来应跨层。

**额外扩散**：数量“1–4”分别存在schema/prompt/Skill/规则稿[:3和4-len]、旧Selection、客户端max_tokens阶段规则与多版README；旧基线不应随新上限一起重写。最小方式是当前流程统一限制来源、保留旧fixture语义、适配历史audit。只改Markdown标题不应触及ORM或任务执行器。

### 5.2 更换模型配置或客户端

**合理改动**：WritingModel与配置解析、mock请求体/错误/usage测试；如API协议不同增加专门适配。DeepWiki上游生成模型在sidecar配置，模型简历云HTTP不必一起更换。GitHub客户端更不应受影响。

**额外扩散**：新generate从旧writer导入客户端；旧/新cache路径不一致；DEEPWIKI_MODEL跨provider泄漏；阶段prompt前缀控制JSON/预算，客户端改动需检查新旧stage。将配置、阶段请求参数与文本prompt分开即可，不预设需统一框架。评测必须记录模型变化，不能拿不同模型的新旧输出宣称单独架构收益。

### 5.3 新增证据来源

**合理改动**：来源适配/路径与大小约束→SourceEvidence→collect/material_evidence→check_claims的支持/验证规则→用户展示与隔离测试。若新增持久化个人材料，还需EvidenceInput、DB CheckConstraint、attach provenance及Alembic迁移；仅新增只读外部线索不一定要改ORM。

**额外扩散**：EvidenceInput Literal、DB类型检查、memory.attach硬编码字典、collect过滤、agent材料检索、Discussion选项、SourceEvidence的自由kind及check_claims分支需同步。两个账本（用户持久材料与一次生成源码证据）职责不同，保留差异；在边界集中来源映射/校验，避免因字段同名强行合一。

### 5.4 改取消/重试/轮询

**合理改动**：Run类型及状态迁移、执行器注册与取消callback、API命令、客户端终态轮询、重启恢复和隔离测试。DeepWiki取消只停止等待的外部约束必须保留说明。

**额外扩散**：同步简历不登记futures，却暴露通用Run命令；status在main.cancel/retry/落稿、analysis.execute/recover均直接修改；architecture和Discussion分别管理busy/轮询/错误，主页面还只从架构runs决定active。先拆任务类型和统一状态命令，再共享轮询，不直接引入队列或把所有执行搬入LangGraph。

## 6. 原始建议顺序（已获用户授权，本轮执行结果见第8节）

1. **先修连接与生命周期**：R01、R02；明确R03并发准入策略。验证未保存目标请求、取消后不落稿、类型正确的重试、重启/幂等/更正保护。先补能失败的入口测试，再最小修改。
2. **统一共享业务边界**：R05 JD版本函数；R04客户端/ProjectValue/collect与旧基线分离；抽生成应用服务，先保持行为。fixture audit/错误/缓存/指纹回归，历史导出不变，不增加框架。
3. **修数据展示及配置文档**：R06、R07、R09，确认R08脚本去留。新旧audit UI测试、配置优先级/请求体测试、临时配置保留测试，现行文档逐条对照。
4. **最后整理旧入口和轮询**：按处置表征得API退役范围，处理旧UI/烟测；R10根据实际请求量优化。确保兼容API/脚本有明确保留或迁移决定，测量而不是只按文件长短拆分。

## 7. 可预防项、人工判断与值得保留的设计

**适合长期约定/小型自动检查（本轮仅建议）**：新增Run类型必须声明执行/取消/重试/恢复协议；测试当前UI请求与API上下文一致；共享配置只在一个解析入口；现行audit使用展示适配和类型检查；禁止生产反向依赖基线模块（可用轻量AST检查模块边，不查函数名legacy）；配置初始化不覆盖未知键；mock/静态/真实质量结果必须分开记录。文档命令/schema示例可做离线烟测，不能自动把历史说明判为错误。

**仍依赖人工判断**：兼容API是否有人使用、基线是否需保留、模型语义支持是否真实、岗位亮点合理性、来源可信度、上游补丁升级策略、是否值得复杂检索/框架。不能用引用合法或测试数量替代这些判断。

**应保留**：工作区require/scoped与外键约束、Contribution乐观版本+MemoryEvent历史、Artifact依赖失效、生成指纹、短SQLite事务、明确演示与规则稿、固定SHA源码/Wiki未知版本分离、结构化Claim的独立维度、确定性渲染、预算与显式失败、外部代码不执行、映射缓存、activeId防切换串数据。单线程分析executor对单人MVP有合理性；问题是另一执行路径没有匹配协议，不是“线程池太简单”。

本轮没有发现必须新增图谱、Agent、消息队列或更大框架的证据。建议按上述顺序小步整理，先以当前行为回归保护，再决定是否需要更大架构变更。

## 8. 已授权整理实施记录（当前状态）

### 8.1 基线与范围

再次核对HEAD仍为eea4c314fd3b2104ca77b18eea2d9ab606719840、分支codex/resume-quality；开始只有本报告未跟踪，未发现用户源码改动。89项基线回归再次通过（4.84s）。原审查R01–R09的确认事实仍成立，未按待核实项删除代码。R03并发版本数据损坏未被证实，结论维持风险，不升级为已复现缺陷。

全部修改在工作区未提交；没有推送、部署、重启8000、改生产DB或实际.env，没有收费模型/外部仓库执行、依赖更新、Skill/提示词/长期规则变动。下面是业务行为修复和结构整理的区分。

### 8.2 逐项修改与验证

| 项目 | 实际修改/性质 | 验证关联与风险 |
|---|---|---|
| R01 已修复 | architecture-entry.tsx:72传递targetRole/targetJD；Discussion的role使用??，保留明确空值。行为修复 | core.spec.ts未保存岗位/JD、清空JD、清空role请求；原目标保存/API 422回归保留 |
| R02 已修复 | main.retry:160按任务类型拒绝resume_generation进入submit；main.cancel:154条件更新；task_lifecycle.check_generation:34；artifact_service取消/异常收尾/保存前条件状态迁移。行为修复 | test_cleanup_lifecycle取消仍在执行→通用重试409→同键/异键新生成409→原请求不落稿→原产物请求可重试；Harness停止前不调用provider；保存后处理失败不遗留running |
| R03 已修复范围 | main.new_artifact:205成为薄入口；artifact_service.create_artifact:11集中短事务、指纹、幂等和异常终态；artifact_lease:22按工作区串行至最终提交，其他Run占用时拒绝。结构整理+准入修复 | 同/异幂等请求冲突，跨工作区互不阻塞，现有指纹/幂等/隔离测试。只承诺单后端进程，不声称分布式锁或已有重复版本数据已修复 |
| R04 已合并/基线保留 | resume_support的WritingModel:17、ProjectValue:64、collect:82、source_ledger:117；resume_writer.write:6→generate→support；write_legacy:10惰性调用resume_legacy仅评测。模型API不再调用compose规则渲染。结构整理 | 有效旧基线测试转为明确resume_legacy导入，客户端测试指向公共共享组件；模型公共入口和原有指纹/失败测试保留；新增“model不渲染reference”验证 |
| R05 已修复 | memory.save_jd_version:18统一词项/版本/MemoryEvent/失效；main.add_jd与save_target:26复用。行为修复 | 相同JD去重、两个入口词项一致、supersedes/version、清空JD、旧更正传播回归；没有回填历史数据 |
| R06 已修复 | ResumeHarness显式JobEvidence/PerspectiveReview字段；ID解析岗位文字；unknown和候选待核验分开；feedback的分类/阻断/段落/候选/源码路径展示，旧issues仍可显示。行为修复 | core.spec.ts新版独立HR/技术反馈、unknown、缺默认数组；原历史audit恢复用例保留；TypeScript验证 |
| R07 已修复 | cache_directory:113供新旧链路；RESUME_MODEL默认deepseek-v4-pro，不继承DEEPWIKI_MODEL；生产Harness显式传stage和JSON输出，客户端不按正文内容决定格式。行为修复+结构整理 | test_cleanup_configuration配置覆盖与独立默认；MockTransport断言原thinking/预算/JSON/截断语义；原缓存隔离回归。没有开启HTTP新重试或改预算/prompt |
| R08 安全化保留 | configure-deepwiki.initialize:9先拒绝已有.env，再完整读取/准备输入，exclusive创建.env；main guard消除导入副作用。行为修复 | 临时虚构配置逐文件字节对比；重复初始化拒绝；sidecar的config.py只当文本，不执行。首次初始化的I/O失败可能需要人工恢复，未宣称多文件事务 |
| R09 已修正 | README/PRODUCT统一现行GitHub入口、固定源码/Wiki未知、结构化Draft/默认16预算/云配置职责；STATUS/DECISIONS/BACKLOG记录真实状态和历史。文档修复 | 对照实际schema、generate、shared配置和测试命令；原8/9预算只留DECISIONS/历史，不继续作为当前说明 |
| R10 部分/延后 | Discussion仅在生成或活跃resume Run轮询；setTimeout等待refresh完成后再调度，显示网络错误且保留卸载停止；原架构轮询保持。相关低风险整理 | E2E生成/刷新/旧数据恢复通过；没有负载字节数/断线长期压测，workspace全量summary和共享轮询留下一阶段评估 |

新增模块各解决现存边界问题：artifact_service集中实际产物事务；task_lifecycle保持同步请求取消后的准入；resume_support解除生产依赖基线；resume_legacy隔离已有评测实现。未按目录美观继续拆文件。

### 8.3 整理后的核心调用链

- 页面main → architecture-entry（当前role/JD）→ Discussion → POST artifacts → main薄路由 → artifact_service（准入/冻结/事务/保存）→ resume_writer.write → resume_quality.generate → resume_support.WritingModel与项目契约 + Harness/SourceReader → 结构化Draft/独立双审 → 确定性render → Artifact及Run终态。
- JD两个API → memory.save_jd_version → JD/MemoryEvent/依赖草稿失效；role+JD仍同一事务。
- 显式reference → memory.compose_project_resume → Artifact；不会在模型失败后自动选择。
- 旧基线只有eval-resume-quality --compare-legacy/明确基线测试 → write_legacy → resume_legacy，共用中性契约和客户端，没有生产反向导入。
- 架构与旧实践分析API继续→analysis executor；简历Run不通过该队列重试。cancel持久化状态，生成Harness各阶段/最终保存检查；resume原命令重试校验同输入版本。

### 8.4 旧实现最终处置与删除条件

| 对象 | 本轮最终状态 | 保留原因/删除条件 |
|---|---|---|
| LegacyWorkbench.tsx | 删除 | 当前main及全库无静态/动态入口，当前能力由architecture-entry/Discussion覆盖，旧API未随UI删除；TypeScript和端到端回归 |
| resume_writer中的旧Markdown/schema/checks/retrieval | 移至resume_legacy保留 | 明确评测比较基线；取消--compare-legacy及相关历史比较需求并确认后方可退役，生产不可用作降级 |
| WritingModel/ProjectValue/validate_product/collect/ROOT | 合并至resume_support | 当前生产和基线共享的中性能力，不复制两份 |
| memory.compose不可达resume字样 | 删除局部特例 | 首行早返回，不改变reference/interview/task_pack三个公共路径 |
| ui-smoke.mjs | 更新保留 | 当前只读截图工具，标题定位改现行品牌；不再当旧页面验收，也未对现有8000运行本脚本 |
| configure-deepwiki.py | init-only保留 | 新本地Ollama初始化，现有.env拒绝；确认不再支持该初始化时可退役，不用于切换云配置 |
| analysis-runs/repo-snapshots/AST/GitHub.snapshot/ZIP/import_zip | 兼容保留 | 测试/脚本仍使用，外部客户未知；须确认退役范围及替代入口后另批删除 |
| demo.py/eval.py/compare-resumes/sidecar补丁 | 保留 | 写入演示/旧模型研究/已存稿对比/上游恢复是不同用途；不是当前真实简历质量结论；demo仅隔离环境 |
| Claim.supersedes_claim_id、SourceReader.trace | 待确认保留 | 没有依据直接删除或扩展成新业务系统 |

### 8.5 验证与失败记录

原始基线89通过。首批移动服务出现3项新增NameError（save_target导入遗漏），修复后相关49项通过；后续97项全量通过。前端noEmit、隔离Vite构建（data/cleanup-build）和4项Playwright通过，旧2项有效用例保留，新2项保护R01/R06。E2E测试服务器使用专用fixture入口拦截GitHub版本解析，不联系模型。最终全量 **99 passed（12.46s）**，包括新增异常收尾/跨工作区测试；实际新旧writer离线同fixture对比通过（injected、9调用、status=passed），输出在独立临时REPOCAREER_DATA目录，未写生产数据。git diff --check通过。未发现基线既有失败；没有放宽有效断言。

未验证真实模型质量、收费服务连接、生产部署、多进程锁、全量摘要负载、长期断线；没有用静态检查或mock次数证明文案准确性。现有8000及dist保持上轮运行版本，代码更新未部署。

### 8.6 上阶段边界建议（已由本次用户授权固化，见第9节）

1. 生产依赖不得反向读取评测基线；共享客户端/配置保持唯一入口，基线调整需说明比较目的。
2. 新Run类型明确声明执行、取消、重试、恢复及占用释放协议；保留入口级取消/幂等/材料更正回归。
3. 现行audit数据契约与历史展示兼容分开；业务/证据/模型配置职责不混，真实质量验收仍依赖人工。

本轮不新增治理框架或持续自动检查。进入“持续约束”阶段须用户确认；全量摘要瘦身、兼容API退役和多进程支持不能默认为已授权。

## 9. 持续约束阶段实施与验证（2026-10-11）

根据用户后续明确授权，已整理AGENTS为短统一入口，新增当前architecture说明；历史发现不全部变成永久规则。上一阶段未提交改动保留，本轮未继续业务重构。

只固化R04的生产/评测依赖边界与当前schemas/architecture_schema/resume_contract的编排依赖方向。scripts/check_architecture.py用AST含函数内/子包/常见字面量动态导入；兼容桥精确限定resume_writer.write_legacy中的单条旧基线导入。backend/tests/test_architecture_boundaries保护这两个规则及例外。生命周期、指纹、JD一致性和前端契约继续由上阶段现有行为回归保护，不用静态文件位置替代。

check.py复用已有pytest/TypeScript/Vite/Playwright；packageManager固定本机pnpm@11.25.0，CI安装既有frozen lock与后端requirements.lock，不改锁版本。CI和本地调用同一入口，缺工具/失败非零且不继续；build/E2E隔离临时目录，不更新8000或生产dist。CI YAML解析/输入/权限/失败策略核对完成，工作流未推送，远端安装、执行和合并保护尚未验证。

真实临时添加生产→resume_legacy和schemas→artifact_service违规，分别返回1/A01、1/A02；原始字节try/finally恢复后返回0。同一check.py违规时仅执行架构阶段即失败，未继续其余检查。最终完整check.py --e2e返回0：106后端通过（7.55s）、typecheck/隔离构建通过、4 E2E（17.3s）；git diff --check通过。检查回归覆盖间接依赖、子包/别名、精确兼容、缺工具和失败退出。无有效测试删除/断言放宽，无新依赖框架。

Codex桌面加载根规则已有本会话注入证据，修改后主动重读；官方优先级与其他AI手动引用办法见architecture，不复制多套规则。是否需要新增抽象、退役兼容、判断岗位亮点或验证真实模型质量仍由维护者/用户决定。开发步骤和少量自动边界现已可使用，未擅自推送/部署/更改远端权限或生产数据。
