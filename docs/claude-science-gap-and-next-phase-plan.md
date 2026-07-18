# gm-science 后续框架完善规划

## 0. 文档目的

本文基于对 Claude Science 实机界面的只读操作，以及对 gm-science 当前实现的代码核对，规划 Phase 7C 之后的框架完善工作。

本文解决三个问题：

1. 明确 gm-science 与 Claude Science 当前的真实差距。
2. 修正“科研功能已经较多，所以整体框架基本完成”的判断偏差。
3. 给出不复制 Claude Science 实现、但吸收其产品语义的后续实施顺序。

本文是实施规划，不代表所有列出的功能都应一次完成。每个阶段必须保持一键启动、核心对话和已有科研流程可用，并经过自动化测试和真实桌面验收后再进入下一阶段。

## 1. 前提与约束

后续实施遵循以下已确认约束：

- gm-science 是本地运行的个人科研智能体和科研工作台。
- 默认优先使用 OpenAI 系列模型，通过 openppx 的 provider 和 agent runtime 调用。
- 前后端继续分离：Electron/React 负责桌面交互，openppx client-api 负责运行时能力。
- 复用 openppx 和 ppx-client，不能在 gm-science 内建立第二套 Session、TaskRun、Skill、MCP 或 Memory 运行时。
- 当前没有正式用户，不承担旧数据兼容成本；必要时可以调整 schema 或清理开发数据。
- 当前阶段不以完整安全沙箱为重点，但不得把尚未实现的安全边界描述成已经生效。
- ToolUniverse、TxAgent 和大规模专业工具接入放在整体框架稳定之后。
- 非敏感配置继续集中在 `~/.gm-science` 的配置文件中；密钥等敏感信息后续使用加密凭据存储，配置文件只保存凭据引用。

## 2. 对比结论

### 2.1 已经理解正确的部分

gm-science 当前设计和实现已经正确吸收了以下产品结构：

- Project 是长期科研工作的边界。
- Description 只用于展示，Agent Context 注入 Project 内所有 agent。
- Session 是连续科研交互记录，并且必须归属明确的 Project。
- Artifact 是论文、报告、批评、数据、图表和代码等持久化科研结果。
- 主控 agent 可以调用专业科研能力和专家智能体。
- 本地 Python 任务应成为可观察、可取消、可重试的 TaskRun。
- 数据分析应保留输入、代码、审批、运行和结果的 provenance。
- Skills、Connectors、Specialists 应当能按 Project 配置。

现有文献检索、Paper Reader、Research Reviewer、本地 Python Run、Data Analyst 草案审批等能力不是无效工作。它们已经形成了 gm-science 的科研垂直闭环，并且部分交互比通用科研工作台更明确。

### 2.2 主要理解偏差

当前实现把 Claude Science 的 Skills、Connectors 和 Specialists 主要理解为“可开关的能力列表”。实机验证表明，它们更接近一个可安装、可组合、可授权、可审计的运行时资源注册系统。

具体表现为：

- Skill 是包含说明、代码、许可和外部依赖的能力包，不只是一个 prompt 开关。
- Connector 是可发现工具的连接器，通常通过 MCP 暴露能力，并具有连接状态和审批策略。
- Specialist 是可配置指令、模型、Skills 和 Connectors 的专家 agent，不只是主控 agent 内部写死的子流程。
- Compute 表示任务执行位置和执行能力，不等同于 Run 列表。
- Files 是统一的科研上下文入口，不只是 Artifact 列表。
- Memory、Credentials、Permissions 和 Network 共同构成工作台的长期状态与治理层。

因此，gm-science 当前更接近“具备若干科研流程的本地 Agent”，距离“可扩展的本地科研工作台”仍有明显差距。

### 2.3 完成度口径修正

后续不再使用单一完成百分比描述项目进度。

采用两套口径：

- **已有路线完成度**：Phase 1 到 Phase 7C 的基础闭环约完成 96%。
- **科研工作台语义完成度**：按 Claude Science 的核心产品结构估算，目前约完成 60%。

第二个口径较低，主要因为动态能力注册、统一 Files、会话级调度、Memory 和治理层尚未完成，而不是因为已有科研流程不可用。

### 2.4 2026-07-18 Specialist 实机补充结论

重新登录 Claude Science 后，对 Specialist 新建页和 Reviewer 详情进行了只读验证，进一步确认：

- 自定义 Specialist 的 Instructions 是追加到 Claude Science 基础提示词，不是替换基础提示词。
- Description 只用于 registry 和 delegation 菜单展示，不进入 agent prompt；Agent ID 用于日志和委派。
- 自定义 Specialist 页面没有独立模型选择。子 agent 使用 `General -> Subagent model`，并可配置为跟随主模型。
- Specialist 可以分配 Skills 和 Connectors；Connector 还能继续细化到其内部具体工具的启用集合。
- 新建页会预选当前可用 Skills 和 Connectors，但 gm-science 不照搬这一默认值。作为本地科研智能体，第一版继续采用显式分配和最小能力集合。
- `Chat with Claude` 不直接创建 agent，而是打开预填 `/Customize` 的新 Session，由自然语言工作流帮助用户生成 Specialist 定义；`Write from scratch` 才进入结构化表单。
- 内置 Reviewer 保留不可移除的基础 rubric。用户只能追加更严格的 Instructions，并可补充领域 Skills 和 Connectors。

这些结论修正了“每个 Specialist 应在 UI 中独立选择模型”的假设。gm-science 配置仍保留可选的单 Specialist 模型覆盖，以满足 openppx provider 的高级用法，但产品默认应使用统一的子 agent 模型策略。Connector 内工具级白名单和 `/Customize` 创建向导作为后续 registry write 与 Session orchestration 能力实施。

## 3. 后续产品目标

后续阶段的一句话目标是：

> 将 gm-science 从内置科研流程集合，演进为由 openppx 驱动、能力可安装和组合、过程可审阅、结果可追溯的本地个人科研工作台。

产品中心仍然是自然语言科研交互，但用户还应能够：

- 查看系统有哪些能力以及能力来自哪里。
- 将 Skill、Connector 和 Specialist 安装或附加到 Project。
- 在 Session 内选择是否委派、使用哪个 Specialist、Memory 和 Compute Target。
- 从统一 Files 面板选择本机文件、Project 文件、Artifact、Dataset 和 Run 输出。
- 使用 `@`、`#` 和 `/` 显式引用科研上下文。
- 审阅长期记忆、外部连接、凭据使用和关键能力变更。
- 理解任务在哪里运行、使用了哪些输入、产生了哪些结果。

## 4. 差距与优先级

| 优先级 | 差距 | 当前状态 | 目标 |
| --- | --- | --- | --- |
| P0 | 动态能力注册 | gm-science catalog 硬编码少量能力 | 从 openppx 动态发现并投影 Skill、MCP Connector 和 Specialist |
| P0 | 统一 Files 与引用 | Artifacts、Data、Runs 分离，Composer 只有纯文本 | 统一资源浏览，并使用结构化引用进入消息上下文 |
| P0 | 会话级调度 | 主要依赖 Project 默认值和主控自动判断 | Session 可选择 Delegation、Specialist、Memory、Compute 和 Review Policy |
| P1 | Memory 产品层 | openppx 有底座，gm-science 无可见管理界面 | 用户和 Project 记忆可查看、编辑、禁用和追溯 |
| P1 | 凭据与审批 | 主要依赖配置文件 | 敏感凭据加密保存，连接器和注册表写操作可审批 |
| P1 | Compute Target | 已有本地 Python TaskRun | 将执行目标与 TaskRun 状态机分离，先支持 Local |
| P2 | Network 管理 | 文献源配置存在，无统一界面 | 配置镜像、CA 和连接器域名策略，沙箱级强制后置 |
| P2 | Storage、Usage、General | 配置和诊断分散 | 提供数据目录、用量和模型策略的统一管理界面 |
| P3 | 专业科研生态 | 三个文献源和少量专家 | 框架冻结后接入 ToolUniverse 和领域工具 |

## 5. 目标架构

### 5.1 保持现有分层

继续保持以下职责边界：

```text
gm-science-desktop
  UI、交互状态、系统文件选择器、桌面凭据入口

ppx-client adapter / Electron IPC
  稳定客户端契约、流事件转发、桌面能力桥接

openppx client-api
  Project、Session、Capability、Artifact、Memory、TaskRun API

openppx runtime
  ADK agent、Skill、MCP、Specialist、Memory、TaskRun、provider

~/.gm-science
  配置、数据库、Project workspace、Artifacts、日志、凭据引用
```

gm-science 只增加科研产品层模型和投影，不复制 openppx 的运行时事实源。

### 5.2 统一能力模型

能力定义和能力使用必须分离：

```text
CapabilityDefinition
  id
  kind: skill | connector | specialist
  name
  description
  source
  version
  availability
  license
  data_sharing
  configuration_requirements
  kind_specific_metadata

ProjectCapabilityAttachment
  project_id
  capability_id
  enabled
  configuration_overrides

SessionPolicy
  session_id
  delegation
  memory
  specialist_id
  compute_target_id
  review_policy
```

关键原则：

- 全局安装不等于所有 Project 自动启用。
- Project 启用不等于所有 Session 必须使用。
- Session 选择不修改 Project 默认配置。
- capability definition 来自真实 openppx registry，不由 UI 维护第二份静态清单。
- 各种 capability 可以共享展示字段，但不能用一个无边界的大对象抹平 Skill、Connector 和 Specialist 的语义差异。

### 5.3 统一科研资源引用

Files 面板使用统一资源引用，而不是把文件路径直接拼接进 prompt：

```text
ResourceRef
  kind: artifact | dataset | run_output | project_file | attached_folder_file | session
  id
  display_name
  project_id
  mime_type
  version_or_hash
  access_mode
```

Composer 解析出的 `@artifact`、`#session` 和 `/skill` 必须作为结构化 message parts 发送。后端在运行前解析引用、校验 Project 归属、控制读取范围并记录 provenance。

### 5.4 Compute 与 Run 分离

`ComputeTarget` 回答“在哪里运行”，`TaskRun` 回答“任务运行到哪里”。

```text
ComputeTarget
  id
  type: local | ssh | modal | model_endpoint
  name
  availability
  capability_summary
  credential_refs

TaskRun
  继续作为状态、事件、取消、重试和 Artifact 的唯一事实源
```

第一版 ComputeTarget 只正式提供 `local`。SSH、Modal 和模型 endpoint 在接口稳定后增加适配器，不能为远程计算另建状态机。

## 6. 分阶段实施计划

### Phase 8A：动态 Capability Registry

#### 目标

将当前硬编码 catalog 替换为 openppx 运行时注册表的科研产品投影。

#### 实施内容

后端：

- 从 openppx `SkillRegistry` 发现内置、用户和 workspace Skills。
- 从 openppx MCP registry 投影可用 Connectors、连接状态和工具摘要。
- 扩展 Specialist registry，使专家定义能够声明模型、指令、Skills、Connectors 和权限摘要。
- 保留 Project capability attachment，调整为引用动态 definition。
- 增加 capability detail API，返回文件清单、来源、许可、配置要求和状态。
- 明确 registry refresh、attach、detach 和 enable/disable 的行为。

桌面端：

- Skills、Connectors、Specialists 支持搜索、来源分组和详情页。
- 展示 Built-in、Local、Imported、Custom 等来源。
- 在详情页展示状态、许可、配置要求和外部数据共享说明。
- 第一版允许发现和附加本地 Skill；GitHub 导入可在 registry 契约稳定后加入。
- Connector 详情展示 MCP 工具摘要和审批策略，不暴露密钥值。
- Specialist 详情允许设置额外指令和分配 Skills、Connectors。

#### 复用点

- 复用 openppx `SkillRegistry`，不再维护 gm-science 专用 Skill 扫描器。
- 复用 openppx MCP registry 和现有 MCP 调用链。
- 复用现有 Paper Reader、Research Reviewer 作为首批 SpecialistDefinition。
- 继续通过 client-api 和 Electron adapter 暴露能力。

#### 验收标准

- 新增一个本地 `SKILL.md` 后，刷新 registry 即可在 UI 出现，无需修改 gm-science 代码。
- 移除或配置错误的 capability 显示真实 unavailable 状态，而不是静默消失。
- Project attach/detach 后，agent 可用能力和 UI 状态一致。
- 未附加的 Skill、Connector 和 Specialist 不能被该 Project 调用。
- capability detail 不返回 credential secret 或本机无关绝对路径。

#### 测试

- Skill、MCP、Specialist registry 单元测试。
- Project attachment 和未知 capability 边界测试。
- client-api contract 测试。
- Electron adapter 和 React 设置页测试。
- 本地 Skill 动态发现的真实桌面验收。

### Phase 8B：统一 Files 与上下文引用

#### 目标

将 Artifacts、Datasets、Run outputs 和本地 Project 文件统一为可浏览、可搜索、可引用的科研资源。

#### 实施内容

- 将右侧面板升级为 Files 工作区，保留 Artifacts、Data、Runs 的过滤视图。
- 支持 All artifacts、Project workspace 和用户明确附加的本机目录。
- 本机目录默认只读；写权限和更广泛目录访问后续通过权限策略开放。
- 为 Artifact、Dataset、Run output 和文件提供统一详情/预览框架。
- 增加列表和网格视图、类型筛选和全文元数据搜索。
- Composer 支持：
  - `@` 引用 Artifact、Dataset、Run output 和文件。
  - `#` 引用当前 Project 内的 Session。
  - `/` 选择当前 Project 已附加的 Skill。
  - 快捷搜索打开统一命令面板。
- 消息 API 使用结构化引用，不把引用展开为用户可见的伪文本。
- 运行前校验引用归属和文件 hash，运行后写入 Artifact provenance。

#### 验收标准

- 用户能够从 Files 面板或 Composer 选择同一份 Artifact。
- Session 不能引用其他 Project 的私有资源。
- 删除、移动或内容变化的文件会显示明确状态，不悄悄使用旧内容。
- 模型可读取被引用资源，但会话标题和用户消息不泄漏内部上下文包装。
- 原有 Data 和 Runs 流程继续可用。

#### 测试

- ResourceRef schema 和 Project 边界测试。
- Composer suggestion、键盘导航和结构化消息测试。
- 文件 hash、缺失文件和重名资源测试。
- Artifact 搜索和预览组件测试。
- 文献、数据分析和本地 Run 三条回归验收。

### Phase 8C：Session Policy 与专家调度

#### 目标

让用户在会话级明确控制 agent 如何工作，而不要求理解内部 agent 编排。

#### 实施内容

- 新增 Session Policy：
  - Delegation 开关。
  - Memory 开关。
  - Specialist 选择。
  - Compute Target 选择。
  - Review Policy 选择。
- Project 保存默认策略，新 Session 复制默认值；后续修改 Session 时不反向修改 Project。
- 主控 agent 根据显式 Session Policy 和请求意图进行调度。
- 支持显式“Request review”，将当前结果或选定 Artifact 交给 Reviewer。
- Specialist 接收结构化任务包：目标、输入引用、约束和期望输出 schema。
- 将主控、Specialist 和 Reviewer 的事件统一投影到现有运行流，不创建新的会话事实源。
- 明确自动调度和用户显式选择冲突时，以用户选择优先。

#### 验收标准

- 关闭 Delegation 后不会启动 Specialist。
- 显式选择 Specialist 后可观察其开始、结束、失败和输出 Artifact。
- Session 选择只影响当前 Session。
- Request review 可审查指定 Artifact，并保存 critique provenance。
- Specialist 不能使用未分配或未附加的 Skill/Connector。

#### 测试

- Session Policy 持久化和继承测试。
- 调度优先级和 capability enforcement 测试。
- Specialist 失败、取消和重试测试。
- 主控到 Specialist 的结构化上下文测试。
- Reviewer 显式触发的真实桌面验收。

### Phase 8D：可审阅 Memory

#### 目标

将 openppx 的 Memory 能力转化为用户可理解、可编辑、可关闭的科研记忆。

#### 实施内容

- 区分 User Memory 和 Project Memory。
- 支持分类：About you、Research interests、Project facts、Writing preferences、Methods preferences、Important papers。
- 每条 note 保存内容、来源、创建时间、更新时间和适用范围。
- 支持开关、添加、编辑、删除和清理。
- Session Policy 可以关闭读取和写入 Memory。
- Agent 建议写入长期 Memory 时，先生成可审阅候选；第一版不允许无界后台自动积累。
- Memory 召回结果使用结构化上下文注入，并记录使用了哪些 note。

#### 验收标准

- Memory 关闭时不召回、不新增，但已有 note 保持可编辑。
- Project Memory 不跨 Project 泄漏。
- 用户能定位某个回答使用了哪些 Memory note。
- 删除 note 后，新运行不再召回该内容。
- openppx Memory 仍是唯一存储和召回底座。

#### 测试

- Memory scope、开关和删除测试。
- 候选写入审批测试。
- Project 隔离和 prompt 投影测试。
- 重启恢复和 UI 编辑测试。

### Phase 8E：Credentials、Permissions 与 Network 最小治理闭环

#### 目标

在继续增加外部服务前，补齐敏感配置、连接器审批和注册表变更的最小治理能力。

#### 实施内容

Credentials：

- 非敏感配置继续保存在统一配置文件。
- secret 使用系统安全存储或加密 vault，配置中只保存 credential reference。
- 支持 OpenAI、GitHub、OpenAlex、云计算服务和自定义 API key 元数据。
- UI 只显示已配置状态、用途和更新时间，不回显完整 secret。

Permissions：

- 首批管理 registry writes：创建/更新 Specialist、发布/编辑/附加 Skill、附加 Connector。
- Connector 支持按连接器设置逐次审批或 skip approvals。
- 本机目录附加、credential use 和远程 Compute 进入明确权限范围。
- 区分 Global、Project、Session 和 one-time approval。

Network：

- 支持 pip/conda mirror、CA bundle 和科研域名分类配置。
- Connector 调用和受管工具遵守域名策略。
- 在完整沙箱前，不宣称能够强制限制任意本地 Python 进程的全部网络访问。

#### 验收标准

- 配置文件和日志中不出现明文 secret。
- 未授权的 registry write 和 credential use 会生成明确审批请求。
- Project 授权不能自动升级为 Global 授权。
- Connector 的 skip approvals 状态可见、可撤销。
- Network UI 明确区分“受管工具策略”和“进程级强制隔离”。

#### 测试

- secret redaction 和持久化测试。
- approval scope 和撤销测试。
- Connector 审批测试。
- 日志与 diagnostics 泄漏检查。
- 配置迁移、清空开发数据和首次启动测试。

### Phase 8F：Compute Target 抽象

#### 目标

在不改变 TaskRun 状态机的前提下，让 Session 和任务选择执行目标。

#### 实施内容

- 引入 ComputeTarget registry 和 executor adapter。
- 将现有本地 Python Run 注册为 `local` target。
- Session Policy 默认使用 Local。
- TaskRun 记录 compute target、环境摘要和执行 provenance。
- UI 展示 Target 可用性、能力、并发和失败原因。
- 第二阶段再加入 SSH host、集群提交节点、Modal 和模型 endpoint。
- 远程 target 必须继续映射到现有 TaskRun、TaskEvent 和 TaskArtifact。

#### 验收标准

- 现有本地 Run 不发生行为回退。
- 用户能在 Session 和 New Run 中看到并选择 Local target。
- 不可用 target 在运行前失败并给出配置原因。
- 重试默认使用原 target，用户可以显式改为其他 target。
- 增加远程 adapter 时不修改桌面端 TaskRun 状态模型。

#### 测试

- ComputeTarget registry 和选择测试。
- Local executor 回归测试。
- unavailable target 和重试测试。
- target provenance 和 client-api contract 测试。

### Phase 8G：Storage、Usage 与 General

#### 目标

将散落在配置文件和 diagnostics 中的常用工作区设置提供为可理解的产品界面。

#### 实施内容

Storage：

- 展示本地数据目录和磁盘占用。
- 按 Projects、Artifacts、Runs、cache 和 logs 分类统计。
- 修改数据目录需要显式迁移流程和失败回滚。

Usage：

- 本地估算 24h、7 days 和 30 days 的 token、模型调用、TaskRun 数量和运行时间。
- 支持按 Project、Session、Agent 和 Model 聚合。
- 对无法从 provider 获取的费用明确标记为估算或未知。

General：

- 默认模型、reasoning effort、subagent model 和 provider route。
- Skill license/use intent。
- UI 语言、主题、更新和 diagnostics。
- 设置写回统一配置，并通过 runtime reload 或明确重启生效。

#### 验收标准

- UI 与配置文件投影一致。
- 修改模型设置后，新 Session 使用新默认值，已有 Session 策略不被静默改写。
- Usage 不把估算值展示为 provider 官方账单。
- 数据目录迁移失败不会损坏原目录。

### Phase 9：科研工具和领域能力扩展

只有 Phase 8A 到 Phase 8C 完成并冻结公共契约后，才开始大规模增加专业能力。

建议顺序：

1. Crossref、Europe PMC、Semantic Scholar 等文献和引用连接器。
2. GitHub、DOI、开放数据集和本地目录连接器。
3. 生物医学、化学、基因组和蛋白质数据源。
4. 评估 ToolUniverse 作为 MCP 或受管工具集合接入。
5. 吸收 TxAgent 的动态工具检索和治疗研究 Specialist 设计。
6. 领域 Specialist 和高级统计模板。

新增工具必须通过统一 registry、权限、凭据和 provenance，不允许绕过框架直接塞进主控 agent。

## 7. 推荐的立即实施迭代

Phase 8A 按能力类型拆成独立小迭代，避免同时修改 Connector、Specialist、Files 和 Composer。

范围：

- 定义稳定的 `CapabilityDefinition` 公共字段。
- 将 gm-science Skills catalog 改为读取 openppx `SkillRegistry`。
- 保留当前 Literature Review Skill 行为。
- 将其他已发现 Skill 以真实来源和 availability 投影到 client-api。
- Project 继续保存 enabled Skill IDs。
- 桌面端增加搜索、来源和基础详情，不做 GitHub 安装。
- 增加单元、client-api、Electron adapter、React 和真实桌面验收。

这个迭代完成后再评审 CapabilityDefinition 是否足以支撑 MCP Connector 和 Specialist，避免过早设计一个不合适的统一 schema。

### 7.1 Phase 8A.1 实施状态

Phase 8A.1 已于 2026-07-18 完成：

- gm-science catalog 已改为从 openppx `SkillRegistry` 动态投影 bundled 和 agent-local Skills。
- 公共能力记录已增加 `source`、`version`、`license` 和有界相对 `files` 字段，并保留 kind-specific `metadata`。
- Project 创建和更新继续按动态 catalog 校验 `enabledSkills`，未知 Skill 会被拒绝。
- Skills 设置页已支持搜索、Built-in/Local/External 来源分组和行内详情。
- GitHub 安装、依赖安装和动态 Specialist 投影仍按原规划后置。

### 7.2 Phase 8A.2 实施状态

Phase 8A.2 于 2026-07-18 实施：

- gm-science catalog 从 openppx `tools.mcpServers` 动态投影 MCP Connectors，并保留 arXiv、PubMed、OpenAlex 三个内置文献来源。
- MCP Connector 使用 `mcp:<server-name>` 作为 Project attachment ID；有效、关闭和配置错误的条目都会进入同一目录。
- Connector detail 返回 transport、工具前缀/过滤器、确认策略、长任务选项、命令 basename 或远端 origin，以及环境变量/header 名称。
- capability API 不返回 MCP 参数、环境变量/header 值、URL 用户信息、查询参数或本机绝对命令路径。
- gm-science Project run 会在 worker 导入 root agent 前按 `enabledConnectors` 过滤 MCP server；未附加的 MCP Connector 不会出现在该 Project 的 agent 工具集中。
- 普通非 Project openppx run 不应用该过滤，继续使用 agent 的全局 MCP 配置。
- Connector 列表的 `Ready` 只表示配置可被 runtime 构建；实际网络/进程连接仍由 MCP toolset 在加载工具时惰性完成，目录刷新不会主动探测外部服务。
- Connectors 设置页已支持搜索、来源分组和 MCP 专用详情，并保持一次性保存 Project attachment 的交互。

Phase 8A.2 不包含 MCP 安装器、凭据编辑器、持续健康探测、工具清单缓存和审批 UI。上述能力应在 Credentials / Permissions / Network 阶段基于现有 openppx runtime 继续扩展，不能建立第二套 MCP 管理器。

### 7.3 Phase 8A.3 实施状态

Phase 8A.3 于 2026-07-18 实施：

- `science.specialists.custom` 已成为本地自定义 Specialist 的配置事实源，每个定义包含稳定 Agent ID、名称、说明、模型覆盖、额外指令、Skills、Connectors、启用状态和自动调度策略。
- Specialist registry 会保留无效定义并投影可操作的配置错误；缺失 Skill、缺失 Connector 或不可用 Connector 不会被静默忽略。
- 自定义 Specialist 使用 Google ADK `LlmAgent` 和 `AgentTool`，在空白子 Session 中接收结构化目标和上下文，不继承主会话历史、Memory 或隐藏推理。
- 子 agent 只获得显式分配的能力：Skill 作为有界参考材料注入；arXiv、PubMed、OpenAlex 合并为来源受限的文献搜索工具；MCP Connector 只构建被分配的 openppx MCP toolset。
- Project 必须同时启用 Specialist 及其全部 Skill/Connector 依赖。AgentTool 在运行前再次执行大小写无关的白名单校验，不能依靠前端开关绕过。
- 自定义 Specialist 使用固定结构化输出，并保存为 `specialist_report` Artifact；provenance 记录 Specialist、模型、Session 和分配的能力。
- Specialists 设置页已支持搜索、来源分组和详情，展示 Agent ID、模型、执行模式、权限摘要、额外指令以及分配的 Skills/Connectors。
- 内置 `paper_reader` 和 `research_reviewer` 的现有输入、证据边界和 Artifact 类型保持不变。

本迭代没有实现 UI 内创建/编辑 Specialist，也没有实现会话级 Specialist 选择、Delegation、Auto-review 或 Reviewer 检查点。配置文件仍是 registry write 入口；修改后需要重启运行时。上述会话策略属于 Phase 8C，不应与 SpecialistDefinition 混为同一状态。

实机补充验证还表明，Claude Science 支持对 Specialist 已分配 Connector 的内部工具继续做启用/禁用。Phase 8A.3 当前只实现 Connector 级白名单；工具级白名单需要先扩展 openppx MCP registry 的稳定工具描述和过滤契约，再进入 Specialist 编辑 UI，不能由前端维护第二份工具名清单。

## 8. 测试与验收策略

每个阶段至少覆盖以下层次：

1. **Domain unit tests**：registry、scope、schema、权限和状态转换。
2. **Runtime integration tests**：openppx 实际 Skill/MCP/Memory/TaskRun。
3. **client-api contract tests**：请求、错误、Project 隔离和流终态。
4. **Electron adapter tests**：IPC 名称、参数投影和错误传播。
5. **React component tests**：状态、键盘、空态、错误态和窄窗口布局。
6. **真实桌面验收**：从空数据目录一键启动，执行核心用户路径并保存结果记录。
7. **回归测试**：文献检索、Paper Reader、Reviewer、本地 Run、数据导入和分析审批必须持续通过。

对于 UI 阶段，至少检查：

- 1200×768 和 1100×760 桌面窗口。
- 较窄窗口下无文本重叠和不可达操作。
- 弹窗 header/footer 稳定，长内容内部滚动。
- 键盘选择、焦点恢复和可访问名称。

## 9. 暂缓项

以下项目暂不进入最近两个迭代：

- 完整 Docker 或虚拟机沙箱。
- 任意本地进程的强制网络隔离。
- SSH、集群、Modal 和远程 GPU 实际执行。
- GitHub Skill marketplace 完整安装和升级。
- ToolUniverse 全量安装。
- Jupyter/Notebook 编辑器。
- 云同步和多人协作。
- 大量领域数据源和领域 Specialist。

暂缓不代表架构忽略。Capability、ComputeTarget、Permission 和 ResourceRef 的契约必须为后续扩展保留清晰边界。

## 10. 风险与控制

| 风险 | 表现 | 控制方式 |
| --- | --- | --- |
| 继续堆科研功能 | 工具越来越多，注册和权限仍是硬编码 | Phase 8A 到 8C 完成前限制新增专业工具 |
| 过度统一 schema | Skill、Connector、Specialist 失去各自语义 | 只共享公共 header，保留 kind-specific detail |
| runtime 分裂 | gm-science 建立第二套 registry 或 Run 状态 | openppx registry/TaskRun/Memory 是唯一事实源 |
| UI 先于后端 | 页面看起来完整但没有真实状态 | 只展示有 client-api 契约和测试的操作 |
| 权限名存实亡 | UI 有 allowlist，但本地进程不受限制 | 明确策略适用范围，不虚假声明沙箱能力 |
| 配置复杂 | 新用户必须理解大量科研基础设施 | 保持自然语言为主入口，设置使用合理默认值 |
| 扩展破坏科研可靠性 | 第三方工具结果无来源或许可不明 | registry 保存来源、许可、数据共享和 provenance |

## 11. 阶段完成定义

一个阶段只有同时满足以下条件才算完成：

- 领域模型和 client-api 契约已经评审。
- 后端、Electron 和桌面端使用同一事实源。
- 新增功能具备关键路径和边界测试。
- 一键启动仍能在空数据目录完成初始化。
- 已有科研核心路径回归通过。
- 完成至少一次真实桌面人工验收。
- 设计文档、配置说明和实际行为一致。
- 已知限制被明确记录，不用 UI 文案掩盖未实现能力。

## 12. 宏观进度跟踪

后续进度按能力支柱报告，不再只给一个百分比：

| 支柱 | 当前判断 |
| --- | --- |
| Project / Session / Artifact 基础 | 基本完成 |
| 文献与科研垂直闭环 | 第一版完成 |
| 本地执行与数据分析 | 第一版完成 |
| 动态能力注册与组合 | Skill、MCP Connector 和配置驱动 Specialist 第一版完成；安装/编辑与治理待后续阶段 |
| 统一 Files 与上下文引用 | 尚未完成 |
| 会话级调度控制 | 部分完成 |
| 可审阅 Memory | 底座存在，产品层未完成 |
| Credentials / Permissions / Network | 未形成产品闭环 |
| 多 Compute Target | 仅完成 Local Run 基础 |
| 专业科研生态 | 等框架冻结后扩展 |

近期目标不是把科研工具数量做大，而是先完成前三个 P0 项，使以后新增一个 Skill、Connector 或 Specialist 不再需要修改多个硬编码清单和专用 UI。
