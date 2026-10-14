# RepoCareer

中文本地单用户 MVP：GitHub 仓库链接 → 岗位名称/JD → DeepWiki-Open 项目全貌与架构建议 → 讨论、更正和确认贡献 → 项目简历参考稿或个人简历。

## 启动与验证

已有依赖时运行 `powershell -ExecutionPolicy Bypass -File scripts/start.ps1`，打开 http://127.0.0.1:8000 。该脚本启动单个后端进程并提供 frontend/dist。开发时根目录运行 `.venv/Scripts/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`，frontend 中运行 `pnpm run dev`。

新安装：Python 3.12+ 创建 .venv，安装 backend/requirements.lock.txt；frontend 执行 `pnpm install --frozen-lockfile`、`pnpm run build`。

```powershell
.venv/Scripts/python scripts/check.py --e2e
```

该入口与GitHub CI复用架构检查、pytest、前端类型/隔离构建及可选离线E2E；不带--e2e运行核心检查。安装用backend/requirements.lock.txt、frontend/pnpm-lock.yaml和packageManager指定pnpm，缺工具或失败返回非零，不替换生产dist。开发规则统一见[AGENTS.md](AGENTS.md)，模块定位、兼容用途、CI和AI加载说明见[architecture](docs/architecture.md)。

pytest 使用临时数据库与源码请求 mock。Playwright 使用8001/5173与tests/fixture_app.py；统一入口传入临时数据目录，单独执行E2E使用独立data/e2e；GitHub 版本解析固定为离线 fixture，演示流程不调用真实模型。单测/mock/构建通过不证明真实模型文案质量。scripts/ui-smoke.mjs 是现行页面的只读截图检查；scripts/demo.py 会写数据，只能用于自行准备的隔离演示环境。

## DeepWiki-Open

另外部署 [DeepWiki-Open](https://github.com/AsyncFuncAI/deepwiki-open)，使用支持 /wiki/tasks、/api/wiki_cache、/ws/chat 的版本。复制 .env.example 为 .env，配置 DEEPWIKI_BASE_URL、DEEPWIKI_PROVIDER、DEEPWIKI_MODEL；生成与 embedding 凭证留在 sidecar，不填入网页、不提交 Git。

公开链接必须为 https://github.com/owner/repo。应用发送规范 URL，DeepWiki 获取、索引仓库并生成全面 Wiki；当前界面无需打包源码或共享本地目录。新快照尝试解析固定 SHA，简历 SourceReader 只读对应源码；DeepWiki 的 Wiki 版本可能未知，不能把它追认为该 SHA。任何导入源码都不执行。旧 ZIP API 保留兼容，只有旧本地分析模式需要共享目录。

缺少服务明确失败，链接/JD 保留；不会回退旧 AST 模板。演示选项展示固定示例，不代表链接仓库或真实 JD。架构分析取消仅停止本地等待，外部任务可能继续，重试可复用 Wiki。

本机 sidecar 启动命令为 `powershell -ExecutionPolicy Bypass -File scripts/start-deepwiki.ps1`（8002）。上游固定版本及恢复补丁见 scripts/deepwiki-requirements.lock.txt、scripts/deepwiki-local.patch；应用补丁后自行恢复忽略提交的服务端 .env。生成和 embedding 可分别配置云服务或 Ollama；实际配置以本机文件为准，历史测试记录见 docs/STATUS.md 后文。scripts/configure-deepwiki.py **仅初始化没有 .env 的本地 Ollama sidecar**，已有配置立即拒绝，不能用于切换或恢复已配置的云服务。

## 简历生成

两种产物：project_reference 以完整上游项目为主体，不代表用户原创；personal_resume 围绕当前确认的个人贡献。讨论、尝试、实现、验证与支持程度分开；计划和待补问题放在模型正文外，用户数字保留来源及验证状态。显式规则参考稿仍供离线/演示使用，不冒充模型输出。贡献或项目事实更正保留历史，并使相关旧草稿待复核。

生产模型流程（v6）：固定版本概况 → JD深化 → 原始代码检索与有界补读 → 架构主题及独立事实核验 → 共享分析包 → 贡献核验/全局选题 → 写作 → 独立 HR/技术双审 → 最多一次修订及复审。优化方向消费同一分析包，独立判断必要性，不再把大段Wiki拼入聊天。Wiki学习和问答保留；简历无需已有Wiki正文，必须有合法固定版本和可用索引。

默认总预算20次（RESUME_GENERATION_CALLS 8–24），优化12次；每请求结构/引用修复最多一次。原始检索最多12+4条查询，补读共享一轮、32工具调用、12文件（上限16）、30000字符。实际加载写作Skill。事实、个人归属和实测指标分别校验；评分绑定具体草稿哈希，不证明人工质量。

写作模型配置仍为 RESUME_MODEL/RESUME_MODEL_API_KEY/RESUME_MODEL_BASE_URL，默认读取本地DeepSeek配置；与Wiki生成模型独立。共享缓存位于RESUME_ANALYSIS_CACHE_DIR（默认数据目录/resume-analysis-cache），含源码，禁止公开。索引身份包含SHA、embedding配置、维度、分块及文件哈希；新JD重新调查但复用向量，个人编辑不重做纯源码分析。代码embedding与查询embedding分开记录，缺失usage为未知。

新检索接口需要安装受版本控制的sidecar扩展，详见[部署和检索验证](docs/architecture.md#原始检索扩展安装)。安装脚本不启动服务。CODE_INDEX_NEW_VECTOR_BUDGET默认0，只复用已有向量；新文件或模型变化需明确设置预算，不能把未配置的扩展当已部署。

POST /api/workspaces/{id}/artifacts 使用 writing_mode=model、独立 idempotency_key 和当前表单 target_role/target_jd。缺省 writing_mode=reference 保持旧 API 兼容。artifact_service 负责准入、冻结材料、短事务与保存；同一工作区产物串行，不同工作区独立。Run 取消在下一阶段生效，已发 HTTP 模型请求不能撤销，结束前仍占用准入。简历 Run 的通用 /retry 返回 409，须通过原产物请求重试；材料/目标变化需新幂等键。运行中更正导致指纹改变时拒绝保存旧稿。重启将未结束 Run 标记 interrupted，不自动重放付费请求。

历史 Markdown 草稿与旧审查记录保留预览/导出，不回填事实认证。旧legacy、Wiki映射及词面索引执行代码已删除；历史产物仍只读显示，不运行旧模型链路。

## 评测与项目记录

离线生产入口验证：`.venv/Scripts/python scripts/eval-resume-quality.py --output data/resume-quality-offline.json`。使用固定SHA/JD与合成小源码、假embedding和预定模型响应，仅验证控制流。真实模型命令（另行授权后）：`.venv/Scripts/python scripts/eval-resume-quality.py --real --authorize-paid --input <冻结材料.json> --paid-call-limit 8 --output <隔离输出.json>`；也可用 `--workspace <ID>` 只读收集当前材料。8次可能不足补读/修订，失败仍保存阶段诊断，不自动加预算。输出只写隔离评测文件，不创建生产Artifact。

同输入比较用 `--before <已保存评测.json>`，强制核对输入指纹；旧输出只读，不重跑旧链路。人工需核对机制发现、事实支持、选题、贡献、重复和可读性。现有产物比较仍可使用 `scripts/compare-resumes.py`。历史单主题检查点回放与 `--compare-legacy` 已退出，不把旧候选回放当新调查结果。

当前范围见 docs/PRODUCT.md；恢复与验证见 docs/STATUS.md；决定沿革见 docs/DECISIONS.md；反馈任务见 docs/BACKLOG.md；旧代码处置见 docs/code-review.md。旧上传、讨论、规则参考等明确兼容能力继续保留。


项目问答支持本地会话恢复、讨论约束/笔记及按需历史检索；不自动修改贡献或简历。使用方式、预算、删除、迁移和验证范围见 [讨论记忆说明](docs/memory/README.md)。
