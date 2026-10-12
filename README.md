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

生产模型流程：全量有效 Wiki 分块映射 → 无 JD 项目全貌 → 最多 6 个岗位调查问题 → Wiki 召回 → 候选发现 → 问题驱动固定 SHA 补证/卡片补全 → 独立 claim 核验 → 1–4 个主题与职责覆盖 → 结构化 Draft → 独立 HR/技术审查 → 最多一次补证重选/修订 → 确定性 Markdown。实际加载 backend/skills/resume_composition/SKILL.md 与 references/writing-template.md。每段关联 claim，缺证据不凑能力；成果可省略。独立请求仍使用同源模型，不是招聘结论或人工认证。

默认最多 128 次映射请求（64 批、每批最多一次引用修复），后续请求预算默认 16、RESUME_GENERATION_CALLS 限定 8–20，包含结构修复及重选；最多两轮写作，首稿一次独立HR/技术双审，修订稿只做程序契约校验。API 报告用量达到 RESUME_MAX_REPORTED_TOKENS（默认 250000）后停止后续请求。UTF-8 字节估计不等于实际计費量，缺少 usage 表示未知。

模型客户端及材料契约集中在 backend/app/resume_support.py。凭证默认读取 data/deepwiki-open/.env 中 DEEPSEEK_API_KEY/DEEPSEEK_BASE_URL；用 RESUME_MODEL_ENV_FILE、RESUME_MODEL_API_KEY、RESUME_MODEL_BASE_URL 覆盖。写作模型由 **RESUME_MODEL** 指定，未指定默认 deepseek-v4-pro，不再继承 DEEPWIKI_MODEL。Wiki 映射缓存默认 REPOCAREER_DATA/resume-analysis-cache，由 RESUME_ANALYSIS_CACHE_DIR 覆盖；按工作区/快照/材料/模型端点/指令隔离，JD 与贡献每次新读。失败批次不缓存，不静默丢弃后续 Wiki。

POST /api/workspaces/{id}/artifacts 使用 writing_mode=model、独立 idempotency_key 和当前表单 target_role/target_jd。缺省 writing_mode=reference 保持旧 API 兼容。artifact_service 负责准入、冻结材料、短事务与保存；同一工作区产物串行，不同工作区独立。Run 取消在下一阶段生效，已发 HTTP 模型请求不能撤销，结束前仍占用准入。简历 Run 的通用 /retry 返回 409，须通过原产物请求重试；材料/目标变化需新幂等键。运行中更正导致指纹改变时拒绝保存旧稿。重启将未结束 Run 标记 interrupted，不自动重放付费请求。

历史 Markdown 草稿与旧审查记录保留预览/导出，不回填事实认证。resume_legacy.py 只用于明确的离线/历史评测比较，没有生产降级路径。

## 评测与项目记录

离线契约对比：`.venv/Scripts/python scripts/eval-resume-quality.py --compare-legacy --output data/resume-quality-offline.json`。真实模式追加 `--real --workspace <ID> --freeze-revision`，**会消耗 API 用量**，需要人工核对，不自动证明质量提升。已存稿人工对比：`.venv/Scripts/python scripts/compare-resumes.py --workspace <id> --baseline <id> --candidate <id> --output data/resume-comparison.md`。

当前范围见 docs/PRODUCT.md；恢复与验证见 docs/STATUS.md；决定沿革见 docs/DECISIONS.md；反馈任务见 docs/BACKLOG.md；本轮代码整理及兼容删除条件见 docs/code-review.md。旧分析/上传 API 尚未确认退役范围，继续保留。

单主题回归可复用原审计检查点：`scripts/eval-resume-quality.py --real --checkpoint-input <冻结材料.json> --checkpoint-before <原评测.json> --theme <候选ID> --paid-call-limit 8 --output <隔离输出.json>`。该命令会付费，需本次明确授权；输入指纹/产物模式必须匹配原报告。`--source-path`/`--source-question`记录人工补查线索；`--resume-checkpoint`仅重用已完成的补全/核验结果，累计最多8次，不能结合`--compare-legacy`另跑付费基线。原映射/候选被回放，不能把该评测说成新版全量发现验收。人工规则见`fixtures/resume-quality/boundary-review.json`，真实记录/失败原因见`docs/resume-quality-progress.md`。
