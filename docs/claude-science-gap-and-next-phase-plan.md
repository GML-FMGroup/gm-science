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
- ToolUniverse 不进入当前路线，只有收到用户明确指令后才评估；TxAgent 和大规模专业工具接入也必须晚于 Claude Science 复现基线。
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

Phase 15B 后，gm-science 已具备本地科研工作台的主要产品骨架。后续差距主要来自明确暂缓的远程执行、云服务、第三方 OAuth 和专业科研生态，而不是核心工作台信息架构缺失。

### 2.3 完成度口径修正

后续不再使用单一完成百分比描述项目进度。

采用两套口径：

- **当前本地复现基线**：本文纳入的 Project、Session、Files、Artifact、Capability、Memory、Settings 和本地执行基线已完成实现与自动化回归。
- **扩展工作台范围**：远程 Compute、云存储、第三方 OAuth、进程沙箱和专业科研生态为显式暂缓，不与本地复现基线混算百分比。

这种口径避免为了追求一个数字，把不可执行的远程候选、伪云存储按钮或缺少后端合同的 OAuth 页面计为完成。扩展项只有在用户明确调整范围并具备真实运行时合同后，才进入新的实施阶段。

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
| P0 | 动态能力注册 | 动态发现、Project attachment 和手动创建第一版完成 | 补齐编辑、删除、上传和导入，同时保持 openppx registry 为唯一事实源 |
| P0 | 统一 Files 与引用 | Artifacts、Data、Runs 分离，Composer 只有纯文本 | 统一资源浏览，并使用结构化引用进入消息上下文 |
| P0 | 会话级调度 | 主要依赖 Project 默认值和主控自动判断 | Session 可选择 Delegation、Specialist、Memory、Compute 和 Review Policy |
| P1 | Memory 产品层 | 第一版完成：User/Project scope、人工 note、候选审批、召回审计 | 后续补充分类治理、批量导入导出和更强检索，不建立第二套 Memory |
| P1 | 凭据与审批 | Credentials 和全局 registry write 授权第一版完成 | 后续增加 Project/Session/one-time approval，不建立第二套权限系统 |
| P1 | Compute Target | Local executor、统一 registry、远程配置和健康检查第一版完成 | 后续为 SSH、Modal、NIM 增加复用 TaskRun 的 executor adapter |
| P2 | Network 管理 | 镜像、CA、分类域名和受管 HTTP/MCP 强制第一版完成 | 后续随沙箱增加进程级网络强制，不夸大当前边界 |
| P2 | Storage、Usage、General | Storage/Usage 本地可观测性和 General provider/model 第一版完成 | 后续仅在具备真实后端契约时增加迁移、计费或模型策略控制 |
| P3 | 专业科研生态 | 三个文献源和少量专家 | Claude Science 复现基线冻结后扩展领域工具；ToolUniverse 只在用户明确指令后评估 |

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
  artifact_id
  relative_path | sanitized_url
  size_bytes
```

Files 选择产生的资源引用必须作为结构化 message parts 发送。后端在运行前解析引用、校验 Project 归属、控制读取范围并记录 provenance。后续 `@artifact`、`#session` 和 `/skill` 语法也必须复用同一消息合同，不能发展成第二套 prompt 字符串协议。

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

##### Phase 8B.1：统一只读资源目录（已完成）

- 新增只读 `ResourceRef` 投影，不新建资源数据库；Artifact、Dataset 和 Run output 继续使用现有 Artifact 事实源。
- 将普通 Project 文件通过有界扫描投影为 `project_file`，并与已有 Artifact 路径去重。
- 右侧通用 Artifacts 面板升级为 Files；Data 与 Runs 继续保留专项流程。
- Files 支持按名称、资源类型、Artifact 类型、MIME 和相对路径搜索。
- 本机路径仅返回 Project 内相对路径；外部 HTTP(S) URL 删除凭据、query 和 fragment；任意目录不进入 UI。
- `science.resources` 配置扫描数量、深度、隐藏文件和排除目录。
- 当前不支持打开/预览本机文件、选择资源进入 Composer、附加任意目录或跨 Project 引用。

##### Phase 8B.2a：Files 选择与 ADK 原生资源上下文（已完成）

- Files 行使用复选框选择 Artifact、Dataset、Run output 或 Project file，并在 Composer 显示可移除的选择摘要。
- 桌面消息合同只发送稳定 `id` 和 `version_or_hash`，不发送绝对路径或文件正文。
- client-api 在创建 run 前校验 Project/Session/Agent 关系、资源归属、重复项、数量上限和乐观版本。
- 独立 Worker 在模型调用前按同一规则再次校验，只读取 Project 内可读文本；外部、二进制和 metadata-only 资源只生成 descriptor。
- 资源正文受单资源和总字符预算限制，配置位于 `science.resources`。
- 模型请求复用现有 Google ADK Runner，构造一个包含多个 `Part` 的 `UserContent`；provenance 保存在 `part_metadata.gm_science_resource`。
- Session 投影把资源 Part 显示为 `resource_ref`，并从用户可见正文和会话标题中排除内部上下文。

##### Phase 8B.2b：预览与统一 Composer 命令（下一阶段）

- 为 Artifact、Dataset、Run output 和文件提供统一详情/预览框架。
- 增加列表和网格视图、类型筛选和全文元数据搜索。
- Composer 支持：
  - `@` 引用 Artifact、Dataset、Run output 和文件。
  - `#` 引用当前 Project 内的 Session。
  - `/` 选择当前 Project 已附加的 Skill。
  - 快捷搜索打开统一命令面板。
- `@` 入口必须复用 8B.2a 的结构化资源消息合同；`#session` 和 `/skill` 分别定义独立的 typed reference，不把引用展开为用户可见的伪文本。
- 快捷搜索、键盘导航和预览都建立在现有 ResourceRef 目录之上，不直接读取任意路径。

##### Phase 8B.3：附加目录与资源状态（后续）

- 支持用户明确附加的本机目录，默认只读。
- 增加缺失、移动、内容变化和重名资源状态。
- 写权限和更广泛目录访问通过后续权限策略开放。

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
- Session Policy 支持 Auto-review；用户要求评审指定 Artifact 时，通过普通会话显式引用该 Artifact 交给 Reviewer，不新增独立 `Request review` 操作。
- Specialist 接收结构化任务包：目标、输入引用、约束和期望输出 schema。
- 将主控、Specialist 和 Reviewer 的事件统一投影到现有运行流，不创建新的会话事实源。
- 明确自动调度和用户显式选择冲突时，以用户选择优先。

#### 验收标准

- 关闭 Delegation 后不会启动 Specialist。
- 显式选择 Specialist 后可观察其开始、结束、失败和输出 Artifact。
- Session 选择只影响当前 Session。
- Auto-review 开启时可观察 Reviewer 产物；普通会话显式评审继续保存 critique provenance。
- Specialist 不能使用未分配或未附加的 Skill/Connector。

#### 测试

- Session Policy 持久化和继承测试。
- 调度优先级和 capability enforcement 测试。
- Specialist 失败、取消和重试测试。
- 主控到 Specialist 的结构化上下文测试。
- Reviewer Auto-review 和普通会话显式评审的真实桌面验收。

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

- 配置统一保存在本机私有配置文件中，由后端校验并以原子方式写入，文件权限限制为当前用户读写。
- UI 只显示配置状态和安全的来源分类；secret 只允许替换或显式删除，不从后端回传，也不进入 renderer 持久化状态。
- 第一版支持 OpenAI Codex、OpenAI API、Google Gemini、Anthropic、Custom OpenAI-compatible、vLLM、PubMed 和 OpenAlex。
- OpenAI Codex OAuth Token 继续使用 provider 自身的 OAuth cache，不复制到 gm-science 配置。
- 当前单用户本机产品不引入第二套 vault。未来进入多用户、云端同步或企业托管时，再评估系统密钥链或加密 vault。
- 所有人工注册、登录、授权和 API Key 准备要求集中维护在 `manual-registration-and-credentials.md`。

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

- 公共 API、renderer 状态、日志和 diagnostics 中不出现 secret；secret 只存在于权限受限的本机配置或 provider OAuth cache。
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

#### Phase 13 实施结果（2026-07-19）

本轮完成 Phase 8E/8F 的治理基础，但不把尚未实现的审批层和远程 executor 记为完成。

Permissions：

- 使用 `science.infrastructure.permissions` 保存八类全局 registry write 授权：Create/Update Agent、Publish/Edit/Attach/Detach Skill、Attach/Detach Connector。
- Project 创建和能力更新在 backend mutation boundary 检查实际需要的授权；拒绝结果使用稳定 `PERMISSION_DENIED` 和 HTTP 403。
- 当前只有 Global grant/revoke，没有 Project、Session、one-time approval 或 approval request 队列。
- 权限开关管理产品注册表写入，不代表本机进程沙箱或操作系统权限。

Network：

- 使用 `science.network` 保存总开关、allowlist 开关、私网开关、pip/conda mirror、CA bundle、分类域名和自定义域名。
- package mirror 和 model endpoint URL 在保存和公开投影时删除用户信息、query 和 fragment；endpoint API Key 只接受 write-only mutation。
- 原生文献 HTTP 请求在传输前执行策略；远程 MCP 在能力投影和 ADK toolset 装配时执行同一策略。
- 受管 worker 通过有边界的环境 payload 接收策略；损坏 payload 失败关闭。
- 本地 TaskRun 继承 package mirror 和 CA 环境，但当前不限制任意用户 Python 代码自行建立网络连接。

Compute：

- 建立统一 target registry，公开 Local、SSH、Modal、NVIDIA BioNeMo NIM 和自定义 HTTP model endpoint。
- public API 只投影脱敏元数据；SSH identity path 和 endpoint API key 不返回 renderer。
- Local 是唯一 `executable=true` 的 target。SSH 和 endpoint 只进行有超时的连通性检查；Modal/NVIDIA 只检查凭据存在性。
- `configured`、`reachable` 和 `executable` 是独立状态。远程可达不意味着可以提交 TaskRun。

已完成 client-api、Electron IPC/preload、typed adapter、mock 和 Claude Science 风格设置页接线。自动化验证为后端 `1354 passed, 111 skipped, 15 subtests passed`，桌面端 `104 passed`，TypeScript 与 renderer/Electron production build 通过。

隔离真实验收覆盖：撤销 Attach Skill 后 Project 创建返回 `403 PERMISSION_DENIED`，恢复授权后创建成功；Network 和 Compute 配置在 client-api 重启后保持；公开设置不返回 endpoint 凭据、URL 用户信息或 query；含 secret 的 Agent 配置文件权限为 `0600`。真实 Electron 已检查首页、Settings、Permissions、Network、Compute、Add target 和 Local health check，状态与后端一致且没有把远程目标显示为可执行。

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

- 默认模型和 provider route 已完成；reasoning effort 与 subagent model 待后续迭代。
- Skill license/use intent。
- UI 语言、主题、更新和 diagnostics。
- 设置写回统一配置，并通过 runtime reload 或明确重启生效。

#### 验收标准

- UI 与配置文件投影一致。
- 修改模型设置后，新 Session 使用新默认值，已有 Session 策略不被静默改写。
- Usage 不把估算值展示为 provider 官方账单。
- 数据目录迁移失败不会损坏原目录。

#### Phase 14 实施结果（2026-07-19）

本轮完成 Storage 和 Usage 的本地可观测性第一版；General 保持已有 provider/model 与 diagnostics 契约，不增加 runtime 无法执行的候选项。

- 后端新增有条目数和时间预算的磁盘扫描；统计真实 gm-science 数据根目录、可写状态、文件数、总占用和 Workspaces、Databases、Cache、Agent configuration、Logs、Other 六类非重叠数据。
- 扫描不跟随符号链接，达到预算或遇到不可读条目时返回 partial 状态与 diagnostics；缺失目录和数据库的只读查询不会创建新数据。
- Usage 复用 openppx token store 和 TaskRun，提供 24h、7d、30d 的请求、输入/输出/总 token、provider/model 分布、运行数量、状态和窗口内运行时间。
- client-api、Electron IPC/preload、typed adapter、mock 和 Claude Science 风格设置页使用同一事实源；页面明确标注 `Local estimate` 和 `Cost unavailable`。
- 自动化验证为后端 `1361 passed, 111 skipped, 15 subtests passed`，桌面端 `110 passed`，TypeScript、renderer/Electron production build 与一键启动 dry-run 通过。
- 隔离 client-api 验证 token/TaskRun 持久化和重启恢复；真实 Electron 验证 Storage 分类、Usage 模型分布和 24h/7d/30d 切换，默认窗口未发现重叠或溢出。

数据目录迁移、云存储、provider 账单和 plan 限额没有实现，也没有用不可用按钮冒充。它们必须分别拥有原子迁移、storage adapter 或价格/账单事实源后再进入产品界面。

### Phase 9：科研工具和领域能力扩展

只有 Phase 8A 到 Phase 8C 完成并冻结公共契约后，才开始大规模增加专业能力。

建议顺序：

1. Crossref、Europe PMC、Semantic Scholar 等文献和引用连接器。
2. GitHub、DOI、开放数据集和本地目录连接器。
3. 生物医学、化学、基因组和蛋白质数据源。
4. ToolUniverse 保持冻结，只有收到用户明确指令后才评估 MCP 或受管工具集合接入。
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

### 7.3A Phase 15A 手动创建实施状态

Phase 15A 于 2026-07-19 完成第一版手动 authoring：

- Skills 页面可以创建经过 ID、大小和内容校验的 Agent-local `SKILL.md`；
- Connectors 页面可以创建匿名 Remote URL 或本地 stdio command MCP，命令解析为 argv 且不经过 shell；
- Specialists 页面可以创建继承统一模型策略的 ADK Specialist，并从当前真实 catalog 精确选择 Skills 和 Connectors；
- authoring service 直接写入 openppx 已有 registry，不建立第二套数据库；新建能力默认不附加任何 Project；
- `publish_skill` 与 `create_agent` 在后端 mutation boundary 强制，重复 ID 返回 conflict，秘密值和不安全 URL 被拒绝；
- client-api、Electron IPC/preload、typed adapter、mock 和 React 表单使用同一合同。

自动化验证通过后，使用隔离数据目录在真实 Electron 中创建 Skill、Local MCP 和 Specialist，并验证三者在 client-api 重启后恢复、保持 `project_enabled=false`，Specialist 只保留所选依赖。创建表单和列表在默认最小高度内无重叠；启动器 `Ctrl+C` 路径同时清理 Electron 与 client-api。

当前没有实现编辑、删除、草稿、上传、GitHub 导入、OAuth、MCP inline secret 或对话式 Customize。这些是下一轮 Claude Science 复现项，不得与已完成的手动创建混记。

实机补充验证还表明，Claude Science 支持对 Specialist 已分配 Connector 的内部工具继续做启用/禁用。Phase 8A.3 当前只实现 Connector 级白名单；工具级白名单需要先扩展 openppx MCP registry 的稳定工具描述和过滤契约，再进入 Specialist 编辑 UI，不能由前端维护第二份工具名清单。

### 7.3B Phase 15B Claude Science 复现基线实施状态

Phase 15B 已补齐上一节记录的主要生命周期缺口：

- Skill、MCP Connector 和 Specialist 具备统一 catalog 下的查看定义、编辑、删除和 Project attachment；内置或非受管定义明确标记为不可编辑。
- Skill 支持本地文件/目录/zip、公开 GitHub 路径导入，以及存放在产品数据根目录中的持久化草稿。草稿可恢复、更新、删除，并通过正式 Skill authoring boundary 发布。
- MCP Connector 使用 Custom Credential 引用表达 header 或环境变量鉴权，runtime 组装时才解析秘密；Specialist 可以对每个已分配 MCP Connector 设置工具级 allowlist。
- Files 支持导入本地文件或文件夹到 Project workspace、durable source manifest、来源过滤、列表/网格、搜索和删除 source；Composer 支持 `@` 资源、`#` Session、`/` Skill 与命令面板，提交的是稳定 typed references。
- Artifact inspection 支持 Markdown、格式化 JSON、CSV/TSV 表格和普通文本的有界预览，并补齐 rename、star/hide、delete、copy link、download、Finder reveal 与 export。
- Session 支持搜索、重命名和删除；Project 设置可编辑新 Session 默认策略；Reviewer 提供 Default、Main model 和 Subagent model 三类真实路由。
- General 已提供 reasoning effort、subagent model 和 license intent；Storage 已支持受管本机数据根目录迁移；Usage 继续只展示本地事实汇总。

本阶段没有扩大产品边界。第三方 OAuth callback、远程 Compute executor、云存储、进程沙箱、ToolUniverse、TxAgent 和大规模领域工具仍不属于 Claude Science 本地复现基线。

### 7.4 Phase 8C.1 实施状态

Phase 8C 的会话策略核心于 2026-07-18 完成第一版：

- Project 保存 `session_policy_defaults`，每个新 Session 在关联 Project 时复制独立快照；修改 Session 不会反向修改 Project，也不会影响同一 Project 的其他 Session。
- Session Policy 当前包含 Delegation、Auto-review、Memory、Specialist、Reviewer model 和 Compute。首版只提供真实可用的 `Reviewer model=Default` 与 `Compute=Local`，没有展示不可执行的远程候选项。
- client-api 提供 Session-scoped GET/PATCH 契约，并按当前 Project 的 Specialist attachment 和 readiness 校验 Paper Reader、Research Reviewer 等候选项。无效或已失效的选择会在运行前失败，不会静默回退。
- Composer 的 Session options 已改为与 Claude Science 同类的轻量菜单，不再错误跳转到全局 Specialists 设置。开关和候选项通过 Electron IPC、preload 和 typed adapter 写入当前 Session。
- worker 在导入 ADK root agent 前接收并校验 Session Policy。Delegation 只开放自动委派候选；显式 Specialist 是用户直接路由，优先于 Delegation 开关。
- Memory 开关直接控制 Google ADK `PreloadMemoryTool` 是否进入该 Session 的 root tools。此处只完成读取入口控制，不等同于可审阅 Memory 产品层。
- Auto-review 开关控制现有 host-side Research Reviewer gate。关闭时不再隐式评审；开启时 Reviewer 的 critique 继续使用已有 Artifact/provenance 机制。
- 主控提示词只描述本 Session 实际可用的委派、Memory 和 Review 行为，Project 未启用或策略未选择的 Specialist 不会被提示词暗示为可用。

验证结果：

- 完整后端回归通过 `1308 passed, 111 skipped, 15 subtests passed`。
- 完整桌面回归通过 `89 passed`，TypeScript 检查与 renderer/Electron 生产构建通过。
- 使用隔离数据目录完成真实 client-api 验收：Project 默认 `memory=true` 被新 Session 继承；更新 Delegation、Auto-review、Memory 和 Paper Reader 后，重启 client-api 再读取仍保持一致。
- 使用隔离数据目录完成真实 Electron 视觉与交互验收：菜单稳定附着在 Composer 上方，不遮挡消息输入和模型选择；Delegation、Auto-review、Memory 可独立切换，Specialist 只展示当前 Project 中真实可用的 `Paper Reader`。关闭并重新打开菜单后，所有选择保持一致。

Phase 8C 尚未全部完成。以下内容继续保留为后续小迭代：Reviewer 独立模型候选、Specialist 生命周期的专用可视化与失败重试，以及 Project 默认策略编辑 UI。Claude Science 实机不存在独立 `Request review` 操作，因此不再把该按钮或额外状态模型列为缺口。

### 7.5 Phase 8D 实施状态

Phase 8D 的可审阅 Memory 核心于 2026-07-19 完成第一版：

- Google ADK `SQLiteMemoryService` 继续作为唯一长期记忆存储和召回底座；批准 note 与候选生命周期共用同一个 `memory.db`。
- 产品层区分 User Memory 和当前 Project Memory。worker 为当前 Project 合并两个 scope 的召回结果，其他 Project 的 note 不可见。
- gm-science 禁用继承的自动会话事实提取。模型只能通过 ADK 原生 `science_propose_memory` 工具提出候选，候选在用户批准前不进入召回集合。
- Memory 设置页支持全局开关、User/Project scope、人工添加、编辑、删除、清理、候选批准/拒绝、来源和召回次数。Session Memory 开关与全局开关取逻辑与；关闭不会删除已有 note。
- 批准候选保留来源 Session、模型、理由和候选 ID；每次召回记录使用次数与 Session，从而可定位回答使用过的 note。
- Electron IPC、preload、typed adapter、mock 和 client-api 使用同一 Project-scoped 契约；包含冒号的稳定领域 ID 由客户端 URL 编码、服务端逐段解码。

验证结果：

- 完整后端回归通过 `1328 passed, 111 skipped, 15 subtests passed`。
- 完整桌面回归通过 `96 passed`，TypeScript 检查与 renderer/Electron 生产构建通过。
- 隔离数据目录验收确认：全局开关和 note 重启保持；Project A note 不会出现在 Project B；真实模型提出候选后，批准前不可召回，批准后新 Session 准确召回指定标记。
- 真实 Electron 验收完成 User note 新增/编辑、Project candidate 拒绝、来源与召回次数展示；最小宽度窗口中的列表和编辑器无重叠或不可达操作。
- 实测发现并修复 TaskRun 状态在输出 Artifact 提升前暴露 `completed` 的竞态；现在任何对外可见的终态都先完成产物注册。

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
- ToolUniverse 相关安装、适配和评估；只有用户明确指令可以解除此暂缓。
- Jupyter/Notebook 编辑器。
- 云同步和多人协作。
- 大量领域数据源和领域 Specialist。

暂缓不代表架构忽略。Capability、ComputeTarget、Permission 和 ResourceRef 的契约必须为后续扩展保留清晰边界。

## 10. 风险与控制

| 风险 | 表现 | 控制方式 |
| --- | --- | --- |
| 继续堆科研功能 | 工具越来越多，注册和权限仍不完整 | Permissions、Network 和 Compute 治理完成前限制新增专业工具 |
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
| 动态能力注册与组合 | Skill/MCP/Specialist 创建、编辑、删除、导入、草稿、Credential 引用、Project attachment 和 Specialist 工具过滤完成本地第一版 |
| 统一 Files 与上下文引用 | 统一目录、source manifest、搜索/过滤、列表/网格、有界内容预览、Composer 命令和 ADK 原生 typed references 完成本地第一版 |
| 会话级调度控制 | Session Policy、Project 默认值、ADK Specialist 路由、Memory 门控、Auto-review 和 Reviewer 模型路由完成第一版 |
| 可审阅 Memory | User/Project note、候选审批、全局/Session 开关、来源和召回审计第一版完成；批量导入导出与更强检索待后续阶段 |
| Credentials / Permissions / Network | Credentials、全局 registry write 授权、镜像/CA/分类域名和受管 HTTP/MCP 强制第一版完成；作用域审批和进程级隔离待后续阶段 |
| 多 Compute Target | Local executor、统一 registry、脱敏配置和健康检查第一版完成；SSH/Modal/NIM/HTTP endpoint executor 尚未实现 |
| Storage / Usage / General | 本地数据目录迁移与磁盘分类、token/TaskRun 用量窗口、provider/model 分布、reasoning effort、subagent model 和 license intent 完成第一版；云存储与官方账单明确不在当前基线 |
| 专业科研生态 | Claude Science 复现基线冻结后扩展；ToolUniverse 仅由用户明确指令解锁 |

### 12.1 Phase 15B 基线验收结果

2026-07-19 使用隔离数据目录完成当前 Claude Science 本地复现基线的收敛验收：

- 完整后端回归通过 `1411 passed, 111 skipped, 15 subtests passed`；跳过项对应可选依赖或外部服务，不是本基线失败。
- 完整桌面回归通过 `126 passed`，TypeScript 检查与 renderer/Electron 生产构建通过。
- 从空数据目录使用一键启动器拉起真实 Electron 和受管 client-api，完成 Project 创建并确认 Project 描述与 Agent Context 正确进入工作区。
- Customize 实机验收覆盖 Skill 草稿创建、稳定 ID、持久化恢复与删除；Credentials 确认 Custom secret 为 write-only，Project 页面确认 Session defaults，General 页面确认 model、reasoning effort、subagent model 和 license intent。
- Files 实机验收覆盖 Artifacts/Data/Runs 标签、来源与类型过滤、列表/网格入口、本机文件与文件夹导入入口以及对应空状态。
- 本轮没有调用外部模型或科研数据服务；真实模型流式对话、文献检索、Memory、数据分析和 Artifact 生命周期已有前序独立验收与自动化回归，本轮只验证新增基线不会破坏启动和工作区主路径。

当前目标从“继续补页面”切换为缺陷收敛和真实研究任务反馈。远程 Compute adapter 必须继续复用 TaskRun。ToolUniverse 不进入当前路线，只有收到用户明确指令后才重新评估。
