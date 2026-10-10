# 真实烟测记录：未通过质量验收

2026-10-11；仓库qiukuizhenpiaoliang-dot/cp-dance，AI应用开发工程师JD。模型deepseek-v4-pro；固定源码SHA 21d9b9b43409d13bbcfefc2f26f7cbae2640c3b6；历史Wiki版本unknown。输入指纹d7d306dda9960256e34af419f0aa8501f59dbaba995f79699350da8cc46a071b。通过实际resume_writer.write，独立只读脚本；没有业务artifact写入或历史snapshot回填。

最后一次真实调用失败：resume_contract，事实/选题契约校验失败：岗位覆盖必须记录每项调查职责。Trace ID 059e7413044e0f434d3c508a。6个请求，API报告total_tokens合计115512（不含缓存Wiki mapping历史消耗）；模型请求时长合计105.2秒，不等于端到端耗时；价格未记录，不推算费用。

源码召回已从文档/界面移向agent/runtime/context核心路径，但character-memory部分仍遇到30000字符预算，未伪称已核验。核验模型仍将32个claim判不足/unknown，选题却选择无资格候选，修复输出空coverage；本轮拒绝生成正文。此前另一轮16请求完整流程结果needs_review，正文全部剔除，也不是可用简历。

已据失败修复有界结构/引用/资格纠正、输出截断检查、核心路径别名优先、文档/代码kind分开；最后增加程序补unknown覆盖及独立核验去除默认不足状态锚点。最终89项后端回归通过，后两项未再次真实复验。测试与真实效果分开，不能据此声称质量提升。

当前真实新旧同输入人工评分未执行；离线同输入示例见resume-quality-example.md，仅证明契约和控制流。下一步对小型核心机制包人工核对真实原文，分别评事实支持、岗位机制、归属、重复、可读性，再决定是否更换核验模型或调整窗口/召回。不要把同源双审当人工认证。

原始评测JSON保留在忽略提交的data/resume-quality-real-delivery.json；其他失败与完整待复核样例同目录。重跑命令见README，会实际消费API额度，不自动发布或评分。
