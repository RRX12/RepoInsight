# RepoCareer

当前首版流程：GitHub仓库链接 → 岗位名称与JD → DeepWiki-Open项目全貌 → 架构优化方向 → 对话讨论/更正 → 确认个人贡献 → 简历Markdown。

## 启动

已有依赖时在根目录运行：
```powershell
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```
打开 http://127.0.0.1:8000 。单后端进程同时提供构建好的前端。新安装：Python3.12+建.venv，pip install -r backend/requirements.lock.txt；frontend执行pnpm install --frozen-lockfile、pnpm run build。

## 配置真实DeepWiki-Open

此项目已实现服务适配器，不包含已运行的DeepWiki服务。另行部署 [DeepWiki-Open](https://github.com/AsyncFuncAI/deepwiki-open)，选择支持 /wiki/tasks、/api/wiki_cache、/ws/chat 的版本，按其README配置生成模型及embedding模型。

复制.env.example为.env，设置DEEPWIKI_BASE_URL（例如http://127.0.0.1:8002）、DEEPWIKI_PROVIDER、DEEPWIKI_MODEL，重启本项目。模型凭证配置在DeepWiki-Open服务中，不填入网页。

当前GitHub链接模式直接向DeepWiki-Open发送规范仓库URL，type=github、comprehensive=true；无需共享本地源码目录。DeepWiki服务自行获取仓库和索引。公开仓库链接必须为https://github.com/owner/repo；不执行项目代码。源码引用跳转GitHub，来自Wiki材料而非本应用独立读取，可能复用服务缓存，未固定提交。旧ZIP上传API保留兼容，只有旧上传分析需共享数据目录。

缺少服务时真实分析明确失败，保存的链接与JD保留。可在“分析服务与演示说明”显式勾选演示；示例与链接仓库/实际JD无关，不是真实模型输出。取消只停止本地等待，外部任务可能继续；重试可复用Wiki缓存。

真实报告后的对话使用DeepWiki检索聊天；演示报告的对话默认为标记的规则助手。旧OpenAI兼容对话适配器保留。用户确认分析更正后保存为材料并进入后续对话；个人贡献需复核状态与归属。已验证需测试报告、范围、来源和限制。简历只选已实现/已验证贡献，不将建议或上游功能写成个人成果；更正后旧稿待复核。

## 验证与恢复

```powershell
.venv/Scripts/python.exe -m pytest backend/tests -q
cd frontend
pnpm run build
pnpm run test:e2e
```
E2E使用独立data/e2e与8001/5173，不往用户工作区添加测试贡献。pytest使用临时数据库。当前DeepWiki接口离线模拟已验证；真实服务与模型质量未验证。项目记录见docs/PRODUCT.md、STATUS.md、DECISIONS.md、BACKLOG.md。旧搜索/实践API保留兼容，当前界面简化为上传入口。

## 本机DeepSeek配置
已配置DeepWiki生成provider=deepseek/model=deepseek-v4-pro，API https://api.deepseek.com；密钥只在data/deepwiki-open/.env。embedding使用本机Ollama nomic-embed-text:latest，CPU模式避开GPU崩溃。
启动DeepWiki：powershell -ExecutionPolicy Bypass -File scripts/start-deepwiki.ps1（8002）；主应用scripts/start.ps1（8000）。修改密钥后重启DeepWiki。依赖冻结在scripts/deepwiki-requirements.lock.txt；上游源码固定d92819a9c9f3b99416e3580ff235fc9d3adf8b89，恢复时git apply scripts/deepwiki-local.patch（在源码目录使用对应绝对路径），包含DeepSeek客户端映射、Ollama options修复与模型配置；补回服务端.env，禁止提交密钥。scripts/configure-deepwiki.py仅用于本地Ollama/embedding配置，不会写入DeepSeek密钥。

## 云端Embedding当前配置
生成仍为DeepSeek deepseek-v4-pro；embedding已切换用户指定qwen3.7-text-embedding-flash，1024维、每批20条，官方北京兼容地址https://dashscope.aliyuncs.com/compatible-mode/v1。凭证仅在DeepWiki .env的QWEN_EMBEDDING_API_KEY；DEEPWIKI_EMBEDDER_TYPE=openai表示协议适配，不代表向OpenAI发送数据。配置在api/config/embedder.json，初始化独立密钥及base_url。
真实接口HTTP200，DeepWiki Embedder返回2个1024维向量/error=None。索引缓存按模型、维度、端点生成独立目录，不混用旧Ollama缓存。start-deepwiki.ps1已移除强制ollama的环境变量，由.env决定。恢复时应用更新的scripts/deepwiki-local.patch；不要运行本地Ollama初始化脚本覆盖云配置。

## 简历模型写作与有限审查
页面默认“模型按Skill写作与审查”，使用已保存DeepWiki内容、岗位JD和确认的用户材料。实际加载backend/skills/resume_composition/SKILL.md及references/writing-template.md，直接调用现有DeepSeek模型，正文Markdown，审查JSON，最多两轮（初稿和一次修订，生成部分最多八请求（产品全貌、岗位选题、写作与独立双评审），首次Wiki分析另计最多64批）。未通过保存待复核；API失败不冒充规则稿。可明确选择“规则参考稿”用于不调用模型的预览/演示。
写作凭证默认读取忽略提交的data/deepwiki-open/.env中的DEEPSEEK_API_KEY/DEEPSEEK_BASE_URL，模型默认DEEPWIKI_MODEL。可用RESUME_MODEL_ENV_FILE、RESUME_MODEL_API_KEY、RESUME_MODEL_BASE_URL、RESUME_MODEL覆盖；不要提交真实密钥。写作直接调用云API，不要求已保存Wiki重新索引。API POST /api/workspaces/{id}/artifacts传type=resume、writing_mode=model、独立idempotency_key；旧API不传writing_mode仍生成reference以保持兼容。
写作过程不持有长SQLite事务；材料变化返回409，不保存旧材料稿。审查日志、Skill与材料哈希在Artifact.claims的writing_review中，source_ledger_not_generated_text记录为源材料账本，不是逐句事实认证。使用前仍须核对个人经历与数据。研究模板来源见writing-template.md。

### 大项目简历分析 Harness
先对全部有效Wiki分块分析，证据使用预编号短段，原文由程序填入。分块缓存默认在data/resume-analysis-cache，可RESUME_ANALYSIS_CACHE_DIR覆盖；按工作区/快照/材料/模型端点/提示版本隔离。缓存只保留Wiki分析，JD与个人更正每次新读。预算不足明确失败，缓存可复用，不丢弃末尾。API报告usage原样存入审计；字节数只是保守Token上界，不是实际计费值；RESUME_MAX_REPORTED_TOKENS默认250000，达到后停止后续请求。无服务返回usage时不宣称费用或零用量。
独立PRODUCT请求先形成无JD项目全貌，SELECT再结合JD选材；HR/技术两次请求独立审查，最多一次修订。初次分析较慢，请勿重复点击并行提交。同步等待/断线恢复仍是已知限制。
人工对比：`.venv/Scripts/python scripts/compare-resumes.py --workspace <id> --baseline <id> --candidate <id> --output data/resume-comparison.md`。材料指纹不一致时仅描述比较；不得用模型通过率充当质量提升。

每个分析批次引用无效仅修复一次；失败不缓存，已完成批次可复用。调用元数据在缓存目录attempts中，不记录Prompt或密钥。事实映射保留逐字证据，注意不要公开data目录。

D018简历链路：项目全貌（闭环/架构/机制链）→JD中性问题规划→本地候选补证→按链路合并选题并产出大纲→写作与独立双评审。下游最多9次请求；仅Wiki映射缓存，JD变更仍会重做规划和写作。候选召回不是事实认证；来源字段与状态失败会拒绝生成，缺失证据标待确认。
