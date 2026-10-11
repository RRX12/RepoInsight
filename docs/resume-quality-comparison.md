# CP Dance 简历质量差距追踪（2026-10-11）

对照来自用户提供范例，是待核验目标，不是源码金标准。只读固定评测input.json的14页Wiki；Wiki版本本身未知，固定评测SHA不使Wiki自动变为该版本源码证据。匹配仅定位线索，不证明机制完整或源码实现。没有调用模型。

## 五主题Wiki线索

### 多Agent编排
- Character Agent：wiki:0《项目简介》：ls>  # 项目简介  CP Dance（CP 跳动）是一个重视角色自主权与同意边界的像素角色社交模拟项目。每个角色拥有独立的 Character Agent、方向性关系状态和私有记忆，并在交互中始终保留回应、犹豫、拒绝、沉默或离开的权利。项目提供两种体验模式：**自然模式**（Natural mode）不预写剧情，由调度器根据当前世界状态唤醒角色；**导演模式**（Dire；wiki:4《Character Agent 运行时》：ang-dot/cp-dance/blob/main/worker/agent-config.ts) </details>  # Character Agent 运行时  ## 概述  Character Agent 运行时是 cp-dance 项目中负责角色智能体（Character Agent）执行、管理与编排的核心子系统。它定义了角色的能力接口、状态管理、运行时行为模式，
- Relationship Judge：wiki:0《项目简介》：色写台词、读取私有记忆或决定关系结果。两种模式共用相同的 Character Agent、Interaction Runtime、Relationship Judge、空间模型和版本化记忆边界。  Sources: [README.md:1-12](https://github.com/qiukuizhenpiaoliang-dot/cp-dance/blob/main/README
- 调度：wiki:0《项目简介》：交互中始终保留回应、犹豫、拒绝、沉默或离开的权利。项目提供两种体验模式：**自然模式**（Natural mode）不预写剧情，由调度器根据当前世界状态唤醒角色；**导演模式**（Director mode）允许安排公开场景和剧情节拍，但不能替角色写台词、读取私有记忆或决定关系结果。两种模式共用相同的 Character Agent、Interacti；wiki:4《Character Agent 运行时》：Agent）执行、管理与编排的核心子系统。它定义了角色的能力接口、状态管理、运行时行为模式，并通过统一的 AgentEngine 调度引擎将角色能力接入整体世界循环。该运行时同时支持交互式体验（`natural` 模式）和非交互式体验（`story` 模式），并提供了后台异步智能体运行支持。  Sources: [lib/agent-engine.ts
- 并行：wiki:12《部署与基础设施》：app-js` | ^0.0.7 | OpenAI 应用托管 SDK | | `concurrently` | ^9.1.0 | 并行运行多个开发服务器 | | `dotenv` | ^16.4.5 | 环境变量加载 | | `vite` | ^6.0.1 | 前端构建工具 |  Sources: [package.json:15-20](https:

### 版本化记忆
- 版本：wiki:0《项目简介》：用相同的 Character Agent、Interaction Runtime、Relationship Judge、空间模型和版本化记忆边界。  Sources: [README.md:1-12](https://github.com/qiukuizhenpiaoliang-dot/cp-dance/blob/main/README.md#L1-L；wiki:2《快速启动与环境配置》：项目使用 Vite 作为核心构建工具，而 Vite 的运行依赖 Node.js 环境。虽然源码中未明确指定具体的 Node.js 版本号，但根据项目所采用的技术栈（Vue 3、Vite 及 ES Module 构建方案），开发者应确保本机已安装 Node.js 及对应的 npm 或 pnpm 包管理器。Vite 作为现代构建工具，对 Node.js 版
- 记忆：wiki:0《项目简介》：动）是一个重视角色自主权与同意边界的像素角色社交模拟项目。每个角色拥有独立的 Character Agent、方向性关系状态和私有记忆，并在交互中始终保留回应、犹豫、拒绝、沉默或离开的权利。项目提供两种体验模式：**自然模式**（Natural mode）不预写剧情，由调度器根据当前世界状态唤醒角色；**导演模式**（Director mode）允许安；wiki:1《核心边界与自主权原则》：于整个互动系统的各个层面：关系引擎在计算亲密度时会将边界尊重度作为重要因子纳入；互动会话在执行动作前必须通过同意管理器的验证；角色记忆系统会记录每一次边界事件，形成角色的历史行为档案。核心边界与自主权原则与 [关系引擎](#关系引擎中的边界集成) 和 [互动会话](#互动会话中的边界执行) 等模块紧密关联。  Sources: [lib/relatio
- baseRevisionId：未找到字面匹配；不是不存在的结论
- 过期：未找到字面匹配；不是不存在的结论
- 所有权：wiki:0《项目简介》：立回应、边界裁决和安全回退；动画可用性不赋予行为权限或同意；模型只能提出记忆修订，Memory Runtime 在提交前校验证据、所有权和基础版本；玩家输入可以推动当下情境但不能强制产生关系结果。  Sources: [README.md:19-29](https://github.com/qiukuizhenpiaoliang-dot/cp-dance；wiki:8《存档持久化流程》：的数据污染数据库。  验证内容包括：存档类型是否在允许的枚举范围内、必填字段是否存在、数据格式是否符合预期结构、用户 ID 与存档所有权是否匹配。  Sources: [lib/save-validation.ts:1-55](https://github.com/qiukuizhenpiaoliang-dot/cp-dance/blob/main/li

### 长对话上下文
- 压缩：wiki:2《快速启动与环境配置》：5173`，支持热模块替换 | | `npm run build` | `vite build` | 执行生产环境构建，将源码编译压缩后输出到 `dist/` 目录 | | `npm run preview` | `vite preview` | 在本地预览生产构建产物，模拟生产环境下的静态资源服务 |  Sources: [package.json:；wiki:12《部署与基础设施》：ite.config.ts#L1-L10)  配置要点：  - **输出目录**：构建产物输出至 `dist/` 目录。 - **压缩器**：使用 `esbuild` 进行代码压缩，以获得较快的构建速度和更小的产物体积。 - **环境变量**：在配置加载阶段即通过 `dotenv.config()` 加载 `.env` 文件中的环境变量，使构建过程中可
- 摘要：wiki:0《项目简介》：ob/main/db/schema.ts#L88-L127)  ### 事件与剧情  事件系统包括世界事件表、公开剧情事件表和剧情摘要修订表。`cp_dance_world_events` 记录世界层面的通用事件；`cp_dance_story_public_events` 记录公开的剧情事件，其 `source` 字段约束为 `CHECK (sour
- 连续覆盖：未找到字面匹配；不是不存在的结论
- 待办：未找到字面匹配；不是不存在的结论
- 降级：wiki:1《核心边界与自主权原则》：-| | 硬边界 | 绝对红线，不可跨越 | 立即拒绝，触发边界事件 | 不可协商 | | 软边界 | 弹性限制 | 警告后拒绝或降级处理 | 可在高信任下协商 |  Sources: [lib/autonomy-boundary.ts:20-35](https://github.com/qiukuizhenpiaoliang-dot/cp-dance

### 检索增强
- Wikipedia：wiki:0《项目简介》：me-or-day}_{weather-or-clear}_{utc-timestamp}_{short-id}.png` 格式。Wikipedia、Wikidata 和 Moegirl 内容仅在用户主动选择研究后获取，且必须保留来源归属和 API 返回的许可证元数据。  Sources: [ASSETS.md:15-23](https://github.com/q
- Wikidata：wiki:0《项目简介》：_{weather-or-clear}_{utc-timestamp}_{short-id}.png` 格式。Wikipedia、Wikidata 和 Moegirl 内容仅在用户主动选择研究后获取，且必须保留来源归属和 API 返回的许可证元数据。  Sources: [ASSETS.md:15-23](https://github.com/qiukuizhen
- Moegirl：wiki:0《项目简介》：r-clear}_{utc-timestamp}_{short-id}.png` 格式。Wikipedia、Wikidata 和 Moegirl 内容仅在用户主动选择研究后获取，且必须保留来源归属和 API 返回的许可证元数据。  Sources: [ASSETS.md:15-23](https://github.com/qiukuizhenpiaoliang-
- 消歧：未找到字面匹配；不是不存在的结论
- 别名：未找到字面匹配；不是不存在的结论

### 运行可靠性
- 超时：wiki:3《系统架构总览》：运行在 Cloudflare Worker 环境中，作为外部大语言模型 API 的统一代理。它处理请求格式转换、API 密钥管理、超时控制和错误重试，将标准化的请求转发给实际的 AI 服务提供商，并将响应转换为系统内部可用的格式。  Sources: [worker/ai-api.ts](https://github.com/qiukuizhenpia
- 重试：wiki:3《系统架构总览》：udflare Worker 环境中，作为外部大语言模型 API 的统一代理。它处理请求格式转换、API 密钥管理、超时控制和错误重试，将标准化的请求转发给实际的 AI 服务提供商，并将响应转换为系统内部可用的格式。  Sources: [worker/ai-api.ts](https://github.com/qiukuizhenpiaoliang-
- 降级：wiki:1《核心边界与自主权原则》：-| | 硬边界 | 绝对红线，不可跨越 | 立即拒绝，触发边界事件 | 不可协商 | | 软边界 | 弹性限制 | 警告后拒绝或降级处理 | 可在高信任下协商 |  Sources: [lib/autonomy-boundary.ts:20-35](https://github.com/qiukuizhenpiaoliang-dot/cp-dance
- D1：wiki:0《项目简介》：ai-api.ts` | 服务端 Character Agent 权限边界 | | `worker/save-api.ts` | D1/R2 世界与角色持久化 | | `desktop/` | 可选的 Electron 透明桌面角色层 |  Sources: [README.zh-CN.md:47-55](https://github.com/qiuk；wiki:6《数据库结构与 Save API》： 数据库结构与 Save API 是 cp-dance 项目中负责持久化用户创作内容的子模块。该模块建立在 Cloudflare D1（SQLite）之上，通过 Drizzle ORM 定义数据表结构，并向外暴露一套 RESTful 接口用于保存「世界」（World）、「角色」（Character）以及「导演设置」（Director Setup）三类数
- R2：wiki:0《项目简介》：api.ts` | 服务端 Character Agent 权限边界 | | `worker/save-api.ts` | D1/R2 世界与角色持久化 | | `desktop/` | 可选的 Electron 透明桌面角色层 |  Sources: [README.zh-CN.md:47-55](https://github.com/qiukuiz
- 测试：wiki:11《AI 模型集成》：ctionsPanel.tsx` 是用户配置和管理 AI 模型连接的 UI 组件。该面板允许用户添加、删除、编辑模型提供商配置，并测试连接状态。  Sources: [app/ModelConnectionsPanel.tsx:1-60](https://github.com/qiukuizhenpiaoliang-dot/cp-dance/blob/；wiki:12《部署与基础设施》：rrently` 同时启动 Vite 开发服务器和 Cloudflare Worker 本地模拟环境（端口 4000，启用定时任务测试）。`build` 脚本先执行 oxlint 静态检查，再通过 Vite 构建生产资源。`worker:deploy` 将构建产物部署至 Cloudflare。  Sources: [package.json:7-8](

## 实际阶段丢失
最近失败Run 9f9be500a0c34b78bcd2fa75cc6d3542：18个映射批次全部命中缓存；PRODUCT输出5条产品断言；DISCOVER仅4条事实、3个候选（单智能体+Skill改造、角色自主决策与调度、隐私边界）。32条全unknown是更早4501e1a任务，不能混作本次结果。
本次核验仅claim-4为supported/implemented/upstream；SELECT以缺个人贡献为理由选空，而模式为project_reference；没有进入新写作。因此不能把V17当作当前流程成功输出进行文案A/B对比。
映射cache_hits表示复用，不证明映射内容准确。此次未重新生成或语义复核18个缓存映射；因此Wiki→映射层是否已经遗漏仍待逐条核查。

## 针对性改动
v4已独立项目简介主线/所选技术主题权限，明确参考稿与个人稿选题政策。本轮复用mapped facts按页建立mapping_inventory，记录无映射事实页面、页面机制与尾页；将清单送入DISCOVER，减少只关注README/用户提议。清单不代表理解完整，不新增模型请求。
128后端测试通过；新增尾页和wiki:1/wiki:11区分回归。离线测试不是内容质量评测。

## 下一轮有限验证
优先核对版本化记忆的来源与调用链，然后在授权范围内同输入运行当前生产入口。比较候选机制数量、证据支持、归属与选题、重复及可读性；不得用所提供范例补写源码缺失事实。若映射已遗漏，修改映射并局部失效缓存；若映射存在而发现遗漏，修发现阶段。当前未证明跨仓库质量通过。
