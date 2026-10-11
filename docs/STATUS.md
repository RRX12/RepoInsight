# 当前交接：简洁用户页与过程后台（2026-10-12）

- 分支 `codex/resume-quality` / 基线 `eea4c31`；本轮按用户请求将当前源码、测试、迁移和文档整理提交到同名GitHub分支；推送结果以实际远端核验为准。
- 已实现：用户页顶部固定导航：项目设置（仓库/JD）、项目全貌、优化大方向、讨论区、当前信息、项目经历编辑器。长报告不再遮住交互入口；无项目显示明确引导，无浏览器选择记录时恢复最近项目。
- 过程后台入口 `/?view=admin`：Wiki、JD详细取舍、阶段/输入输出、证据索引、变更记录、写作审查与历史高级工具。复用原状态/API/报告和Discussion，不新增业务流水线。用户页保留来源、待复核、未保存等必要提醒。
- 验证：统一入口通过，152后端（9.55秒）、8 E2E（20.3秒）、类型检查、隔离构建、架构检查通过。新增页面测试覆盖入口可见、空项目提示、默认项目恢复、前后台分离、跨标签与后台往返保留手动文本、390px窄屏。已查看隔离测试截图；当前Codex浏览器连接不可用，未直接读取用户当前标签页。
- 已加载：frontend/dist已构建，8000用户首页及`/?view=admin`均200，最新包index-DG3GiPSM.js可访问且包含新导航/过程后台。只改前端，未迁移数据库、未重启后端、未调用真实模型。现有浏览器页面需刷新载入新包。
- 发布范围：源码/测试/文档及CI配置纳入当前版本；`.env`、数据库/备份、依赖、构建产物不纳入；本地导出的第三方项目Wiki（exports/）仅供下载，未纳入本次代码发布。
- 下一步：用户按顶部导航体验；若新增建议涉及模型输出质量，另做固定输入真实评测，不能以本轮UI测试替代。

---
# 当前交接：项目分析后的交互迭代 MVP（2026-10-12）

- 分支 `codex/resume-quality`，基线 `eea4c314`；保留既有大量未提交改动。代码未提交/推送；2026-10-12已按用户“加载项目最新版”请求完成本地构建、备份和服务重启。
- 已实现：统一工作区版本/幂等/原子更新；讨论结构化操作；JD/贡献/方案/指标面板；正文手动版本、审查与生成建议、差异接受/拒绝、恢复历史；生成期间指纹检查。方案决策与完成、源码事实与个人归属分开。
- 复用：原 SQLAlchemy/MemoryEvent/Artifact/JD、贡献验证、模型客户端/Skill、既有简历生成与任务互斥。新表只补交互状态；没有新增 Agent 或第二套简历生成流程。历史高级工具折叠保留，用途/退役条件见 architecture。
- 迁移：新增 Alembic 002，只添加 interaction_states 和交互回执唯一索引；旧数据延迟映射，旧简历首次作为当前版本。生产库已在备份后升级至002，完整性检查ok。备份：`data/backups/repocareer-before-interaction-20261012-013918.db`。
- 已验证：最新后端全量 **152 passed（9.73秒）**；最新前端类型检查、隔离构建、**6条Playwright E2E（18.0秒）**通过；A01/A02架构检查及git diff --check通过。交互专项14条覆盖原子回滚/幂等/版本冲突/跨工作区、采用与完成分离、指标历史、JD保留、审查接受/恢复、生成中改稿及旧生成标识拒收、001→002迁移、长证据摘要指纹和稿件归属。前轮2条旧E2E隐藏控件超时已修复进入方式，断言未放宽。没有遗留检查失败。
- 真实模型未调用：离线模型返回仅用于结构与页面验证，不证明批判性建议、指代消歧或文字质量。`frontend/tests/fixture_app.py` 只在测试服务器替换传输，生产不可用时明确报错。
- 启动与演示：后端 `.venv/Scripts/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`；前端 `pnpm --dir frontend run dev`。完整演示/限制见 architecture 的“交互迭代 MVP”。本次已重建frontend/dist，当前8000已加载最新交互版；首页/既有工作区interaction API均200，新前端包index-CZ9jaWZJ.js可访问，7个交互路由已注册。
- 下一条可执行任务：按architecture演示路径体验已加载的本地版本。真实模型固定场景仍需新的实际调用授权；未保存正文仅在当前浏览器本地保留，不是跨设备同步。

---
以下是历史记录，不代表本轮已加载或验证。

2026-10-12 JD自主发现实验：已准备docs/chatgpt-jd-experiment.md，使用冻结仓库/JD，不含五点范文。尝试连接ChatGPT网页时浏览器桥接拒绝，未发送任何消息、未运行网页模型、未改变业务代码。待浏览器可用或用户在ChatGPT执行后再比较真实结果；不得标记实验通过。

加载确认：候选输出预算修复已重启8000，API 200，无任务自动重跑。

2026-10-12候选截断修复：961a3b任务DISCOVER输入31312/输出7000 tokens截断，尚未进入关联修复。发现/增量/补全阶段默认输出预算12000（RESUME_DISCOVERY_MAX_TOKENS限制7000–16000），补丁仍3500。清单机制文本与facts重复，发现输入仅保留逐页标题/数量/状态；要求省略空值和默认字段但不裁剪全Wiki。截断提示显示阶段和上限。138后端测试/架构检查通过，未调用真实模型，服务商对新预算的接受及质量尚未验证，未自动重试。

服务加载确认：无活动任务时已重启8000并检查API 200，字段兼容修复已加载，未自动生成。

2026-10-12补丁字段兼容：ReferencePatch在解析前将明确候选事实引用字段的claim_ids规范化为refs；同值双字段可接受，冲突、证据字段误用、未知字段均拒绝，不改输入对象。仍经过原合并及完整事实校验，不新增模型请求。137后端测试（6.84秒）与架构检查通过，无付费重跑、推送或生产记录修改。

服务确认：已在无运行任务时重启加载空证据补丁修复，API返回200；未自动生成。

2026-10-12空证据补丁修复：d3b951任务将用户计划误标user_confirmed且无贡献ID，触发关联修复后模型清空证据。现accept_discovery复用bound_attribution保守降级无绑定个人标签并审计，再作引用校验；apply_reference_patches明确拒绝空证据且不修改原材料。133后端测试/A01/A02通过，未付费重跑。当前分支及既有改动保留，未推送。

2026-10-12服务加载确认：无运行任务时重启8000，首页/API均200，已加载补丁式关联修复；未重新生成或调用模型。

# 当前状态：关联修复补丁化（2026-10-12）

codex/resume-quality，既有改动保留。针对f6b6780任务LINK_REPAIR整份重写达到7000输出Token失败，改为ReferenceRepair引用补丁，程序深拷贝合并再经Discovery及事实契约核验。仅可修改既有引用、删除可选机制步骤；禁止改事实正文/状态/新增实体，重复或未知补丁拒绝。保持一次全局修复上限与原Token预算，未以提高额度掩盖问题。无付费调用/推送/生产记录修改。

验证：131后端测试通过；新增补丁事实保持、未知目标和非法字段回归。真实模型补丁输出质量尚未验证，旧失败任务未自动重跑。下一步另获模型调用授权进行固定样例验证。服务加载状态见后续记录。

# 当前状态：能力调查与依赖补查（2026-10-11）

codex/resume-quality，HEAD eea4c314；原有未提交改动保留，无提交/推送/付费调用/生产数据修改。本轮未重启服务，磁盘新实现待加载。

已实现：JD_PLAN从岗位能力提出中性实现问题；SOURCE从已接受片段解析安全相对导入，补读一层最多两个依赖文件，共享既有文件/字符/工具预算，记录路径线索与未读预算；TECHNICAL原请求反向核查动态、并行、记忆与权限表述；Skill加入隔离事实的写作结构示例。继续复用现有候选/核验/写作与一次双审，没有新增模型阶段或框架。

验证：130后端测试通过（6.78秒）、A01/A02通过。新增现存路径/越界拒绝/js到ts解析及一层共享预算回归。静态线索仅证明import关系，不证明执行链；历史未解析SHA无法源码核验，路径别名/反向调用/全语言调用图尚未实现。真实单主题与跨仓库质量未验证，不将测试通过当作文案质量证据。

下一任务：固定仓库SHA并只读核对一条完整机制，再另获模型调用授权做同输入生产回归；启动命令仍为`.venv/Scripts/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`。

本轮对照追踪（2026-10-11）：新增docs/resume-quality-comparison.md，列五主题Wiki定位、实际阶段丢失与验证限制。新增mapping_inventory逐页映射清单，供DISCOVER并持久化trace/audit，避免只采用README与用户优化，零新增模型请求。128后端测试通过（6.80秒）；未付费、未改生产记录、未重启8000，改动未提交。尚未逐条语义核对18个缓存映射/范例全部源码，下一任务固定版本记忆机制补证与授权生产回归。

# 当前状态：项目主线与岗位选材v4（2026-10-11）

分支codex/resume-quality，HEAD eea4c314fd3b2104ca77b18eea2d9ab606719840；已有未提交改动保留，未提交/推送。本轮无付费模型调用、生产数据修改或外部源码执行，8000仍加载此前代码，尚未重启。

已实现：复用项目全貌/机制卡片/补证/核验/写作入口。SELECT仅接收合格候选支持事实，明确参考稿上游能力与个人稿贡献政策；发现按项目闭环及触发—处理—边界—输出分析后关联JD。新增轻量project_spine函数复用核验claim供简介，弃用未映射product文本，亮点与成果仍禁止未选事实。audit保留project_spine_claim_ids，契约标记v4。Skill与PRODUCT/architecture/DECISIONS同步。未新增Agent或流水线。

验证：127后端测试通过（6.79秒）、架构A01/A02通过。新增主线事实状态筛选、简介/亮点/成果权限、选题模式政策与资格隔离测试；旧“全部未选事实禁止入写作”测试改成当前明确的简介权限，未放宽亮点断言。无前端代码变更，未重跑前端检查。

限制：模式政策的语义执行、工程机制发现完整度、跨仓库实际文案质量尚未真实验证；提示词不能保证模型不误判。未虚构同输入改进结果。下一条任务：加载v4后，另获付费授权运行固定SHA/JD单主题（版本化记忆）验证，再扩展整份与跨仓库样例。启动仍为`.venv/Scripts/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`。

最新服务恢复：按用户要求重启8000，已加载减少修复/一轮双审的最新代码；首页与/api/config均200，启动完成。上文历史“尚未重启”状态已失效。未自动重跑生成或调用付费模型。

# 当前状态：减少修复与无效模型调用（2026-10-11）

分支codex/resume-quality，HEAD eea4c314fd3b2104ca77b18eea2d9ab606719840，既有未提交改动保留；本轮未提交/推送、未改生产记录、未调用付费模型。

定位：4501e1a任务32条核验事实均supported/unknown，因此无合格候选；仍调用空材料写作和第二轮评审，导致16请求耗尽。现零资格/零可写事实在拟稿前停止并保存状态诊断；核验提示区分Wiki版本、实现和验证状态，不以程序猜测提升事实。SELECT提供预筛eligible_ids。source_paths超预算本地去重保留4条并审计遗漏，不修整份JSON。全流程契约修复（schema/link/selection/fact）最多一次，失败明确报错；不会降级冒充生成成功。

写作改为独立初稿→合并→一轮HR/技术意见→按类别整理→必要时最终修订一次，仅程序校验，不再第二轮模型双审。事实/机制反馈仍先局部核验，未解决用户证据缺口保留needs_review。audit.final_model_reviewed记录最终稿是否经过模型评审。复用同一生产入口，无新模块/框架。

验证：124后端测试通过（6.58秒）、A01/A02通过、diff检查通过；新增未知实现停止、路径预算不修复回归，原个人零贡献测试改为明确停止契约，保留禁止个人断言保护。没有前端改动，未重复前端检查；真实模型效果未验证。8000本轮尚未重启，磁盘修改待加载。下一任务重启后在另获付费授权情况下重验冻结样例，检查状态判断准确性与调用数，而非以stub证明质量。启动命令见下文。

# 当前状态：候选编号混用与终态刷新修复（2026-10-11）

保持codex/resume-quality/eea4c314，全部原有未提交改动保留。真实v3失败b7f39676：修复输出将Wiki证据编号和其他候选claim写入机制标注，严格校验阻断；未生成V18。生成错误路径act未刷新最终状态，页面可能滞留running。

已修复：关联修复输入包含每候选允许claim和claim→证据关系；一次模型修复后仅剔除无法关联的可选标注，步骤整条移除，问题关联丢失时清空问题，并记录trace/gaps。不猜映射、不更改原事实、不放宽核心证据/候选契约。前端act成功/失败均最终刷新，刷新失败显示错误；读取禁用缓存。复用现有流程，无新模块。

验证：共享check.py --e2e全部通过：122后端测试、架构A01/A02、类型检查、隔离构建、5浏览器测试（13.8秒），新增编号混用与失败终态保留V17回归。无付费调用/外部代码执行。随后本地frontend/dist构建并重启8000加载修复，重启前无运行任务。未推送或修改业务记录。真实模型内容尚未重验，旧失败记录不会改成成功；下一任务用户重新生成后核对真实输出。启动命令仍见下文。

服务恢复记录（2026-10-11）：按用户要求重启8000，最新磁盘v3已在新进程启动；首页与/api/config均200，Uvicorn启动完成。重启前有一个running任务529f1b906d8d464f9c354d93b0e5e85c，启动恢复机制将其标记interrupted，不自动再次付费调用。未重跑生成、未推送。先前“8000未重启”说明为当时状态，现已失效。

# 当前状态：证据关联与双视角拟稿（2026-10-11）

分支codex/resume-quality，HEAD eea4c314fd3b2104ca77b18eea2d9ab606719840；原有未提交改动保留，本轮也未提交/推送/部署，未改生产数据、密钥或运行服务。

已实现：DISCOVER明确合法证据编号列表、禁止fact-*代替source_ref和引用未输出claim；复用已有一次LINK_REPAIR，不猜测编号映射，错误指出claim及未知编号。resume-quality-v3首轮DRAFT_HR/DRAFT_TECHNICAL独立拟稿→本地契约核验→WRITE去重合并→独立双审→必要时修订一次再双审。初稿及其问题保存audit.perspective_drafts；不合格初稿隔离，不成为事实来源。两轮写作/评审与原有局部补证、贡献/取消/指纹约束继续生效，没有新增Agent或流水线。

验证：后端121项通过（6.37秒）；A01/A02架构检查通过；git diff --check通过。本轮无前端改动，未重跑前端；没有真实模型调用，离线测试证明流程和契约，不能证明简历内容质量。新增流程顺序、独立输入、初稿审计回归；旧版本断言同步v3，未降低事实断言。

剩余：页面失败任务是v1历史记录，8000未重启，磁盘变更尚未加载到运行服务；启动仍为`.venv/Scripts/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`。下一任务先在合适时机重启服务使v3生效，再另获真实付费调用授权验证同一固定样例；上次授权8次已耗尽。旧稿保留，不自动重跑或伪造成功。真实单主题质量仍未通过（见下文）。

# 当前状态：机制内容质量专项（2026-10-11）

分支`codex/resume-quality`，HEAD `eea4c314fd3b2104ca77b18eea2d9ab606719840`，未创建新提交，上一阶段未提交改动全部保留。本轮未推送/部署、未更新实际.env/依赖/锁文件、未替换8000服务或frontend/dist、未改生产业务记录；固定源码仅只读，未执行外部仓库代码。

## 已实现

复用原生产调用链 `main.artifacts → artifact_service → resume_writer.write → resume_quality.generate`，没有新Agent/第二流水线。候选改为可选机制卡片及原子事实/边界/贡献/结果引用；先DISCOVER，再候选问题驱动固定SHA SOURCE与ENRICH；共享文件/字符/问题账本，预留一次增量容量，允许同一文件新问题读取不同范围。独立核验/选题及旧工作区、取消、幂等、更正指纹规则保持。

写作与审计选中卡片共用writing_pack，仅投递已选支持事实/步骤及有映射的问题，剔除自由机制摘要、个人推测、选题理由/大纲；job_focus只提供关联的JD职责表达重点，不是项目证据。审查将未支持/未实现claims单列状态限制，区分表达/候选遗漏/机制缺失/事实归属。按相应阶段局部修复，两轮/一次增量/原总预算内执行；联合事实与遗漏反馈合并一次重选。模型未绑定确认贡献的个人标签保守降unknown且记录原状态，不放宽check_claims。前端同步显示步骤/边界/分类并兼容旧audit/missing。

复用eval-resume-quality.py增加冻结检查点单主题回归与跨恢复累计8请求上限；原阶段明确replayed，不当作新模型全量发现。fixtures/resume-quality/boundary-review.json保存人工机制/证据/选题/归属/重复/可读性标准。生产API和write入口测试覆盖投递隔离、修订路由与幂等，不以stub或模型自評作为文案质量证明。

## 已验证与真实未通过

- 固定cp-dance提交`21d9b9b43409d13bbcfefc2f26f7cbae2640c3b6`、原JD版本、原材料指纹完整一致；旧输出/阶段记录/恢复输入均保留于忽略提交的`data/resume-mechanism-regression`。
- 最近统一`check.py --e2e`：架构A01/A02通过、后端119 passed（9.60s）、前端typecheck/隔离Vite构建通过、Playwright4 passed（15.9s），退出0。随后联合反馈去重修改与新增回归，全量后端**120 passed（14.36s）**、架构再次通过；最后job_focus轻元数据变更相关生产/API/机制回归**36 passed（5.92s）**。未有当前新增失败。首次E2E初始化竞争失败一次，单测重跑通过；新增“初始旧目标加载完成”准备等待，保留所有提交断言，后续4项通过。
- 实际write离线fixture回归9请求通过，仅控制流/契约证据，不是真实质量结论。
- 用户明确授权一次8请求：DeepSeek deepseek-v4-pro实际累计**8次、API报告62779 tokens**。保留阶段失败/恢复/usage，未发第9次请求。旧参考稿空；本次推进到单主题选题和真实草稿/双审，但简介缺claim、机制仍偏类型/模块介绍、评审误要求上游证明个人归属并误受用户提议影响；局部重核因累计预算停止。没有最终accepted稿或生产Artifact。
- 真实请求后对写作/评审输入隔离、机制补全指令、参考稿归属、同文件补查和共享投影的修正只离线验证，尚未真实复验。不能宣称简历内容质量已达标，也未扩展完整简历。

具体失败分析、同输入前后表与付费阶段记录：`docs/resume-quality-progress.md`本轮章节；原始真实草稿（明确未通过）`data/resume-mechanism-regression/after-unapproved.md`；总结`summary.json`；阶段报告`after-real-01..04.json`。明示参考稿与个人简历归属，未伪造成果/数字/模型输出。

## 尚未解决、阻塞与下一步

单主题真实语义验收未通过：需要从代码中的拒绝/退出参与判定提炼动作机制，而不是介绍接口；评审仍需验证对上游/个人/提议隔离的稳定性。Wiki版本unknown、有限源码窗口不能证明全仓覆盖，完整简历去重/全量新发现质量尚未评估。首次E2E暴露初始化期间目标编辑可被异步choose旧值覆盖的既有风险：本轮测试等待初始加载以验证生成提交契约，未扩大范围修复这一启动期UI行为，后续可独立处理。

阻塞：本轮8次真实调用授权已经全部使用，进一步付费验证需新的明确授权。下一条可直接执行任务：保持原input.json/提交/JD与单主题范围，获得新授权后用已修正流程重提炼拒绝分支，按boundary-review人工逐条核对；该主题通过后才扩展完整简历。不要盲目再跑全仓、增加Agent或扩大上下文。

启动仍 `.venv/Scripts/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`；frontend中`pnpm run dev`。统一检查 `.venv/Scripts/python scripts/check.py --e2e`，Codex环境使用architecture所列捆绑Node PATH和`--pnpm`参数。工作区尚未提交的本轮文件：resume_contract/resume_quality/resume_support、既有写作模板、eval脚本、test_resume_mechanisms、boundary-review fixture、HighlightSelection/ResumeHarness与E2E准备等待、README/PRODUCT/architecture/STATUS/DECISIONS/BACKLOG/resume-quality-progress；上一阶段清理/约束改动也仍未提交。实际全清单以`git status --short`核对。

---

## 上一阶段持续约束记录（历史）

# 2026-10-11 持续开发约束阶段状态

分支codex/resume-quality，HEAD eea4c314fd3b2104ca77b18eea2d9ab606719840，未创建新提交。上一阶段全部未提交整理改动保留；本轮新增/更新仅AGENTS、architecture、README、STATUS、DECISIONS、BACKLOG、code-review、两个检查脚本/对应测试、frontend包管理/类型脚本/E2E隔离配置及.github/workflows/checks.yml。未改业务实现、依赖版本或现有锁文件；未推送、部署、改远端权限、生产数据/实际.env/dist。临时违规文件恢复到修改前原始字节，schemas无最终diff。

已完成：根AGENTS统一短规则和按任务范围读取/复用/替换清理/公共消费者/验证/交付标准；architecture记录当前链路、职责方向、常见修改位置、兼容用途/删除条件及实际命令。既有PRODUCT保存细节，DECISIONS保存选择，不增加重复治理文档。

程序约束只有两项：A01生产不能使用历史resume_legacy/write_legacy（现存评测桥仅允许指定函数内导入）；A02现有公共契约不能经直接/间接导入回到编排。标准库AST扫描含子包/函数内/常见字面量动态导入，不执行应用源码，无新检查框架/依赖。模块更名、新公共契约或真实边界变化需同步规则及其测试；计算型动态加载和语义判断仍人工审查。

本地与CI共享 `.venv/Scripts/python scripts/check.py --e2e`，不带--e2e为核心检查。依次架构/pytest/现有TS typecheck/隔离Vite构建/可选离线E2E；失败和缺工具非零，首个失败后停止。前端packageManager固定当前已验证pnpm@11.25.0、Node24，既有pnpm-lock.yaml不变，CI安装frozen lock及后端requirements.lock。E2E统一入口使用临时REPOCAREER_DATA，单独调用仍data/e2e。Codex环境pnpm不在PATH时加`--pnpm C:/Users/RS/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/pnpm.cmd`并把捆绑Node目录加到本次进程PATH。

已验证：最终统一入口架构通过，**106 passed（7.55s）**，前端typecheck通过、Vite临时目录构建通过、Playwright **4 passed（17.3s）**，返回0。两次真实临时违规（生产→评测、契约→产物服务）均返回1/A01或A02，try/finally恢复逐字节后检查返回0；同一check.py在违规时返回1且未继续pytest/前端。新增检查器/入口回归7项包含间接依赖、子包、导入别名、兼容例外、缺工具和失败停止。没有新增/既有测试失败，未删除或放宽有效测试。git diff --check通过。

CI YAML用现有PyYAML离线解析，核对触发器、只读permissions、frozen lock、同入口及无continue-on-error；pnpm/action-setup@v4输入与上游action.yml核对。GitHub工作流未推送/执行，干净远端安装与runner结果尚未验证；合并保护尚未设置，需未来首次CI运行后管理员在目标分支选择checks为必需项。不能把本地通过等同于远端保护有效。

AI加载：本会话注入证明Codex桌面已读根AGENTS，修改后已主动重读；官方加载优先级/新会话确认方法记录在architecture。未确认使用其他AI工具，未添加CLAUDE/Cursor/Copilot规则副本；通用提示要求先读根AGENTS，必要时手工提供，不能假定自动加载。

仍需判断：新职责是否值得抽象、兼容API何时退役、证据可信度/岗位亮点/真实模型文案质量、未来多进程与摘要优化必要性。静态边界不证明运行正确性或语义质量，既有生产风险见下阶段记录。本轮未调用付费模型或真实业务服务；只查官方规则/动作文档。

启动不变：`.venv/Scripts/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`（单进程），frontend `pnpm run dev`；8000及dist未替换。下一条可执行任务：收到新功能反馈后按AGENTS定位architecture对应落点、复用/清理消费者并用同入口验证；发布/推送及远端保护需后续明确指令，本轮结束。

---

## 上一阶段代码整理交付（历史）

# 2026-10-11 代码整理阶段状态

当前分支 `codex/resume-quality`，HEAD `eea4c314fd3b2104ca77b18eea2d9ab606719840`；审查基线未变化。开始仅有未跟踪 docs/code-review.md，本轮按用户授权更新该报告；源码、测试、README、PRODUCT、STATUS、DECISIONS、BACKLOG 和 .env.example 为未提交整理改动，新增共享组件/产物服务/生命周期和测试文件，删除未使用的 LegacyWorkbench。未提交、未推送、未部署；未更改实际 .env、生产数据库、依赖、Skill/提示词或 AGENTS 开发规则。

已实现：R01 当前编辑目标传递；R02 类型正确的重试拒绝、阶段取消检查、取消后不落稿、停止期间准入占用及异常终态；R03 产物应用服务和单进程/按工作区串行准入；R04 生产共享组件与旧 Markdown 评测基线分离，模型路径改用元数据账本而不渲染规则稿；R05 JD 版本共用历史/词项/失效逻辑；R06 新旧岗位证据/双评审显示；R07 写作模型独立配置、缓存覆盖和显式阶段/JSON协议；R08 init-only脚本已有.env拒绝；R09 当前产品/启动/配置说明校准。R10 只收窄简历轮询并防重叠/显示错误，全量摘要与共享轮询延后。

阶段验证：原基线 89 passed；首批生命周期/目标与现有写作相关回归 49 passed；后续全量 97 passed；TypeScript noEmit通过，Playwright 4 passed（37.3s，离线8001/5173），Vite隔离输出至 data/cleanup-build通过。最终后端 **99 passed（12.46s）**，新增异常收尾/跨工作区回归通过；新旧实际writer同fixture离线契约对比通过（injected、9请求，报告位于临时隔离目录），不是文案质量证据。git diff --check通过。首次移动服务遗漏save_target导入导致3项新增失败，已修复并通过对应回归；基线无既有失败。

保留：显式规则参考稿、旧写作比较基线、旧分析/ZIP/搜索API、来源与更正历史、独立SourceReader和DeepWiki适配器。兼容用途与删除条件见 code-review.md；未按“待核实”结论删除代码。

剩余风险：准入是单个后端进程内的锁，不支持多worker/多进程分布式互斥；已发HTTP模型调用不能撤回，取消在下一阶段及保存前生效；同步生成断线恢复仍依赖Run记录与原请求；workspace summary仍带历史Wiki/audit，数据量增大后的收益需实测。真实模型质量未复验，离线检查不证明文案质量。此前真实质量失败记录仍见 resume-quality-progress.md。

启动方式不变：根目录 `.venv/Scripts/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`，frontend `npm run dev`；不要启用多个uvicorn workers。现有8000服务及 frontend/dist未替换，本轮检查只启动隔离测试服务。

下一条可直接执行任务：用户确认进入“持续约束”阶段后，依据 code-review.md 第8节选择少量边界约束；本轮不搭建治理工具、不追加重构。新会话先读AGENTS/PRODUCT/本状态并核对Git。

---

## 上轮功能交付记录（历史，非本轮验证）

# 2026-10-11 当前状态（后文为历史记录）

当前分支codex/resume-quality，起点ec2b8fce5ca58304573ff4d7b26b4465fe171715；本轮后端/前端/Skill/测试/fixture/评测脚本及文档已整理为提交，按用户新指令发布GitHub master；具体提交与推送状态以Git记录核对。启动命令不变：`.venv/Scripts/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`；frontend中`npm run dev`。已确认无运行任务后重启8000本地服务，监听PID19308；首页200并加载新版bundle，OpenAPI含target接口。已完成隔离8001端到端验证。npm不在当前工具shell PATH时可用Codex依赖Node直接运行frontend/node_modules/typescript/bin/tsc、vite/bin/vite.js、@playwright/test/cli.js。

已实现：GenerationContext/原子目标与JD去重/Run trace，固定SHA只读补证，SourceEvidence/Claim/Metric/结构化Draft，岗位中性调查与结构召回，宽候选/独立核验/覆盖/一次补证重选，独立双审/有界修复，逐段映射/可选成果/贡献模式与参考模式，历史导出兼容。无需SQL迁移，新字段存现有JSON；未追认历史Wiki或旧草稿的核验状态。贡献更正沿用历史与指纹失效保护。界面当前表单传给生成，追问显示在正文外。

已验证：89项后端回归通过；TypeScript/Vite构建通过；Playwright 2 passed；实际新旧writer离线同输入对比通过（fixture控制流，非质量证据）。真实烟测已经执行并暴露结构、ID、状态判定和输出截断问题；一次跑完全流程的结果needs_review且正文剔除，未达到直接使用的语义质量标准。最新真实烟测因核验/选题覆盖契约失败；后续防锚定与unknown覆盖修复仅通过离线回归，真实质量未复验，详细证据见[优化进度](resume-quality-progress.md)。

未完成/风险：真实新旧输出人工评分、跨仓库/跨岗位泛化验收；DeepWiki无固定ref；定向源码读取受范围预算限制，没有运行源项目测试；同模型双审可能漏错或过严。不存在账号凭证阻塞，本轮模型调用使用现有配置，密钥未写入文档。

恢复先读AGENTS/PRODUCT/本状态，并核对Git；按需DECISIONS/BACKLOG。下一条可直接执行任务：查看data/resume-quality-real-delivery.json的trace/正文，人工核对所引固定SHA源码，填写质量评分；如失败按具体阶段定位，禁止取消事实guard凑正文。具体改动与限制见resume-quality-progress.md、离线对比见resume-quality-example.md。

---

# 当前真实状态与恢复

最新修复：GitHub clone的git-upload-pack连接被重置；官方codeload下载成功，已增加带路径/体积检查的下载备用方式。2026-10-09，MultiAgentPPT重试已读取479文档并进入embedding阶段，Wiki/架构评审尚未完成。主应用PID24564/8000，DeepWiki PID21712/8002；旧进程记录为历史。31项pytest通过，覆盖下载路径安全、现有目录保护及错误分类。后续旧状态按时间保留，不代表当前仍未配置模型。

2026-10-09 Asia/Shanghai。当前为GitHub链接首版；分支master，无提交。工程文件全部未提交，涵盖backend/frontend/fixtures/scripts/docs、AGENTS.md、README.md、.env.example、.gitignore。数据、密钥、依赖、构建与测试产物忽略提交；未部署、未创建PR。

## 已实现

GitHub仓库链接 → 岗位名称/JD → DeepWiki-Open comprehensive Wiki → 架构必要性评审 → 对话讨论与更正 → 确认个人贡献 → 简历Markdown。

首页已移除打包上传要求；链接保存API校验规范https://github.com/owner/repo，直接发送URL/type=github/comprehensive=true给DeepWiki，按github类型读取缓存。换仓库使旧方案与简历待复核。链接保存不冒充已下载仓库，未固定Git提交；Wiki源码引用跳转GitHub HEAD，明确由外部服务提供、需核对版本。旧ZIP API/历史记录保留兼容。

架构建议先说明实际问题、已有解法、必要性、替代方案、代价与验证，再关联JD；最多3项且允许维持架构、不引入Skill/MCP/multi-agent。Wiki失败/截断/路径不匹配显示覆盖限制。无服务配置明确失败，不回退函数模板。演示必须明确勾选，报告不分析链接仓库或实际JD。

真实报告后对话使用DeepWiki检索聊天；单LangGraph Agent/按需Skill与结构化贡献记忆保持。项目分析更正保存为用户确认材料，后续对话参考、旧简历待复核；不静默改写原Wiki。个人贡献由用户确认状态与归属，版本化更正保留历史。已验证需报告与范围/来源/限制，未完成建议不进入简历，无依据数字不输出。

## 最近验证

- pytest：29 passed（含旧逻辑、上传兼容、链接校验/幂等、换仓库失效、DeepWiki github payload与cache类型、路径与覆盖、隔离、更正传播）。
- TypeScript、Vite生产构建通过。
- 新版Playwright E2E：1 passed。GitHub链接保存、岗位JD、显式演示报告、讨论、贡献确认、简历、更正状态后旧稿待复核、刷新保留；无pageerror，390px无横向溢出。使用独立data/e2e。
- 真实DeepWiki服务/模型/embedding、真实全貌分析与对话质量未验证。mock/E2E演示通过不能视为真实语义分析验证。

## 启动与恢复

应用运行在 http://127.0.0.1:8000 ，本轮因后端入口变更重启；会话/系统停止后须核对端口。根目录运行 powershell -ExecutionPolicy Bypass -File scripts/start.ps1 。前端变更后frontend执行pnpm run build；后端变更后重启。README/.env.example说明配置。data保存用户记录，不得覆盖；数据模型沿用冻结迁移。

## 限制、阻塞与下一步

未配置DEEPWIKI_BASE_URL，当前可保存链接/JD、预览明确演示、讨论规则提示、记录贡献与简历；真实分析待服务配置。现有Ollama/qwen2.5:3b尚未作为正式组合验证，embedding未验证，没有下载模型。

GitHub链接模式无需共享本地源码目录。DeepWiki可能复用缓存且当前不固定提交；Wiki引用不等于本应用读过源码。取消只停止本地等待，外部任务可能继续。不执行用户仓库代码；本地单用户无认证，不公开部署。简历事实筛选较保守，尚无任意文字风格编辑。

下一条可执行任务：有可用DeepWiki服务后设置.env的DEEPWIKI_BASE_URL/provider/model，重启，填入真实GitHub仓库链接，验证Wiki、架构建议、GitHub引用、对话更正与简历；人工核对模块/链路/必要性，记录真实质量与版本/覆盖限制，修复实际接口差异。不要把未联调写成已验证，不自动扩展功能。

## 2026-10-09 模型配置进展（覆盖上述“未配置”的旧状态）
已访问本机Ollama http://127.0.0.1:11434，qwen2.5:3b存在；下载nomic-embed-text约274MB。GPU推理出现0xc0000005，切换请求num_gpu=0后生成成功、embedding返回768维。独立DeepWiki源码在data/deepwiki-open，版本d92819a9c9f3b99416e3580ff235fc9d3adf8b89；独立环境data/deepwiki-venv安装进程曾启动，需核对是否完成，尚未验证服务启动与真实Wiki。不能把配置写入等同服务运行。
本机.env已写DeepWiki地址8002/provider=ollama/model=qwen2.5:3b。scripts/configure-deepwiki.py可恢复CPU模型设置及上游Ollama options嵌套修复；scripts/start-deepwiki.ps1启动8002，尚未运行验证。
用户最新反馈认为3b太差，希望选择更强模型；当前转为提供云API配置方案，未擅自更换模型或产生云调用费用。下一步用户选择服务商/模型后，配置DeepWiki侧密钥与本项目provider/model；安装依赖完成后启动服务、重启主应用并验证真实调用。凭证只写本地.env，不记录密钥。Ollama本地embedding可继续使用。

## 2026-10-09 DeepSeek配置与实际验证（当前状态）
用户授权后已将密钥写入忽略提交的DeepWiki服务.env，主应用provider=deepseek、model=deepseek-v4-pro、baseURL8002。未将密钥写进文档或测试。真实/models认证HTTP200，账号返回deepseek-flash和deepseek-v4-pro；关闭thinking的短生成HTTP200返回OK；DeepWiki DeepSeekClient真实调用data=OK/error=None。
独立依赖安装完成并冻结scripts/deepwiki-requirements.lock.txt。DeepWiki服务PID26240/会话57884/8002 health healthy；主应用PID8140/会话93462/8000配置显示deepseek-v4-pro。恢复启动见README。上游补丁scripts/deepwiki-local.patch记录DeepSeek映射、嵌套Ollama options、embedding完整tag修复。后端29 passed。
检索smoke尚未通过：Hello-World无支持扩展名文档，上游索引0条；Spoon-Knife遭遇GitHub连接443失败。模型配置/API验证成功不等于全仓库分析完成；普通网络错误继续定位，不能伪造Wiki。下一步测试含支持源码/文档的小仓库，确认GitHub可访问后验证索引、检索和comprehensive Wiki。


本次反馈为缺陷：错误发生在仓库下载而非模型配置；提示已按下载/embedding/其他生成分类，改为保留“仓库链接与JD”。上游补丁更新scripts/deepwiki-local.patch，新增帮助文件scripts/deepwiki_archive_fallback.py由启动脚本复制到上游api。检索归档不包含.git，不保证固定提交；下载100MB、展开300MB/50000条目预算，不执行源码。原计划重复clone改为官方archive备用，不使用第三方镜像。下一条可执行任务：查询Run c12125934e8949d388e0b23a74d1af32与DeepWiki同名任务，确认embedding/Wiki生成是否完成，定位后续阶段实际失败，检查超大文件跳过范围；只有完成报告后才记为整链路验证。

## 2026-10-09 13:01 状态检查
用户反馈持续分析中。实际DeepWiki任务status=indexing/pages=0，无error；Ollama ps为nomic-embed-text:latest 100% CPU（表示CPU运行模式，不是CPU利用率百分比），日志于13:01仍更新，处理任务号已到1062。真实下载12:54:41成功，479文档拆分约5个批次，约6分钟后仍在向量计算；尚未开始Wiki页面生成。当前没有死锁/停止的证据。界面只使用Wiki页数0/0，索引阶段缺少细粒度进度，不能据此解释为0%或模型没有工作。索引包括部分构建/依赖类目录，可能增加工作量；未在进行中重启或重新下载，以免丢失当前进度。后续需增加索引进度，并按实际目录清理范围评估排除生成产物；不能静默缩减源码覆盖。

## 当前：云端embedding切换（覆盖旧CPU索引状态）
用户授权使用qwen3.7-text-embedding-flash，密钥保存于忽略提交的服务.env，无文档密钥。官方北京接口HTTP200/1024维；DeepWiki真实Embedder调用2条/error=None。每批20条，生成模型仍deepseek-v4-pro。
已停旧Sidecar/CPU任务，保留旧索引；新索引按模型/维度/端点独立namespace=99bdc9b98108a216。已修复启动脚本强制ollama导致.env失效，当前读取.env协议类型openai（实际提供商百炼）。服务重启PID12860/8002、主应用PID23788/8000。恢复Run c12125934e8949d388e0b23a74d1af32，复用已下载源码，重建云索引。完整Wiki及评审完成情况仍需另查，不把2条测试当全仓库完成。
分支master，工程仍未提交。恢复命令scripts/start-deepwiki.ps1与scripts/start.ps1。依赖/上游补丁/模型说明见README。下一步查询该任务与索引日志，确认批量embedding、Wiki及架构建议生成；若失败定位实际阶段。

云端仓库索引实际验证：已复用下载目录，日志103批embedding，约14秒完成27批（当时约26%），无接口错误；不是只做2条烟测。完整Wiki任务仍处理中，批次进度不代表Wiki总进度。用户页面继续显示分析中，云端embedding无需Ollama运行。

## 最新：Wiki流式DeepSeek注册修复
用户询问服务器中断：检查主应用8000与Sidecar8002均存活，实际Run为failed。13:12云embedding已完成2053个1024维片段、FAISS成功；随后目录规划报Provider deepseek not registered。之前只验证配置映射/普通客户端，遗漏ChatStreamer注册，这是接入缺陷而非余额或embedding故障。已新增DeepSeekChatStreamer，使用官方OpenAI兼容chat streaming与thinking disabled，真实流式测试返回OK；Sidecar重启PID9940/会话48760，主应用仍PID23788/8000。原Run已安全重试，索引可复用，不重算云向量。上游补丁已保存scripts/deepwiki-local.patch。
旧interrupted状态来自配置切换时主动重启主应用，不能解释成服务崩溃；本次failed与旧状态区别应说明。当前尚未验证全Wiki与架构评审完成。下一条任务查询原Run及Wiki目录生成进度，若有后续实际失败按阶段修复，不重复做embedding。

## 最新：架构评审校验失败诊断与修复
用户反馈原Run c12125934e8949d388e0b23a74d1af32两次校验失败。数据库确认21页Wiki已保存，失败在架构评审。原始输出未记录，不能追认原失败的具体字段。复用保存Wiki进行了真实两次诊断调用：第一次JSONDecodeError line229/column107，why_now文本混入_how_now字段片段；第二次通过JSON、Pydantic及允许引用路径校验。诊断输出仅在忽略提交的data/review-response-*.txt，不进入贡献记忆，不写成正式报告。
已实现：记录最近10条结构诊断（字段位置、错误类别、简短原因、输出长度，不存原始输入/密钥）；修复提示包含具体校验错误及上次输出；最终错误保留具体原因。保持源码引用校验，不静默删除错误字段或伪造路径。普通DeepWiki问答提示要求Markdown与评审严格JSON存在格式冲突；尚未实现专用结构化生成接口/JSON mode，因此不能保证从根源消除偶发格式错误。
验证：后端34 passed（含未知路径拒绝及精确修复、JSON/字段错误诊断）；真实诊断第二次通过不等于新修复逻辑已完成真实正式报告验收。原Run仍failed，21页Wiki保留。主应用已重启PID26204/会话64118/8000，Sidecar8002保持运行。
分支master，工程未提交。启动仍scripts/start.ps1及scripts/start-deepwiki.ps1。下一条可执行任务：对原Run安全重试，只重新评审；检查review_diagnostics与报告，人工核对必要性和来源，不重建Wiki。建议后续提供专用JSON输出模式、压缩重复材料、路径标识映射；这些建议尚未决定实施。
## 当前交接：完整项目简历参考稿（D012）
用户明确要求原项目提炼为简历主体，融合用户优化，优化允许讨论设计且允许自主补充数据，无讨论也可直接生成参考稿。已实现独立resume生成路径：当前快照Wiki/结构报告提炼项目目标与技术架构，JD排序最多三项用户优化，分别表达设计/尝试/实现/验证；预期结果和用户补充未核验结果保留来源标签，已有对照材料限定范围。原task_pack/interview_notes逻辑保留。确认的讨论设计无需填写个人职责，已实现/已验证仍需职责；讨论消息不自动变已完成贡献。更新界面说明、产品规则与运行时Skills，D012记录替代旧选材限制。
验证：后端36 passed（无讨论Wiki生成、状态/用户指标/更正传播、原工作区隔离）；TypeScript与Vite生产构建通过；Playwright核心流程1 passed，最后小表单调整后再次验证结果见执行记录。当前真实MultiAgentPPT已生成参考稿artifact 2122245f999e453499f155ecc59f0f7f/v2，包含A2A/ADK/MCP与业务链路，未添加用户未确认的优化。当前Run已有结构评审报告，说明此前failed状态已被后续重试替代，但架构结论仍需人工核对；不把生成完成当代码运行认证。
当前分支master，所有工程仍未提交。启动scripts/start.ps1（8000）与scripts/start-deepwiki.ps1（8002）；最新后端重启见执行记录。主要变更memory.py、schemas.py、Discussion.tsx及测试/项目文档，无数据库迁移，无额外模型调用。网页刷新后点击“生成项目简历参考稿”。
已知问题：确定性提炼较长段落会截断，当前是可编辑参考用途；未实现模型精修/完整STAR语义规划。固定Git提交、缓存更新及专用Markdown评审仍未实施。下一条可直接执行任务：查看当前参考稿，按用户反馈精简技术设计措辞；需融合想法时保存“仅讨论”优化并生成新版，核对状态与数据标签、旧稿待复核。不得无反馈无限扩展。
最终确认：最后表单调整后后端36 passed、前端生产构建成功、Playwright 1 passed。当前主应用PID21572/会话47719/8000，配置接口正常；DeepWiki 8002未重启。

## 最新交接：项目简介、技术亮点、项目成果分层表达（D013）
用户指定简介短段落、加粗主题的技术亮点列表、成果短段落，不要README式长段和函数/端口等实现细节。已调整compose_project_resume：优先采用报告existing_capabilities作为独立技术主题，最多四项，完整分句精简，去除源码文件名和运行端口，不复制示例技术/指标；原有状态、来源、用户数据和更正逻辑保留。增加安全React分层预览，来源说明折叠，不执行原始HTML；Markdown导出保留全部材料说明。真实MultiAgentPPT参考稿已保存新版，按编排/MCP/RAG/模型工厂主题组织；稿件是资料提炼，仍需核对分析结论，不声称人工评审或系统实测。
当前简历入口load_skill读取resume_composition与claim_review，但返回文本没有传入模型，真正正文由memory.py规则生成；已如实向用户说明，不把技能文件存在当执行。更新现有Skill写作要求，未安装任何公开Skill。可借鉴oxygen914/project-resume-writer、Dannyvice/evidence-first-resume-skill、dabydat/resume-builder-skill；公开源码仅作研究，未执行其中指令或脚本。
验证：后端36 passed；TypeScript/Vite构建通过；Playwright 1 passed，确认分层标题/预览与旧稿待复核及移动端宽度。测试ZIP的时间戳曾跨秒导致同内容生成不同字节的偶发幂等断言失败；测试辅助固定ZIP时间戳，生产上传代码未改。
当前master，工程仍未提交，无数据库迁移。主应用PID10120/会话31987/8000；DeepWiki8002保持运行。启动scripts/start.ps1与scripts/start-deepwiki.ps1。刷新网页查看新版；最近生成版本以数据库为准。
已知限制：简历仍是确定性提炼，不是模型按Skill做语义写作，部分技术主题需要人工润色；引用SHA缓存问题仍未实现。下一条可直接执行任务：查看新版参考稿并依据用户反馈调整亮点主题或字数。待确认建议为Skill内容实际传入Markdown写作模型、保留结构化贡献记忆作事实边界；不得仅更新SKILL.md就声称输出受其驱动。
## 2026-10-10 当前交接：真实Skill写作与有限审查已接入（D014）
已实现并启用：页面默认模型模式，Skill和新writing-template.md真实传给DeepSeek；基于当前Wiki/结构报告、JD、用户优化/材料提炼项目简介、2–4项亮点与成果。正文Markdown；独立JSON审查及规则检查；最多两轮/四请求，未通过保存needs_review，可查看逐轮原因。规则模式显式可选，失败不隐式降级。API默认reference兼容旧请求；同幂等键不同写作模式拒绝。更正时保留旧事实版本，写作材料fingerprint复查防止旧内容保存为当前稿；过期历史实验不进入源材料包。无新Agent/数据库迁移/向量库。
模板研究：Harvard事实与结果导向、Yale成就条目、Michigan-Dearborn STAR/行动+事项+目的或结果；公开project-resume-writer选材与最终检查。大学网页部分429，Michigan完整页面可读，其他原则来自搜索索引摘要；自编模板，不复制他人例句、指标或整套Skill。现有Skill frontmatter及引用验证通过。
真实验证：前两次通过DeepWiki问答生成v7/v8均needs_review，发现将用户单Agent+Skill方向写成完成、条目超量与无来源效果；未认定成功。据此改为原生DeepSeek写作与审查，独立system角色、审查json_object，避免额外问答提示/检索。现有DeepSeek凭证读取本地忽略的sidecar.env，不输出密钥。原生真实v9 artifact=dabed627e43b48f9bb58cfd43001fb3e，初稿审查发现重复与推断描述，修订后第二次通过，review_status=current；没有虚构量化指标。模型通过不等于人工证实，应核对用户经历。用户未指定完成状态的陈述标unconfirmed，不能据此推断已重构；想法需确认保存为设计状态后选择进入稿件。
最新验证：后端44 passed（有界修订、具体问题反馈、新指标/技术拒绝、JSON审查失败标待复核、原生系统消息/JSON模式、写作期JD/贡献更正拒绝、幂等与失败不替代）；TypeScript/Vite构建成功；Playwright 1 passed（规则预览、分层显示、更正待复核与移动端）。真实模型调用经API验证，浏览器演示测试不冒充云模型质量验证。Skill quick_validate UTF-8模式通过。
当前master，工程仍未提交。主要新增backend/app/resume_writer.py、Skill references/writing-template.md、tests/test_resume_writer.py，更新main/schemas/Discussion与文档。启动scripts/start.ps1/8000及scripts/start-deepwiki.ps1/8002。当前主应用PID16488/会话16737，SidecarPID9940仍8002；写作不借用sidecar聊天，只用已保存Wiki与其现有DeepSeek凭证。可用RESUME_MODEL_*覆盖，示例与README已更新。
已知问题：相同模型自审可能漏事实错误，常见技术/数字规则不是完整语义证明；写作context按页面摘录最多40000字符，保留覆盖元信息，未声称每行代码已读。写作请求同步等待，界面显示处理中，尚未实现断线后后台恢复/细粒度生成进度。固定Git提交和缓存新版本检测未实施。下一条可执行任务：刷新页面查看v9，确认是否符合用户目标岗位和简历表达；用户新增/确认优化设计后生成新版并检查状态与指标来源。不要重复生成或无限审查以追求模型自评分。
## 2026-10-10 当前交接：HR/技术面试官视角先评选亮点（D015）
用户要求模型根据JD先以HR/面试官角度判断值得写的亮点，再写简历。已实现原生SELECT JSON阶段：岗位关联、HR价值、面试追问、选择理由、允许材料编号及状态，最多四项，允许证据少时一项，不强加JD关键词。程序验证编号/状态，未完成或未确认材料不能作为既有/已完成能力的依据；正文标题与顺序须匹配评选。选择记录进入writing_review.selection，页面HighlightSelection可展开查看，正文不混入HR评价。评选一次+最多两轮写作审查，总计最多五请求，不新增子Agent。
真实验证：v10初次模型自审通过，但进一步规则核对发现将评测材料不足写成体系尚未建立；已标needs_review，保留正文及原审查，在audit追加post_validation失败记录，未静默改成成功。补充不把未提及等于不存在的规则与写作要求，相关测试通过。真实v11 artifact=34d543d855854f179e38b03e564a4ede：先评选四个岗位主题，生成后第一轮检查通过，review_status=current；没有新增性能指标。模型检查不是人工认证。v11正文含编排/并行、MCP集成、RAG、模型工厂；选题依据可查看。未把尚未确认的单Agent+Skill方向写成已重构。
最新验证：后端45 passed（加入选题编号/状态/混合计划拒绝、选题传入正文和五请求上限、缺失断言阻止）；TypeScript/Vite生产构建与Playwright 1 passed；Skill UTF-8 quick_validate通过。页面演示测试仍显式reference，真实模型评选/写作经当前项目API验证，不冒充独立HR评价。
当前master，工程未提交，无数据库迁移。新增HighlightSelection.tsx，更新resume_writer、Skill、Discussion及测试/文档，保留旧稿与规则模式。主应用PID14412/会话41630/8000正常；Sidecar8002保持原服务。启动scripts/start.ps1与scripts/start-deepwiki.ps1；写作直接用已有DeepSeek配置，源码不执行。
下一条可直接执行任务：刷新页面展开v11的“查看岗位亮点评选依据”，用户反馈想强调/排除的主题后更新选材。限制：选材为模型判断，来源编号证明材料存在而非逐句语义事实证明；不输出ATS/录用概率，证据不足只记无法确认。任务恢复/固定SHA等旧问题仍未实施，不因本次选题新增独立Agent或无限循环。
## 2026-10-10 当前交接：工程亮点内容卡片与证据补充（D016）
已实现：选题卡片（问题/机制/取舍/结果/贡献/缺失问题），完整Wiki本地保留并纳入材料指纹；初选后按引用页与关键词补充段落，18000字符预算，不将完整Wiki直接灌入提示。写作/审查仍最多五请求，允许删减、重排、合并到已有主题，拒绝新主题。评审结构化分类rewrite/needs_evidence/future_work，改写问题触发有限修订，其余供用户补材料或后续讨论；页面展开卡片和反馈。更新既有Skill及模板，未增加Agent、迁移或自动爬取。
验证：后端49 passed，包含末尾段落召回/预算、主题调整边界、追问不写成果和改写触发修订；TypeScript/Vite通过，Playwright核心流程1 passed。真实原项目模型稿v12 artifact=7ed1094d246c46c480a0d933620c2418，补充61段、4张初选卡片、正文3条主题，首轮passed/current；无虚构性能指标。模型通过不是人工质量认证；没有已标注多项目评测集，不宣称内容质量提升比例。最后补充审查卡片动机/取舍的提示后运行验证见后续结果；v12是该补充之前生成。
限制：关键词检索而非语义检索；卡片来自初选，正文读取补充材料但卡片未再次自动更新；模型可能合理化设计动机，需来源核对；资料追问在页面展示，用户需沿现有讨论/贡献入口补充，不自动更改贡献状态。固定SHA/缓存恢复等旧问题仍未实施。
当前master，所有工程未提交，无数据库迁移。主应用重启PID25724/会话48696/8000，DeepWiki8002未修改。启动scripts/start.ps1及scripts/start-deepwiki.ps1，前端dist已构建。下一条可执行任务：刷新查看v12及卡片，人工核对问题/取舍来源，回答卡片missing并在贡献记录确认状态，再生成新版；补充最后提示后需重启主应用生效。自动标注或多项目评测仍待后续范围确认。

最后卡片动机/取舍核对提示已补充，后端49 passed；主应用再次重启以使提示生效（PID18728/会话44915/8000）。v12不因提示更新自动重写，旧版本保留。

## 2026-10-10 最新交接：D017 全块理解、项目价值、独立双评审和Harness
已实现：有效Wiki全部按5000字符分块，每批两块；预编号800字符证据段，模型选择来源、程序填入逐字原文，来源失败每批最多修复一次。未知来源拒绝、不缓存失败；已完成批次按工作区/快照/全文/端点模型/指令隔离复用。上限64批（最多128分析请求）+产品全貌/选题/两轮写作及独立双审最多8请求，超限明确失败，不截断末尾。全貌PRODUCT请求不含JD，提炼用户/场景/背景/价值主张与机制链、限制和不确定性；SELECT再结合JD。HR与技术两次独立请求，不读取对方意见；意见分类、去重，最多一次修订。稳定h1–h4关联支持标题重命名/删减/重排/合并，标记校验后删除，导出无内部标记。重复引用用逐字包含关系合并，保留原文与全部来源ID；最后该去重仅自动化测试，未再重复云生成。
Harness已实现：阶段短Prompt，完整Skill/模板仅写作加载；全貌/选题用紧凑事实包，写作/技术评审回看所选原文，HR不读全量证据。输出Token上限、输入字节保守上界、API已报告总Token预算、调用上限、真实usage/耗时及失败元数据trace（无Prompt/密钥）。缓存仅Wiki映射，个人贡献/JD每次新读取，保留主流程材料指纹更正保护。页面显示全貌、机制链及边界、覆盖/空白页、实际usage和独立双审结果。没有子Agent或数据库迁移。
已验证：后端62 passed，覆盖全部字符/末尾进入分析、来源/原文校验、缓存模型/工作区/材料隔离、失败续用缓存、独立无JD全貌、双审不串读、稳定ID、引用去重、Token预算和失败日志无敏感输入；TypeScript/Vite构建通过，Playwright核心流程1 passed，Skill UTF-8 quick_validate通过。
真实当前项目是qiukuizhenpiaoliang-dot/cp-dance，snapshot=722cf256290e4066aa31d1ae3f789d99，run=0ba886bf677a4954b07fc395e30ac665。14页有效Wiki/142931字符，35块/18批，共155条事实；全部批次已缓存（不是源码覆盖率/理解准确率）。最初页面/片段编号混用和引用失败未生成稿件，改为证据段编号与一次有界修复；全量引用重复导致事实包超预算，紧凑包53784 bytes后复用全部缓存，不重新索引/上传。
真实v14 artifact=69d800cd45ea47559ddefe2c56c8bcfe，双审运行后needs_review，暴露标题精确匹配误拒绝及HR过拟合JD；保留历史。修复为稳定ID和HR职责边界。最终v15 artifact=9f7260301e3a40bd901d774f35803c25，18批全部cache hit，下游8次真实调用、两轮，仍needs_review。最终两角色approved=true但还有rewrite意见，合并逻辑保持待复核，不把审批布尔值当全部问题解决。HR建议涉及JD的Python/FastAPI与项目TypeScript实际栈差异及RAG可迁移表达；没有虚构技术补齐，不无限循环。v15 API报告总154897 Tokens，只是本次8调用，不含早期冷分析/诊断费用；早期调用无完整usage记录，不能追认总成本或节省比例。
质量比较：新增scripts/compare-resumes.py生成工作区限定的人工表。data/resume-comparison-v13-v15.md材料指纹不一致，仅描述比较；data/resume-comparison-v14-v15.md指纹一致，可对本次修复做人工比较。待人工填写，不宣称输出质量已提升或自动评分认证。
当前master，工程全部未提交/初始未跟踪，新增resume_harness.py、测试、ResumeHarness.tsx和比较脚本，修改resume_writer/Discussion/Skill/文档，未覆盖用户导入代码。启动scripts/start.ps1（8000）与scripts/start-deepwiki.ps1（8002）；前端dist已构建。最后主应用重启见下一行，Sidecar未修改。
未完成/已知限制：不保证DeepWiki覆盖全部源码；无Github源码自动补证、固定SHA缓存更新、精确模型tokenizer或价格计算、局部修订、后台进度/断线恢复、人工标注多项目质量基准。模型同源双审仍可共有偏差；价值链与设计动机需要来源核对。超大事实包明确报预算错误，不能宣称任意仓库都能处理。
下一条可直接执行任务：刷新查看v15背景价值、链路限制、覆盖和双审意见，核对项目技术与目标JD差异；对有依据的材料缺口沿讨论/贡献入口补充并确认状态，再按最新材料生成。不要为了通过HR建议虚构Python/FastAPI、RAG或团队协作经历。

最终主应用PID7136/会话63115/8000；包含引用去重与失败trace的最新代码已启动。GET / HTTP200，前端最新构建可用。

## 2026-10-10 页面空白缺陷修复（最新）
用户打开项目空白。HTTP200/前端资源正常；用真实工作区恢复复现TypeError reading length。后端selection.model_dump(exclude_defaults=True)会省略空omitted数组，HighlightSelection直接读omitted.length导致React整页渲染失败。改为可选长度/空数组兼容，同时兼容缺selected。保留所有数据，不清空localStorage、不重新分析/生成、不调用模型。
验证：真实8000页面使用当前工作区恢复后pageerror=0，讨论区显示；TypeScript/Vite构建通过，Playwright2 passed（新增恢复带省略默认数组的模型稿回归）。此前仅演示参考稿流程遗漏该场景，不能把原E2E通过说成真实模型记录已验证。主应用保持PID7136/8000，前端新资源index-Ca6RC9ly.js，未改后端。分支master，工程未提交。
下一条直接任务：刷新当前浏览器加载新资源，查看v15及反馈；缺少材料的JD要求仍不可补造。

## 2026-10-11 D018 当前交接：整体架构、JD补证与主题合并
已实现：产品全貌新增product_flow、architecture与key_chains，链路来源只能引用项目材料；新增独立JD_PLAN（最多6问题），本地按问题均分18000字符预算检索完整证据段，再SELECT核对匹配/合并链路并生成outline。写作与双评审读取整体主线、检查已选机制遗漏与重复。JD匹配direct/partial/unconfirmed，原机制与优化状态分开。页面展示闭环/架构/问题/大纲；来源错误提供安全字段位置，不输出模型原文或密钥。全貌/规划尚未缓存，原Wiki缓存继续复用。下游9次、含分析修复最多137次。
已验证：后端67 passed；TypeScript与Vite生产构建通过（index-Be3zmhB9.js）；Playwright2 passed。回归包括JD先于选题、全貌无JD、末尾检索/预算/未知、链路拒绝非法或计划引用、合并不提升状态、更正与隔离沿用。E2E首轮因依赖旧文本及复用测试工作区失败，改为每次创建独立测试工作区和校验真实保存状态后通过，不删除用户数据。
真实cp-dance调用：首次选题校验拒绝，未创建新稿；当时错误位置未保留，不能追认具体字段。增加安全诊断后第二次正式调用成功保存v16，artifact=5e22cedf5d6e4734843f93bd2bda9c7b，仍needs_review。6个JD问题，9请求、18批Wiki缓存，API报告总199518 Token；其中JD规划1176 Token，不包含首次失败成本，不声称整体省Token。正文包含AgentEngine编排/多Runtime、版本化私有记忆/上下文、同意边界，仍需人工核对Wiki与作者原意；不是已确认个人实现。
未通过项：两轮后仍有完整闭环措辞、成果中未确认改造方向、重复及额外机制选材意见；未降级或无限重试。模型第二轮漏技术亮点标题，新增仅补标题的确定性格式修复，测试通过；未重新生成真实稿验证，历史v16保持原文/待复核。评审对未选主题的意见可能过度扩大选材，质量尚未人工认证。关键词召回可能漏同义词，全事实包与全貌保留作补充；不能保证全面理解。
恢复：master，工程全部仍未提交/未跟踪，未建提交或迁移，主要变更resume_writer.py、ResumeHarness/HighlightSelection/Discussion、测试、Skill及现有项目文档。启动scripts/start.ps1或.venv/Scripts/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000；DeepWiki仍scripts/start-deepwiki.ps1。本轮最终主服务重启状态见执行日志，HTTP验证见下文。
下一条可执行任务：刷新当前工作区展开v16，核对主题/架构是否符合作者原意及目标JD，对待复核意见逐项给出人工取舍；使用同材料基准对比后再决定语义召回或模型变更。不要将结构实现与测试通过写成简历质量改善认证。
最终服务：主应用PID3372/会话21955，首页HTTP200；真实当前工作区v16展开全貌/JD候选证据/大纲，Playwright检查pageerror=0、Agent运行时架构可见。
2026-10-11 GitHub发布准备：用户授权发布。目标账号Floraaaaa-mdd，默认RepoCareer私有仓库；上传前71个源码/文档文件扫描无常见密钥模式，data/.env/依赖/构建已忽略。当前GitHub连接器无法创建仓库，本地Git未登录，已准备首次提交；远端创建及推送尚未完成，下一步完成GitHub CLI设备登录后创建并推送，核对远端SHA。

2026-10-11 GitHub发布：用户确认RRX12；私有仓库https://github.com/RRX12/RepoCareer，默认master。71个源码/文档文件全量上传，远端树542d17132f474e812831cbc93903dad4ec53a49c与原本地树一致；data/.env/依赖/构建排除。Git HTTPS网络失败，改用官方API。首版352bbecc14ad08dfb2dd7927986efb410cfef640，本地分支同步，原提交保留codex/local-initial-mvp。发布记录另提交上传；运行代码不变，既有启动、测试及质量限制沿用上文。下一条任务：按反馈核对v16主题及事实，继续开发。常规git push仍可能受本机网络影响。
