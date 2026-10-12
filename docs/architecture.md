# 当前架构与开发定位

本文件描述生产结构和检查边界，不保存方案历史；取舍沿革见DECISIONS，产品规则见PRODUCT，实际验证/恢复见STATUS。当前为单后端进程本地MVP，未实现多进程准入或后台简历队列。

## 生产入口与调用链

| 流程 | 实际调用链 |
|---|---|
| 页面 | frontend/index.html → src/main.tsx → architecture-entry.tsx；Discussion负责讨论/贡献/简历，ResumeHarness/HighlightSelection/ResumePreview负责审计/选题/正文显示 |
| GitHub及架构 | FastAPI main.repository-link → SourceReader.resolve_revision → Snapshot；architecture-runs → analysis.submit/execute_architecture → DeepWikiOpen → Wiki/架构契约校验 → Run/Evidence/报告 |
| 讨论及更正 | main.messages → agent.chat（LangGraph+按需Skill+只读工具）→ 用户确认 → memory贡献/证据/MemoryEvent → invalidate依赖草稿 |
| 目标 | main.jd-versions和target/产物目标 → memory.save_jd_version/save_target → JD词项/版本/历史/失效，同事务保存role/JD |
| 模型简历 | main.new_artifact → artifact_service.create_artifact → 按工作区准入/冻结GenerationContext → resume_writer.write → resume_quality.generate → Harness/SourceReader/resume_support.WritingModel → 结构化Draft/独立HR技术审查 → resume_contract.render → 指纹/状态核对 → Artifact和Run终态同事务 |
| 规则参考稿 | 显式writing_mode=reference → memory.compose_project_resume → Artifact；不在模型失败时自动降级 |
| 运行状态 | 架构任务由analysis executor登记；同步简历由task_lifecycle保持请求占用。cancel条件更新Run；简历每阶段/保存前检查状态，已发HTTP不能撤回；通用retry不能投递简历，原产物API负责版本校验后重试；启动recover_runs将未结束Run标为interrupted |

## 职责与依赖方向

- main是HTTP参数/错误/路由入口，产物编排在artifact_service；analysis处理架构和兼容分析executor。不要复制第二条模型生成保存路径。
- memory处理贡献版本、JD版本、证据和依赖失效；db是ORM/SQLite，migrations是数据库变更入口。多表读快照、短事务和工作区限定保留。
- resume_quality负责调查/候选/核验/有界写作和审查；resume_contract负责GenerationContext、Claim/Metric/Draft等契约、程序校验及确定性渲染，不读取业务编排。
- resume_support提供中性项目全貌契约、材料收集、元数据账本、模型HTTP及缓存配置；resume_harness负责请求预算、分块/缓存/用量记录，不替代语义质量验收。
- SourceReader只读固定版本源码/材料，DeepWikiOpen适配上游Wiki/聊天；它们与写作HTTP有不同协议，不强行合并成通用框架。写作配置RESUME_MODEL独立于DEEPWIKI_MODEL。
- schemas/architecture_schema/resume_contract可依赖现有中性契约/源码证据和确定性校验，但不能经其他模块间接回到main、artifact_service、analysis、agent、memory、task_lifecycle或生产writer编排。
- resume_legacy是历史Markdown评测基线；可读取共享组件，生产不能反向使用。唯一兼容桥为resume_writer.write_legacy函数内直接导入该基线，供显式比较脚本/测试使用，不是API降级选项。

## 常见修改落点

| 修改 | 正常修改位置/消费者 |
|---|---|
| 简历主题数量或格式 | resume_contract的Choice/Draft/渲染、resume_quality选材/写作限制、Skill模板、ResumePreview/审计展示、PRODUCT及fixture/公共入口测试；旧评测基线不随新格式强行改写 |
| 模型端点/客户端/缓存 | resume_support.WritingModel/cache_directory、.env.example、配置及MockTransport测试；更换DeepWiki模型改sidecar，不同步改变简历模型策略 |
| 增加证据来源 | SourceReader/SourceEvidence、resume_support.collect、resume_quality.material_evidence/核验、契约/展示和隔离回归；持久个人材料还查schemas、db约束、memory.attach与migration |
| 任务取消/重试/轮询 | main状态命令、analysis或artifact_service/task_lifecycle对应类型、Harness阶段检查、architecture-entry/Discussion及重启/幂等/隔离回归；不能把resume Run交给旧analysis队列 |
| JD或贡献更正 | memory唯一版本/失效入口、API输入/所有消费者；保留MemoryEvent、贡献乐观版本与生成指纹 |

跨层功能涉及多个文件是正常的；是否新增抽象要看实际重复职责，不能按文件数量或长度判断。

## 开发与同一检查入口

安装后端：Python 3.12+创建.venv，`.venv/Scripts/python -m pip install -r backend/requirements.lock.txt`。前端使用frontend/package.json的packageManager（pnpm@11.25.0），`pnpm --dir frontend install --frozen-lockfile`；不改锁规避失败。Node 24与当前本机一致。CI使用Windows以匹配现有启动/E2E脚本。

启动：根目录`.venv/Scripts/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`，frontend中`pnpm run dev`。已构建部署入口为scripts/start.ps1（frontend/dist）；检查不更新此目录。

完整本地/CI：`.venv/Scripts/python scripts/check.py --e2e`。默认不带--e2e依次执行：

1. scripts/check_architecture.py：AST边界检查，不导入应用或执行源码。
2. 当前Python的`-m pytest backend/tests -q`：临时数据库/mock契约与业务回归。
3. `pnpm run typecheck`：现有TypeScript编译器noEmit。
4. `pnpm run build --outDir <临时目录>`：现有tsc/Vite，临时输出，不替换生产dist。
5. 指定--e2e时`pnpm run test:e2e`：离线fixture应用+Chromium，8001/5173需空闲，数据由检查器临时REPOCAREER_DATA提供。单独执行E2E仍使用data/e2e。

任何失败停止并返回非零，包括工具缺失；检查脚本不包含依赖安装步骤、不跳过检查（应先按锁准备依赖）。未在PATH的pnpm可通过`--pnpm <绝对路径>`指定（Codex环境使用捆绑pnpm.cmd，同时需Node在PATH）。定向测试允许用于小改，但提交前CI使用完整入口。真实模型评测是显式收费操作，不在此入口。

CI配置为.github/workflows/checks.yml（pnpm/action-setup@v4的package_json_file输入已按[上游action.yml](https://github.com/pnpm/action-setup/blob/v4/action.yml)核对）：安装后端固定requirements、前端frozen lock和Playwright Chromium，再调用同一check.py --e2e；不提供密钥，不联系真实业务服务，无continue-on-error。远端尚未运行；干净环境安装及GitHub runner结果不能由本地通过替代。

若以后启用合并保护：由仓库管理员在目标分支规则中选择首次CI运行产生的checks检查为必需项，并确认Actions启用；本轮不修改远端权限，也不把未推送配置称为已启用保护。

## 两项程序约束及维护范围

A01：backend/app（包含子包）的生产模块不能导入resume_legacy或write_legacy；唯一兼容函数内的指定导入除外。局部导入、绝对/相对导入及字面量import_module/__import__同样检查；生产通过模块属性调用write_legacy也报错。
A02：schemas、architecture_schema、resume_contract沿本地导入边不能抵达业务编排模块，错误报告完整依赖链。现有SourceEvidence在SourceReader中，允许读取该中性类型，不为强行分层拆出新模块。

规则位于scripts/check_architecture.py，测试在backend/tests/test_architecture_boundaries.py，依赖仅标准库+已有pytest。维护成本为模块更名、新公共契约模块登记或真实依赖边界改变时同步这两处及本说明；不能把新违规直接加白名单。动态计算模块名、任意getattr/反射、语义事实、运行时状态正确性不由静态检查保证，仍由入口测试和人工审查负责。

## 必要兼容路径

| 路径 | 用途与删除条件 |
|---|---|
| resume_writer.write_legacy → resume_legacy | --compare-legacy/历史基线测试；确认不再需要同输入比较并处理脚本/测试后删除；禁止生产降级 |
| writing_mode缺省reference、memory.compose_project_resume | 旧API及显式离线演示；当前页面仍提供，不能当遗留删除 |
| analysis-runs/repo-snapshots、GitHub.snapshot、AST实践分析 | 有效兼容API/脚本/测试；确认外部调用及退役范围、替代入口后另批删除 |
| repository-upload/import_zip及archive SourceReader | 旧ZIP API/测试/历史快照证据；历史数据迁移与API退役方案确认后再删 |
| 历史Markdown/audit显示与导出 | 既有产物可恢复，不回填证据认证；确认迁移或停止支持历史记录后再退役 |
| configure-deepwiki.py | 没有.env的本地Ollama初始化，已有配置拒绝；取消该初始化支持后可移除，不能覆盖云配置 |

其他待核实字段不列永久规则。完整历史处置证据见code-review.md第8节。

## AI规则加载与简短交付

已确认当前实际工具是Codex桌面，本会话注入的“AGENTS.md instructions for …/AIforResulme”证实根规则已加载。Codex官方说明：启动时按全局与仓库到当前目录读取AGENTS，AGENTS.override可覆盖，存在总字节限制；修改后新的任务/会话应再次确认加载来源。参考[官方AGENTS说明](https://learn.chatgpt.com/docs/agent-configuration/agents-md)（2026-10-11核对）。本会话修改后的规则已主动重新读取，不假设旧上下文自动热更新。

其他AI工具未由当前会话确认使用，未创建CLAUDE/Cursor/Copilot规则副本。通用启动提示可用：“先读取根AGENTS.md，按本次任务范围定位现有实现/调用方；遵守完成标准，运行相关检查，简述复用、新增理由、旧代码处置、影响范围、验证与限制。”工具若不能读取文件，需手工提供AGENTS内容；若有原生规则导入功能只引用根文件，并在新会话要求列出加载来源，不假定所有AI会自动读取。

AI阅读负责复用/清理/文档/交付说明；程序负责上述依赖边界和既有行为/类型/构建回归；是否需要新架构、兼容退役、事实/岗位亮点与真实模型质量仍需用户及维护者判断。小改几句话即可，不强制长报告。

## 机制卡片整理后的简历链路（2026-10-11）

生产入口仍 main.artifacts → artifact_service → resume_writer.write → resume_quality.generate。原Wiki映射、全貌、JD调查/本地召回不变；DISCOVER先产候选，source_investigation以候选缺口补查固定SHA，CANDIDATE_ENRICH补既有卡片，CLAIM_VERIFY独立核验，SELECT记录采纳/舍弃，writing_pack只投递已选支持事实，WRITE加载原Skill，双审按分类修订，原确定性render导出。没有第二套业务流水线或新增Agent。

resume_contract保存可选机制事实/候选/审查分类契约；resume_quality承担预算、关联校验、保守归属上界和定向修订；resume_support继续复用唯一模型客户端/材料收集。新审计仍存既有Run/Artifact JSON，无DDL；旧反馈important_omission只兼容解析。前端ResumeHarness显示新分类，其他页面行为不变。

单主题真实回归复用scripts/eval-resume-quality.py的检查点模式，通过相同生产write入口运行后续阶段；前置模型结果明确标replayed，不能冒充新版全量发现质量。冻结输入指纹/提交/JD/模式必须与原样例一致，恢复检查点还检查主题与人工检索线索，累计付费最多8次并禁止同时跑旧基线。fixtures/resume-quality/boundary-review.json保存固定版本人工机制核对标准，不是自动自评或stub质量评分。






当前材料边界：复用PRODUCT→DISCOVER→候选补证→核验→SELECT→统一写作/独立评审（角色职责详见下方v5）。发现从整个用户闭环出发再关联JD。SELECT只收合格候选及支持事实，按project_reference/personal_resume传递明确政策。project_spine复用已核验上游事实，不投递未经核验产品摘要；允许简介引用完整项目事实，亮点/成果仍限定所选主题。该边界由check_draft和回归测试保护。语义选题正确性、机制完整性仍需真实固定仓库评测，不以离线测试宣称跨仓库质量通过。

MAPPING_INVENTORY为现有全块映射的本地逐页索引：记录事实数/机制/无映射状态，传入DISCOVER并保存审计；不是新增模型阶段，也不将页覆盖视作语义准确。

当前定向SOURCE补查：从已接受片段的显式相对import/from/require解析仓库内现存路径，单层最多2个依赖文件，共享原文件/字符/工具预算并记录dependency_hint；不是调用图证明。暂不处理路径别名、动态导入或跨语言全量调用图。JD以任务推进、上下文、状态和恢复等能力提问，技术评审逐项核查强术语，沿用原评审请求。

2026-10-12：DISCOVER_LINK_REPAIR改为ReferenceRepair补丁响应，仅返回有误引用字段/可选步骤删除，程序合并后完整校验；不再要求整份Discovery重写。预算与事实边界保持。

ReferencePatch仅兼容候选事实字段的claim_ids→refs同义表达，统一输出refs。保留原因是实际模型返回原卡片字段名；若补丁协议完全统一且真实回归证明不再出现该输出，才评估移除。冲突/证据目标/未知字段仍拒绝。


## 交互迭代 MVP（2026-10-12）

生产新增入口：Discussion → ProjectIteration（三标签）→ `/api/workspaces/{wid}/interaction/*` → interaction_service。interaction_contract 只包含输入/输出契约；操作服务复用 memory.save_target/save_contribution/invalidate，事实、贡献、方案和证据仍用原表。当前编辑指针、用户指标、待接受建议存 interaction_states JSON；审计用 MemoryEvent，正文用 Artifact。

聊天读取当前工作区/最近消息/项目报告/有限证据，使用现有 WritingModel + contribution_interview Skill 解析一次结构化响应，再经统一 mutation 校验和原子写入。讨论或澄清不写事实，非法操作整批回滚；聊天本身有记录和版本。模型没有数据库工具权限。报告中的版本、证据摘录覆盖限制会传入模型，不把未包含材料当成不存在；没有扩建源码分析系统。当前未做多轮自主工具补查。

状态锁使用工作区材料哈希+revision CAS，包含当前编辑版本；mutation_id 回执唯一索引防重复。长模型请求前提交读取事务，返回后核对版本。生成标识另绑定材料/编辑版本，避免中断后用同一标识取回旧缓存稿；编辑稿类型随审查和恢复保留。多操作、审计与回执同事务。单人本地部署，没有新增用户认证；隔离沿用 workspace_id，不能解释为多租户访问控制。

生成仍调用 artifact_service.create_artifact → resume_writer/resume_quality 全流程，收集增加用户指标/方案状态并计入材料指纹；个人稿无已确认贡献提前补问。生成完成先存待接受 proposal，冻结当前编辑指针；只有 decision 接受才保存新的正文版本。审查只读取提交的编辑器文本，返回问题分类和建议，不把编辑文本当项目事实；sync_candidates 必须另行明确确认，调用相同 mutation。人工保存/恢复后的事实关联均待复核，不声称旧逐句映射仍准确。已接受生成记录源 artifact_id，可查原证据审计。

前端保留本地未保存正文（按工作区 localStorage），服务器更新不覆盖本地；建议基稿与编辑器不同时不能直接接受。JD表单同样不覆盖未保存输入。表单显式字段和聊天操作落同一状态；来源表单为 source_message_id=null，聊天保存来源消息。采用/完成不自动创建个人贡献。

### 兼容路径

- 历史生成与证据工具折叠保留，供旧审计、验证报告、实验贡献和旧 API 使用；旧生成仍调用同一 artifact_service。编辑指针建立后，历史生成只增加历史记录，不替换当前正文。旧工具没有新交互版 expected_version，单独使用时注意按提示刷新；其材料改动会使交互请求指纹失效。移除条件：旧导出/测试与外部调用迁移，证据上传/已验证贡献录入的界面被等价承接。
- `/messages` 旧 LangGraph 贡献候选接口保留供历史客户端和其回归；新主界面不调用，也不会串联两次聊天模型。移除前需确认外部调用方。新讨论只新增受控操作协议，不创建第二个 Agent。
- `/improvements/{id}/select` 旧单选入口保留单选语义，但现在委托统一 mutation 同步 details.decision，防止新旧状态分裂。新信息面板允许多个并行事项。

### 迁移与验证

Alembic 001→002 为纯增量建表/部分唯一索引，不重写事实/旧正文，不需要预填交互状态。启动自动 upgrade；回退前应导出交互数据，downgrade 会删除新交互状态，不能作为无损撤销方法。隔离迁移回归从001写入旧项目/正文再升级002验证保留。

验证入口不变：`.venv/Scripts/python scripts/check.py --e2e`。定向 `.venv/Scripts/python -m pytest backend/tests/test_interaction.py -q`。Playwright 使用8001隔离数据库与测试专用模型返回；不使用当前8000服务。无额外依赖/锁文件。

### 一条可操作演示

1. 保存仓库链接并分析（或明确选择演示报告），打开讨论区；讨论具体改进的必要性。真实讨论需当前模型配置；离线 E2E 有明确模拟响应。
2. 当前信息中添加改进，采用后显示“已采用/未开始”；单独“报告已完成”显示用户报告、未核查源码。个人贡献另填本人职责和行动。
3. 添加“幻觉率下降/70/%/相对下降”；表单改80，或聊天明确更正。检查同一指标 v2、来源保留，正文只标待更新。
4. 修改当前 JD并保存，其他事实/指标/正文不变；下一次生成重新按当前目标选材。
5. 编辑器明确选“离线规则演示”生成项目参考建议，或真实模型生成；查看差异后接受。个人稿要求确认贡献且不能用规则演示冒充。
6. 修改正文保存，继续把“快照恢复”编辑为“任务级断点续跑”，分析当前文本；查看事实/归属类问题。接受/拒绝前正文保持；信息同步候选另行确认。
7. 刷新检查保存和未保存状态；恢复历史版会创建新版本。生成等待时编辑仍可操作，旧建议不能覆盖不同的本地正文。

### AI 判断固定样例及评审标准（待真实运行）

- 材料：角色有私有记忆/独立决策；提议合并Agent。应讨论统一执行器与合并上下文的区别、隔离风险、收益假设及验证方式，不预定推荐结论。
- 两个70%指标：更正指代不清应只澄清；希望达到80%不得更新；有唯一明确名称时改原ID，保留旧值。
- “另外加缓存”保留事项；“A暂缓改做B”产生两个独立决策；话题切换不沿用旧指代。
- 编辑器把快照恢复扩大为任务断点续跑：说明证据缺口/含义区别，保留用户文本，不能反向认定已实现。
- 评审看依据、取舍、澄清必要性、事实/归属一致性及操作正确性，不要求特定句子。测试fixture只验证预定响应的状态处理，不能替代上述真实模型判断验收。


## 用户页与过程后台（2026-10-12，替代交互区置于长报告底部的布局）

`architecture-entry.tsx` 仍为唯一前端入口，根URL呈现核心功能，`?view=admin` 呈现独立过程页。沿用现有服务端静态挂载，无路由依赖和后端接口变更。这是本地单用户的展示分区，不是新权限系统。

用户页固定导航控制项目输入/全貌/方向/交互区域；ProjectIteration接受受控tab，切换时保持组件挂载和本地草稿。Discussion用户模式仅渲染交互编辑功能；管理员模式承接原历史生成、证据、审查和兼容工具。ProcessPanel只负责展示既有Run/事实/事件记录。模型和更新服务不分叉。

原始Wiki、阶段输出、源码路径、评选/双审细节仅在过程页显示；用户仍看见原项目归属、未验证指标、输入变化及人工修改提示。需要技术排错使用右上“过程后台”；后台有“返回用户界面”。当前项目沿用原localStorage选择，无有效选择时取后端最新项目；没有项目时入口仍可见并说明创建步骤。

交互回归位于原Playwright入口；旧高级流程测试改从后台进入，业务断言保留。新增回归保证切换页面不丢编辑、空项目入口可见和窄屏导航可用。


## 角色职责与材料链 v5（2026-10-12）

主调用链不变：artifact_service → resume_writer.write → resume_quality.generate → resume_contract.render。交互编辑/版本接收仍走interaction_service，不复制生成入口。

- resume_index：无模型的原文范围索引、词面召回与已读/未读预算账本；复用SourceEvidence。每个来源ID绑定唯一原文范围，邻居各自保留ID。
- resume_prompts：四种TaskSpec白名单、独立上下文投影、固定版本模板和哈希；不能从用户材料加载路径或工具。模板缺失预检失败。resume_composition Skill只供WRITE，不负担角色路由。
- resume_revision：确定性候选演进历史、事实门禁与评分计算；无模型/数据库依赖。内容评分是辅助观察，不能代替事实门禁和人工复核。
- resume_quality仍编排原阶段；移除DRAFT_HR/DRAFT_TECHNICAL两次调用，SELECT为HR选材，CANDIDATE_ENRICH/增量发现为技术调查，WRITE统一写作，REVIEW_HR/TECHNICAL独立评审。
- SourceReader.search_ranges在固定SHA缓存内按问题词和控制流窗口取最多3段；记录未读命中，不执行代码、不宣称完整调用图。Python AST仍仅作本地静态定位。
- Harness阶段缓存使用完整prompt/schema、模型端点/模型名、输出预算配置、workspace/snapshot/SHA及契约版本。仅完整成功流程写入新缓存；角色实际输入不同，JD/证据/模板变化自然失效。缓存命中依旧执行取消检查及调用方契约检查，实际调用usage未知保持null。

历史write_legacy仍被显式评测入口引用，保留用途和原删除条件；历史双稿审计无需迁移，新生产不再生成双稿。没有新依赖、迁移或Agent框架。

评测准备（无模型）：`.venv/Scripts/python scripts/eval-resume-quality.py --prepare-only --checkpoint-input data/resume-mechanism-regression/input.json --checkpoint-before data/resume-mechanism-regression/before.json --theme cand_memory_version --benchmark fixtures/resume-quality/memory-review.json --output data/resume-role-regression/prepared-memory.json`。这些本地冻结文件不入Git；缺文件不能声称复现。真实验证另加--real和有界授权；--resume-checkpoint累计计费请求，--restart-downstream仅清旧响应，不重置累计额度。
