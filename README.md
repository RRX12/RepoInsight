# RepoInsight

输入公开 GitHub 仓库链接，生成中文项目全貌，围绕源码提问，并讨论优化方向。适合在本地学习和理解项目；岗位JD或关注点可选。

## 1. 安装与准备

当前启动脚本面向 **Windows PowerShell**。请先安装：

- Python **3.12**（已验证版本），确保 `python` 可用。
- Git、Node.js **22 LTS**、pnpm **11.25.0**，确保命令可用。可用 `npm install -g pnpm@11.25.0` 安装 pnpm。
- Ollama：以下配置用它在本地计算 embedding；文本生成使用 DeepSeek API。

```powershell
git clone https://github.com/RRX12/RepoInsight.git
cd RepoInsight
powershell -ExecutionPolicy Bypass -File scripts/start.ps1 -SetupOnly
```

首次执行会创建 `.venv`、按锁文件安装后端／前端依赖、构建网页，并在不存在时复制 `.env.example` 为 `.env`。已有配置不会被覆盖。依赖或前端代码更新后加 `-Install` 重新安装并构建：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start.ps1 -Install -SetupOnly
```

Python、Git、Node.js、pnpm、Ollama 需要自行安装；脚本不会安装系统软件。下面的 DeepWiki 服务也需要首次配置一次。

## 2. 安装项目分析服务

RepoInsight 通过本地 **DeepWiki-Open sidecar** 生成 Wiki 和处理项目问答，增强模式复用其任务服务并加入结构分块、源码检索和工具调用。目前增强生成链支持 **公开 GitHub 仓库＋DeepSeek**。

在仓库根目录执行（固定版本，勿直接换成上游最新分支）：

```powershell
git clone https://github.com/AsyncFuncAI/deepwiki-open.git data/deepwiki-open
git -C data/deepwiki-open checkout d92819a9c9f3b99416e3580ff235fc9d3adf8b89
git -C data/deepwiki-open apply ../../scripts/deepwiki-local.patch
python -m venv data/deepwiki-venv
data/deepwiki-venv/Scripts/python -m pip install -r scripts/deepwiki-requirements.lock.txt
.venv/Scripts/python scripts/configure-deepwiki.py --sidecar data/deepwiki-open
.venv/Scripts/python scripts/install-deepwiki-retrieval.py --sidecar data/deepwiki-open --wiki-rag
ollama pull nomic-embed-text
```

`configure-deepwiki.py` 只用于首次配置，已有 sidecar `.env` 时会拒绝覆盖。更新本仓库补丁后重新执行最后的 `install-deepwiki-retrieval.py` 命令并重启 sidecar；安装器会检查上游版本及未知修改，不会自动覆盖不兼容改动。

## 3. 配置模型

两份 `.env` 均在本地编辑，**不要提交 API Key**。

在根目录 `.env` 设置：

```dotenv
REPOINSIGHT_DEMO=false
DEEPWIKI_BASE_URL=http://127.0.0.1:8002
DEEPWIKI_PROVIDER=deepseek
DEEPWIKI_MODEL=你的DeepSeek模型ID
WIKI_RETRIEVAL_MODE=enhanced
WIKI_RAG_INDEX_MODE=auto
WIKI_RAG_AUTO_VECTOR_LIMIT=10000
PROJECT_MODEL=你的DeepSeek模型ID
```

在 `data/deepwiki-open/.env` 中保留初始化生成的配置，并添加：

```dotenv
DEEPSEEK_API_KEY=你的APIKey
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

模型 ID 必须是账户实际支持的名称，并支持工具调用。Wiki 使用 `DEEPWIKI_MODEL`；优化分析与讨论使用 `PROJECT_MODEL`，默认读取 sidecar 中的 DeepSeek Key 与地址。如需独立配置，在根目录设置 `PROJECT_MODEL_API_KEY` 和 `PROJECT_MODEL_BASE_URL`，无需重复配置同一密钥。

**Embedding 与文本模型是两种配置**：以上初始化使用本地 Ollama 的 `nomic-embed-text`，不是让 DeepSeek 生成向量。保持 Ollama 运行；首次索引较慢，后续复用缓存，仅计算缺失输入。切换 embedding 模型会产生新的索引身份。其他 embedding 服务配置见 sidecar 的 `api/config/embedder.json`，本 README 不假定不同服务参数通用。

可选：根目录 `GITHUB_TOKEN` 用于 GitHub API 访问额度；当前增强流程仍以公开仓库为范围。

预算由根目录 `WIKI_RAG_*` 控制，完整选项见 [.env.example](.env.example)。`auto` 模式最多生成 `WIKI_RAG_AUTO_VECTOR_LIMIT` 个缺失向量；这不是 token 数。`WIKI_RAG_INPUT`／`WIKI_RAG_OUTPUT` 分别控制章节输入估算与输出预算，模型自身上限仍有效。文本 API 可能收费；提高预算可能增加费用和等待时间。

### 可选：优化建议的外部资料调研

在根目录.env设置 `OPTIMIZATION_WEB_ENABLED=true`、`TAVILY_API_KEY=你的Key`。普通搜索可能按服务商额度收费，默认关闭；未配置时仍可基于源码生成受限规划，并标明未完成外部调研。搜索与已读正文各默认最多6次；缓存24小时，可用 `OPTIMIZATION_WEB_REFRESH=true` 强制刷新。优化规划默认2次主要模型调用，可选一次补查修订及一次格式修复；首次源码准备和Wiki另计，不是整个分析仅两次。全部参数见.env.example。

## 4. 启动

保持 Ollama 运行，然后在两个终端分别执行：

```powershell
# 终端一：Wiki 服务
powershell -ExecutionPolicy Bypass -File scripts/start-deepwiki.ps1
```

```powershell
# 终端二：RepoInsight（缺少应用依赖时自动安装）
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

打开 **http://127.0.0.1:8000/**。网页由后端提供，无需额外启动前端开发服务器。两个终端各按 `Ctrl+C` 停止对应服务。不要开启多个后端 worker。

修改 `.env` 后重启对应服务；修改网页后执行 `start.ps1 -Install` 重新构建。开发前端时可单独运行 `pnpm --dir frontend run dev`（5173 端口）。

## 5. 使用与功能

1. 保存 GitHub 仓库链接，再填写可选岗位JD／关注点并开始分析。
2. 在项目全貌左侧选择章节，阅读源码引用、技术说明和证据支持的 Mermaid 图示。
3. 使用可拖动、缩放和收起的聊天框讨论当前章节；在优化方向中比较问题、已有方案和改进取舍。

源码调查绑定固定提交 SHA，保留证据和未确认范围；建议是待实施方案，不代表已完成优化或实测收益。数据与聊天存储在本地 `data/`，请备份，不要公开其中的源码缓存、数据库或密钥。项目不再提供简历生成。

**重新分析**使用当前配置创建新任务；**安全重试**恢复原任务并复用已保存阶段，不会自动重写已生成 Wiki。切换预算或写作要求后，请选择“重新分析（生成最新版本）”。

## 常见问题

- **页面打不开**：检查终端二是否启动成功、8000 端口是否占用。前端更新后内容未变，重新构建并刷新页面。
- **Wiki／模型失败**：检查终端一的具体错误、API Key、模型 ID、Ollama 和网络。页面通用错误不一定表示服务商故障，也可能是输出校验失败；成功缓存保留。
- **提示缺失向量超出上限**：先确认仓库规模，再调整自动向量上限；已有缓存不会因此删除。
- **模型调整后无变化**：重启服务，并发起新分析。不同模型的上下文和工具调用兼容性需要实际验证。

## 开发与验证

```powershell
.venv/Scripts/python scripts/check.py --e2e
```

默认检查离线隔离运行，不调用真实付费模型；通过不等于真实内容质量已验证。当前增强生成仍在完善，可能遇到模型输出格式、引用和工具调用兼容问题。

更多细节：[架构与安装协议](docs/architecture.md) · [产品范围](docs/PRODUCT.md) · [当前状态与验证范围](docs/STATUS.md)。


优化建议的内容评测：`python scripts/evaluate-optimization-advisor.py` 默认仅输出5类离线评测场景和人工评价维度，不连接服务。真实对照必须显式传 `--allow-paid --workspace-id ID --snapshot-id ID --output data/advisor-eval.json`，可能产生模型／搜索／embedding费用；固定相同SHA、JD与约束，由人工核对准确性、方向覆盖、取舍、可执行性和成本。默认不发布分析记录或方向。
