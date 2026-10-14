# RepoInsight

中文本地项目理解与优化讨论工具：公开 GitHub 链接 → DeepWiki 项目全貌 → 项目问答与优化方向。简历生成功能已移除。

## 使用

1. 先保存仓库链接，再填写可选岗位JD；选择“分析项目全貌与优化方向”或“跳过”。顶部“修改岗位JD”可随时编辑保存，保存不自动分析。
2. 项目全貌左侧选择章节，右侧阅读内容；浮动聊天框自动关联当前章节。
3. 优化大方向查看建议，点击“讨论此方向”比较问题、方案和取舍；可手动保存、编辑自己的方向。

聊天框可拖动、放大缩小、右下角调整尺寸和收起。问答与优化讨论分别持久保存到本地，刷新恢复，讨论不会自动修改方向或标记实现。旧简历数据仍保留，不提供生成或编辑。

## 启动与检查

后端：`.venv/Scripts/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`（单进程）。前端：`pnpm --dir frontend run dev`。本地页面 http://127.0.0.1:8000/ 使用 frontend/dist，开发页为5173。

依赖使用 backend/requirements.lock.txt 与 frontend/pnpm-lock.yaml，pnpm 版本见 frontend/package.json。配置参照 .env.example；Wiki/问答由 DEEPWIKI_* 配置，共享项目调查优先 PROJECT_MODEL_*，可复用现有 DeepSeek 服务 .env。新代码向量预算默认0，仅复用；真实模型调用可能收费，离线检查不调用真实服务。

完整离线检查：`.venv/Scripts/python scripts/check.py --e2e`。当前产品、架构、恢复和验证见 docs/PRODUCT.md、docs/architecture.md、docs/STATUS.md；讨论存储和预算见 docs/memory/README.md。

新项目仓库：[RRX12/RepoInsight](https://github.com/RRX12/RepoInsight)。本地目录名为RepoInsight。配置优先REPOINSIGHT_DATA/DEMO/API_TARGET，原REPOCAREER字段兼容现有环境；浏览器旧项目选择自动恢复。新数据库使用repoinsight.db，旧文件可继续读取。

## 首次安装（Windows）

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements.lock.txt
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend run build
.venv/Scripts/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

复制.env.example为本地.env并配置DeepWiki服务后才可运行真实分析。Sidecar安装与只读源码扩展步骤见docs/architecture.md；默认检查离线，不包含真实模型内容质量验收。
