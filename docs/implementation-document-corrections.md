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

## 6. Phase 13 新增修正记录

### DOC-CORRECTION-007：Permissions 是产品注册表授权，不是本机沙箱

**原有判断**

早期规划把 registry writes、本机目录附加、credential use 和远程 Compute 混在同一个 Permissions 阶段，容易让设置页开关被理解为操作系统级隔离。

**新证据**

Claude Science 可见 Permissions 条目主要是 Create/Update Agent、Publish/Edit/Attach/Detach Skill 和 Attach/Detach Connector；gm-science 当前也没有进程沙箱作为这些开关的执行底座。

**修正结论**

第一版 Permissions 只授权持久化 registry mutation，并在 backend mutation boundary 强制。它不限制本机文件、shell、任意 Python 进程或操作系统权限。后续沙箱治理必须使用独立、可验证的执行边界，不能复用 UI 文案冒充。

### DOC-CORRECTION-008：Compute 的 configured、reachable、executable 必须分离

**原有判断**

“支持 SSH、Modal 或 model endpoint”容易被简化为保存配置后即可作为 Session Compute Target 执行。

**新证据**

远程目标可能只有凭据、端口可达或健康端点，但仍缺少 TaskRun executor、取消、重试、日志和 Artifact 回收适配器。

**修正结论**

Compute Target 必须分别报告配置完整性、连通性和可执行性。Phase 13 只有 Local 可执行；SSH、Modal、NVIDIA BioNeMo NIM 和自定义 model endpoint 即使已配置或可达，也不能出现在 Session 的可执行候选中。

### DOC-CORRECTION-009：Network 第一版只强制受管产品边界

**原有判断**

统一 Network allowlist 容易被理解为可以阻止本机所有子进程访问未授权域名。

**新证据**

当前可稳定控制的是 gm-science 原生 HTTP connector、远程 MCP 装配、显式 Compute 健康检查和 TaskRun package/CA 环境。任意用户 Python 代码仍运行在本机普通进程中。

**修正结论**

第一版 Network 对受管 HTTP/MCP 路径执行策略，并明确失败关闭和私网规则；它不是进程级网络隔离。完整子进程网络强制随未来沙箱阶段实现。

### DOC-CORRECTION-010：基础设施 URL 不是凭据传输通道

**原有判断**

Network mirror 和自定义 model endpoint 只要是合法 HTTP(S) URL 就可以原样保存并投影到设置页。

**新证据**

URL 可能包含 `user:password@host`、query token 或 fragment。原样投影会把凭据带回 renderer、截图和诊断；把它写入 TaskRun 环境也会扩大泄露面。

**修正结论**

所有基础设施 URL 在保存、公共投影和 mock 路径中统一删除用户名、密码、query 和 fragment。Model endpoint 的 API Key 只能通过 write-only secret mutation 写入；私有 package mirror 的 URL 凭据当前不受支持，不能把 token 嵌入 URL 作为替代方案。

## 7. Phase 13 后的有效实施基线

- 八类 registry write 使用全局 durable grants，并由后端 mutation service 检查；
- Network 策略统一投影到原生科研 HTTP、远程 MCP 和 worker 环境；
- Local 是唯一真实 Compute executor，远程 target 只提供脱敏配置和健康状态；
- package mirror 和 model endpoint URL 不承载凭据，公共投影不会返回用户信息、query 或 fragment；
- 任何界面都不得把凭据存在、端口可达或 endpoint HTTP 响应解释为远程 TaskRun 可执行。

## 8. Phase 14 新增修正记录

### DOC-CORRECTION-011：Storage 第一版是有边界的本地可观测性，不是迁移或云存储管理

**原有判断**

早期规划把数据目录展示、磁盘分类、修改数据目录和云存储连接放在同一个 Storage 阶段，容易为了对齐界面而提前暴露没有事务保障的操作。

**新证据**

gm-science 的 launcher 已经统一控制产品数据根目录，但安全迁移还需要停写、原子复制、完整性校验、重启和失败回滚；当前也没有云 bucket adapter。直接提供 `Change location` 或 `Connect cloud storage` 只会形成不可兑现的产品承诺。

**修正结论**

Phase 14 Storage 只提供只读本地观测：真实数据根目录、可写状态、文件数量、总占用、非重叠分类和扫描诊断。扫描有条目数与时间预算，不跟随符号链接；达到边界或遇到不可读条目时返回 partial 状态，而不是长期阻塞或静默漏算。数据根目录迁移与云存储必须在拥有独立后端事务契约后再进入界面。

### DOC-CORRECTION-012：Usage 是本地记录的事实汇总，不是官方账单

**原有判断**

Claude Science 的 Usage 页面包含 plan 和 token 消耗信息，容易被解释为 gm-science 也应展示费用、账户额度或 provider 账单。

**新证据**

openppx 已持久化每次模型调用的 token 事件，并以 TaskRun 保存受管执行状态和时间；但当前没有 provider invoice、价格版本账本或账户 plan API。模型返回的 token 字段也可能因 provider 能力而不完整。

**修正结论**

Phase 14 Usage 只汇总本地记录的 24 小时、7 天和 30 天窗口：请求数、输入/输出/总 token、provider/model 分布，以及 TaskRun 数量、状态和窗口内运行时间。界面固定标注 `Local estimate` 和 `Cost unavailable`，不得将缺失记录转换成官方零费用，也不得声称代表 provider 账单或账户限额。

## 9. Phase 14 后的有效实施基线

- Storage 与 Usage 通过 client-api、Electron IPC/preload 和 typed adapter 使用同一后端事实源；
- 磁盘分类为 Workspaces、Databases、Cache、Agent configuration、Logs 和 Other，分类不重叠且扫描不跟随符号链接；
- token 事实继续来自 openppx token store，运行事实继续来自 TaskRun，不建立 gm-science 第二套 usage 数据库；
- 数据目录迁移、云存储、费用核算和 plan 限额仍是明确未实现能力，界面不提供伪操作；
- General 只展示 runtime 能实际执行的 provider/model 与诊断设置，不复制无法落地的 Claude Science 候选项。

## 10. Phase 15A 新增修正记录

### DOC-CORRECTION-013：Capability 创建必须写入既有 registry，且不等于 Project attachment

**原有判断**

早期路线把“安装、创建、发现和附加 Capability”统称为动态能力管理，容易让创建动作同时修改全局 registry 和当前 Project，或者引入一套 renderer-owned 能力数据库。

**新证据**

openppx 已经分别拥有 Agent-local Skill 目录、`tools.mcpServers` 和 `science.specialists.custom` 三个运行时事实源；Project 只保存稳定 Capability ID attachment。真实 Claude Science 表单也把全局能力创建和 Project 启用作为不同操作。

**修正结论**

手动创建 Skill、MCP Connector 和 Specialist 直接写入 openppx 既有 registry，并在刷新后进入统一 catalog。创建成功不自动附加到当前或其他 Project；attachment 继续通过现有 Project mutation 和权限检查显式完成。不得建立第二套 Capability 持久化或把 renderer 状态当作事实源。

### DOC-CORRECTION-014：自定义 MCP 创建表单不是秘密值传输通道

**原有判断**

因为 openppx MCP 配置能够表达 environment 和 headers，创建表单似乎也可以直接接受这些字段。

**新证据**

当前 Credentials 服务尚未提供由 MCP assembly 消费的 write-only credential reference。直接从 renderer 接收 environment、header、URL query 或命令参数中的 token，会让秘密进入请求状态、日志、配置投影或截图。

**修正结论**

Phase 15A 只创建匿名 Remote URL 和无 shell 的本地 argv Connector，并拒绝 URL credentials、query、fragment 和 inline secret。需要鉴权的 MCP 必须等待独立的 write-only credential reference 契约，不能用隐藏输入框或文档约定代替后端秘密边界。

## 11. Phase 15A 后的有效实施基线

- Skill 创建写入 Agent-local `skills/<id>/SKILL.md`，MCP Connector 和 Specialist 分别写入现有配置 registry；
- `publish_skill` 和 `create_agent` 在后端 authoring boundary 强制，冲突、权限和无效输入使用稳定 HTTP 语义；
- 新建 Capability 默认不附加 Project，Specialist 只保存用户明确选择的 Skill 和 Connector；
- 一键启动器使用受管进程组，Electron 在退出和终止信号下幂等释放 adapter，`Ctrl+C` 不再遗留 client-api；
- ToolUniverse 不属于当前 Claude Science 复现路线，只有收到用户明确指令后才允许重新评估。

## 12. Phase 15B 新增修正记录

### DOC-CORRECTION-015：鉴权 MCP 使用 write-only Credential 引用

**原有判断**

DOC-CORRECTION-014 正确禁止 renderer 直接把秘密写进 MCP definition，但当时后端还没有可供 MCP assembly 消费的 Credential 引用，因此结论停留在“仅支持匿名 Connector”。

**新证据**

Settings 现在提供 Custom Credential 的 write-only upsert/remove 契约；公共投影只返回 ID、名称和 configured 状态。MCP registry 保存 `credentialBindings`，worker 只在构建运行时配置时把引用解析为 header 或环境变量，并在交给 MCP runtime 前移除引用元数据。删除仍被 Connector 使用的 Credential 会被后端拒绝。

**修正结论**

自定义 Remote/Local MCP 已支持 API Key、header token 和环境变量鉴权，但只允许绑定 Custom Credential 引用。URL userinfo/query/fragment、命令参数 token 和 renderer inline secret 继续禁止。通用第三方 OAuth callback 仍未实现，不得把 Credential 引用描述为 OAuth。

### DOC-CORRECTION-016：Storage 已具备本机数据根目录迁移事务

**原有判断**

DOC-CORRECTION-011 将数据目录迁移列为未实现能力，原因是当时缺少停写、复制校验、重启和失败回滚合同。

**新证据**

Electron 主进程现在独占迁移流程：要求目标为空且与源目录不存在包含关系，停止受管 client-api，复制到同级 staging，按文件数与字节数校验，原子改名，持久化新位置并完成 runtime bootstrap 后才删除旧目录。任一步失败都会删除目标副本、恢复环境和持久化位置，并重新启动旧 runtime。

**修正结论**

本机受管模式可以从 Storage 页面迁移数据根目录。云存储、同步和多机迁移仍未实现；外部管理的 client-api 也不能执行该迁移。

### DOC-CORRECTION-017：Files 引用必须使用稳定类型合同

**原有判断**

早期规划把 `@`、`#`、`/` 视为输入框文本补全，容易让显示标签进入 prompt 后再由模型猜测对应资源。

**新证据**

资源、Session 和 Skill 都有稳定 ID；Project 文件还具有 version/hash。client-api 与 worker 可以在运行前重新校验 Project 归属、版本和 capability attachment。

**修正结论**

Composer 中 `@ Artifact/File`、`# Session` 和 `/ Skill` 只负责选择，提交时使用 typed reference parts。显示名称不是授权或定位依据；资源变化、跨 Project 引用和已卸载 Skill 必须在 runtime boundary 失败。Files 选中的本地文件夹会复制进 Project workspace，并通过 durable source manifest 管理，不长期依赖原始外部路径。

## 13. Phase 15B 后的有效实施基线

- Skill、MCP Connector、Specialist 均支持创建、读取定义、编辑、删除和 Project attachment；Skill 另支持本地 bundle、公开 GitHub 导入以及持久化草稿发布；
- Custom Credential 支撑鉴权 MCP，秘密不进入 capability catalog、公开设置投影或 renderer 持久状态；
- Specialist 对每个已分配 MCP Connector 可以继续限制允许工具，运行时取 Connector 全局过滤与 Specialist 过滤的交集；
- Files 支持 Project 内 Artifact、workspace 文件和导入 source 的统一浏览、搜索、来源过滤、列表/网格、结构化引用，以及 Markdown、JSON、CSV/TSV 有界预览；
- Artifact 支持重命名、star、hide、删除、复制链接、下载、Finder 定位和导出；Session 支持搜索、重命名、删除和 Project 默认策略；
- General、Credentials、Storage、Usage 与 Session options 只显示后端可兑现状态；远程 Compute execution、云存储、沙箱和第三方 OAuth 仍是明确暂缓项；
- ToolUniverse 与 TxAgent 不进入本基线，只有用户后续明确指令才能开始评估。

### DOC-CORRECTION-018：已安装前端依赖不应经过包管理器启动开发服务器

**原有判断**

一键启动器在依赖已经准备好时仍执行 `pnpm dev`，表面上只是在运行本地脚本。

**新证据**

在离线回归中，包管理器会先检查或解析自身版本，导致已经完整安装的桌面端仍可能因网络不可用而报 `fetch failed`。项目内 Vite 可执行文件本身不需要该网络步骤。

**修正结论**

启动器只在确实缺少依赖时调用 pnpm 安装；依赖就绪后直接调用项目内 `node_modules/.bin/vite`。这样安装责任与运行责任分离，离线启动不再取决于全局 pnpm 状态或包管理器网络检查。
