# 实施过程中的设计文档修正记录

## 1. 文档目的

本文单独记录 gm-science 在实机对照和具体实施过程中，对既有设计文档中假设、优先级或功能语义的修正。

现阶段不直接重写全部历史规划，避免丢失决策演化过程。后续统一整理文档时，应以本文记录和已通过测试的实现合同为依据，将有效结论合并回正式设计文档，并删除已失效的描述。

每条修正包含：

- 原有判断或假设；
- 新证据；
- 修正后的结论；
- 影响范围；
- 后续文档整理动作。

## 2. 修正记录

### DOC-CORRECTION-001：不新增 Artifact `Request review` 操作

**原有判断**

`claude-science-gap-and-next-phase-plan.md` 的 Phase 8C 后续项将“显式 `Request review` 指定 Artifact”列为待实现能力。Phase 10 结束时也曾将其作为下一优先级建议。

**新证据**

2026-07-18 对已登录 Claude Science 进行实机检查：

- Artifact 详情的操作菜单包含 Star、Hide、View in context、Provenance、Copy link、Rename、Download、Metadata/Cloud Export 和 Delete；
- 菜单中不存在 `Request review`；
- Session options 使用独立的 Auto-review 开关控制 Reviewer 行为。

**修正结论**

gm-science 不新增 Claude Science 中不存在的 Artifact `Request review` 按钮或独立评审状态模型。显式 Artifact 检查继续通过普通会话交互和现有 Reviewer 能力表达；自动评审继续由 Session Policy 的 Auto-review 控制。

**影响范围**

- Phase 8C 剩余工作清单；
- Artifact 操作菜单设计；
- Reviewer 调度和状态模型；
- Phase 11 实施优先级。

**后续整理动作**

正式整理 `claude-science-gap-and-next-phase-plan.md` 时，删除“显式 `Request review` UI/状态模型”待办，将相关内容改为 Auto-review 语义、Artifact inspection 和普通会话中的显式 Reviewer 请求。

### DOC-CORRECTION-002：Reviewer 不属于 Session Specialist 候选

**原有判断**

早期设计把 Paper Reader、Research Reviewer 和可配置 Specialist 视为可以通过同一 Session Specialist 候选列表直接选择的能力。

**新证据**

Claude Science 实机检查显示：

- Reviewer 在全局 Specialists 设置中作为内置能力存在；
- Session options 的 Reviewer model 和 Auto-review 是独立控制项；
- Session Specialist 子菜单不列出 Reviewer，只列出普通可选 Specialist 和创建入口。

**修正结论**

Reviewer 是评审策略能力，不是普通 Session Specialist 直接路由候选。gm-science 的 Session Specialist 候选应继续排除 `research_reviewer`；Reviewer model 和 Auto-review 保持独立。

**影响范围**

- Session Policy 候选投影；
- ADK root Agent 工具装配；
- Reviewer host-side gate；
- Specialists 设置页与 Composer 菜单的关系。

**后续整理动作**

正式整理专家调度章节时，将 Reviewer 从普通 Specialist 选择流程中拆出，并明确其配置入口、模型策略和 Auto-review 触发语义。

## 3. Phase 11 实施基线

Phase 11 按修正后的产品语义实施以下只读 Artifact 链路：

- Artifact 详情分屏和标签页；
- 有边界的本地文本预览；
- View in context；
- Provenance 查看；
- Project 所有权、路径和内容大小限制。

Phase 11 不实施 Star、Hide、Rename、Delete、Export，也不实施额外的 `Request review` 操作。

## 4. Phase 12 新增修正记录

### DOC-CORRECTION-003：长期 Memory 只管理 User 和 Project scope

**原有判断**

早期总体设计把 User、Project、Session 和 Artifact 都列为 Memory 分层，容易被理解为四套可管理长期记忆。

**新证据**

- ADK SessionService 已经是会话上下文事实源；
- gm-science Artifact、ResourceRef 和 provenance 已经是文件及科研结果事实源；
- 把 Session 或 Artifact 再写入长期 Memory 会复制状态、破坏删除语义，并增加跨 Project 泄漏风险；
- Claude Science 可见 Memory 页面管理的是长期 note，而不是 Session 或 Artifact 镜像。

**修正结论**

可管理长期 Memory 只提供 User 和 Project 两个 scope。Session 上下文继续由 ADK SessionService 管理，Artifact 上下文继续通过 ResourceRef 和 provenance 使用。模型如需把其中的稳定事实转成长时记忆，必须先提出可审阅候选。

**影响范围**

- Memory domain schema；
- Memory 设置页；
- worker scope 合并；
- 总体设计中的 Memory 分层描述。

### DOC-CORRECTION-004：产品 Memory 必须使用 gm-science ADK namespace 和数据根目录

**原有判断**

“复用 openppx Memory”曾被宽泛理解为可以沿用通用 Agent 的 `openppx` app name 和 Agent home 数据目录。

**新证据**

真实模型验收表明，gm-science root Agent 的 ADK app name 是 `gm_science`。如果 UI note 写入 `openppx` namespace，`PreloadMemoryTool` 永远无法召回；如果 worker 使用 Agent home 的 `memory.db`，而 UI 使用产品数据目录，两者也会形成不可见的双写。

**修正结论**

gm-science 所有批准 note、候选、召回和审计统一使用 `gm_science` app namespace，并统一位于 gm-science 产品数据根目录下的同一个 ADK `memory.db`。openppx 提供实现，不能改变产品 namespace 和存储所有权。

**影响范围**

- ADK Runner 和 `PreloadMemoryTool`；
- client-api worker；
- Memory 设置页；
- 重启恢复与跨 Session 验收。

### DOC-CORRECTION-005：领域 ID 的 URL 契约必须双向明确

**原有判断**

早期 client-api 路由默认把路径 segment 当作原始领域 ID 使用，没有明确客户端编码与服务端解码责任。

**新证据**

Memory note 和 candidate 使用 `fact:...`、`memory_candidate:...` 作为稳定 ID。Electron adapter 会按标准对路径 segment 执行 URL 编码；服务端不解码时会把 `%3A` 当成 ID 内容，导致真实 UI 更新、删除和审批失败。

**修正结论**

客户端对每个领域 ID segment 执行 URL 编码，client-api 在路由匹配前逐段解码。该约束适用于 Memory 以及后续所有含保留字符的稳定领域 ID。

**影响范围**

- Electron adapter；
- client-api handler；
- HTTP contract tests。

### DOC-CORRECTION-006：TaskRun 终态必须包含产品 Artifact 提升

**原有判断**

数据分析早期实现把底层 TaskRun 的 `completed` 直接视为产品层运行完成。

**新证据**

全量测试复现了一个时序窗口：第一次同步读取到 `running`，随后底层任务完成，最终响应返回 `completed`，但输出 Artifact 尚未注册。用户会短暂看到“运行完成但没有报告”的矛盾状态。

**修正结论**

ScienceExecutionService 对外发布 terminal status 前，必须先完成 source、log 和声明输出的 Artifact 提升。产品层的 `completed` 表示运行和产物注册均已完成，而不只是子进程退出码为零。

**影响范围**

- 本地 Python Run；
- Data Analysis；
- Files/Artifacts 刷新；
- TaskRun 终态测试。

## 5. 当前实施基线

Phase 12 结束后的有效基线：

- 长期 Memory 只管理 User 和 Project scope；
- 所有批准 note、候选、召回与审计共用 gm-science 产品数据根目录下的 ADK `memory.db`；
- 模型只能提出候选，不能绕过用户审批写入长期 Memory；
- 全局和 Session Memory 开关关闭时停止召回与候选生成，但不删除已有 note；
- Electron、client-api 和 worker 已通过真实新增、编辑、拒绝候选、跨 Session 召回与跨 Project 隔离验收；
- TaskRun 对外终态包含 Artifact 提升完成，不暴露“已完成但产物尚未注册”的中间窗口。
