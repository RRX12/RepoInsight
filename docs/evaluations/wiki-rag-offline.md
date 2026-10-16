# Wiki RAG 离线评估（2026-10-15）

执行输入见 `fixtures/wiki-rag/cases.json`，逐案例指标与快照 SHA 见同目录 `wiki-rag-offline.json`。12 个案例的核心问题、必要材料组、替代来源和禁止关系由人工定义；长函数由明确的重复语句展开。样本是独立的案例子树视图，链接身份使用测试仓库，不能当成真实公开仓库引用。

对照 A 运行原生产 `_generate_page → research_chat → RAG → FAISS`；预置相同源码的原生 LineTrackingTextSplitter 文档，外部 embedding 使用确定性词语哈希向量，写作响应使用脚本桩。额外限制旧链检索正文为8000 UTF-8字节以比较上下文；不测旧分支缓存、下载或索引创建。B 使用真实 Chapter 计划／结构检索／扩展，只进行初查审查；C 增加最多两轮补查。各组使用同一固定快照、相同向量方法及12000总／8000初查证据预算。B/C每章最多6次模型请求，A保留旧链一次写作职责。离线模型按手工证据组判定覆盖，不能据此证明真实模型会正确审查。

| 案例 | A材料组覆盖 | B材料组覆盖 | C材料组覆盖 | C停止 |
|---|---:|---:|---:|---|
| 单文件 | 100% | 100% | 100% | sufficient |
| 跨文件 | 100% | 50% | 100% | sufficient |
| 混乱README | 100% | 50% | 100% | sufficient |
| 错误候选路径 | 100% | 100% | 100% | sufficient |
| 同名符号 | 100% | 50% | 100% | sufficient |
| 配置分支 | 100% | 50% | 100% | sufficient |
| 尚未接线 | 100% | 50% | 100% | sufficient |
| 长函数 | 100% | 50% | 100% | sufficient |
| 无答案 | 50% | 50% | 50% | no_progress |
| TS类与TSX | 100% | 66.67% | 100% | sufficient |
| 文档替代来源 | 100% | 100% | 100% | sufficient |
| Unicode与fallback | 100% | 50% | 100% | sufficient |

C没有相对A的覆盖提升；样本大多很小，旧流程能一次检索所有相关文件。B的初查覆盖下降是显式缩小首轮材料的结果，C通过已声明缺口恢复所需材料；无答案保持未确认，不声称全仓不存在。不要把C相对B的补读效果解释为相对旧产品的文章质量提升。

JSON另记录每组无关上下文比例（按人工必要来源文件分类的粗粒度代理）、重复UTF-8字节比例、来源还原错误、链接路径／行号错误、禁止关系字面匹配、模型／工具／embedding输入次数、补查新增材料组与实测耗时。未知服务Token为null。B/C源码还原、版本、越界链接与禁止字面关系门槛通过；A的错误候选路径会由原后处理自动列成来源，报告保留该既有错误。字面关系检查不能识别任意隐含错误关系，仍需人工审阅。

复现（只修改临时克隆与显式输出文件，不启动服务）：

```powershell
data/deepwiki-venv/Scripts/python scripts/evaluate-wiki-rag.py --sidecar data/deepwiki-open --output data/wiki-rag-evaluation.json
```

真实内容评估单独命令，**本次没有执行**：

```powershell
data/deepwiki-venv/Scripts/python scripts/evaluate-wiki-rag.py --sidecar data/deepwiki-open --real --authorize-paid --max-model-calls 150 --model deepseek-chat --output data/wiki-rag-real.json
```

需环境显式提供DEEPSEEK_API_KEY及可选DEEPSEEK_BASE_URL；不自动加载生产.env。命令计入修复／旧链fallback，封顶总模型派发数；每次输出限制4000，SDK重试关闭，输入超限显式失败。输出逐组正文 `.pages.json` 与指标，问题回答、错误关系和可用性由人工核对，服务usage未返回不能估成零。真实命令仍使用相同受控离线向量，以单独比较模型内容；真实embedding召回质量、真实仓库复杂度与端到端成本尚未验证。默认legacy不能仅凭这份离线结果切换。
