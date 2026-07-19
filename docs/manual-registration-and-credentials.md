# 人工注册、登录与凭据准备

本文档集中记录 gm-science 当前支持的服务中，所有需要用户手动注册、登录、授权、创建 API Key 或准备本地端点的项目。后续新增此类依赖时，应同步更新本文档，不把注册要求分散在其他设计文档中。

## 基本原则

- 凭据优先通过 gm-science 的 `Settings > Credentials` 写入本机配置。
- 默认 Agent 配置保存在 `~/.gm-science/science-research/config.json`；密钥不会从后端回传到界面。
- 密钥输入框留空表示保留现有值，只有点击 `Remove` 才会删除。
- 不要把 API Key、OAuth Token 或账号信息写进项目文档、对话、代码仓库或截图。
- 模型服务可能有地区、组织权限、套餐、额度或计费要求；注册成功不等于所有模型均可调用。

## 总览

| 服务 | 人工操作 | gm-science 是否必需 | 配置位置 |
| --- | --- | --- | --- |
| OpenAI Codex | 使用 ChatGPT 账号登录 Codex | 默认模型路径必需 | 启动器/Codex 登录流程 |
| OpenAI API | 注册 OpenAI Platform、创建 API Key | 选择 OpenAI provider 时必需 | `Settings > Credentials` |
| Google Gemini | 登录 Google AI Studio、创建 Gemini API Key | 选择 Google Gemini provider 时必需 | `Settings > Credentials` |
| Anthropic | 注册 Claude Console、创建 API Key | 选择 Anthropic provider 时必需 | `Settings > Credentials` |
| OpenAlex | 注册免费账号、复制 API Key | 使用 OpenAlex Connector 时必需 | `Settings > Credentials` |
| PubMed / NCBI | 提供联系邮箱；My NCBI API Key 可选 | 联系邮箱必需，API Key 可选 | `Settings > Credentials` |
| arXiv | 无 | 不需要注册 | 无 |
| 自定义 MCP Connector | 匿名服务无需注册；鉴权要求由服务提供方决定 | 仅使用该 Connector 时 | 先在 `Settings > Credentials > Custom` 保存秘密，再到 `Settings > Connectors` 绑定引用 |
| Custom OpenAI-compatible | 准备兼容端点及其可选凭据 | 仅选择该 provider 时 | 本机配置与 `Settings > Credentials` |
| vLLM/Local | 自行启动本地 vLLM 服务 | 仅选择该 provider 时 | 本机配置；API Key 通常可选 |
| 私有 package mirror | 准备 mirror URL 和可选 CA bundle | 仅使用组织内 pip/conda mirror 时 | `Settings > Network`；URL 凭据当前不支持 |
| Modal | 注册 Modal 并创建 account token | 仅配置 Modal Compute Target 时 | 启动环境；当前只检测配置，不执行任务 |
| NVIDIA 托管 NIM | 注册 NVIDIA Developer/NGC 并创建合适的 API Key | 仅配置 NVIDIA BioNeMo NIM 时 | 启动环境；当前只检测配置，不执行任务 |
| SSH Compute Target | 准备 SSH 账号、网络和密钥文件 | 仅配置 SSH host 时 | `Settings > Compute`；当前只做连通性检查 |
| 自定义 Model endpoint | 准备 HTTP(S) endpoint、健康路径和可选 API Key | 仅配置自定义 endpoint 时 | `Settings > Compute`；当前只做健康检查 |

## OpenAI Codex（推荐）

gm-science 默认使用 `openai_codex` provider，通过 ChatGPT 账号的 Codex OAuth 登录，不要求把 OpenAI API Key 粘贴到 Credentials 页面。

1. 准备可以使用 Codex 的 ChatGPT 账号。
2. 通过 gm-science 启动器或 Codex 登录流程选择 **Sign in with ChatGPT**。
3. 在浏览器完成登录与授权后返回 gm-science。
4. 在 `Settings > Credentials` 确认 OpenAI Codex 显示为 `Configured`。

官方说明：[Using Codex with your ChatGPT plan](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan)。可用额度和模型访问范围取决于账号与工作区策略。

## OpenAI API

这是独立于 ChatGPT/Codex 登录的计费与凭据体系。

1. 注册或登录 [OpenAI Platform](https://platform.openai.com/)。
2. 根据账号情况完成组织、计费或验证设置。
3. 在 Platform 创建 API Key。
4. 在 General 中选择 `OpenAI`，然后到 Credentials 为当前 provider 写入 API Key。

官方快速开始：[Developer quickstart](https://platform.openai.com/docs/quickstart/make-your-first-api-request)。

## Google Gemini

1. 登录 [Google AI Studio](https://ai.google.dev/aistudio)。
2. 接受相关服务条款，并选择或创建 Google Cloud Project。
3. 在 API Keys 页面创建适用于 Gemini API 的 Key。
4. 在 General 中选择 `Google Gemini`，然后到 Credentials 写入 Key。

官方说明：[Using Gemini API keys](https://ai.google.dev/gemini-api/docs/api-key)。Google 可能要求项目权限、受支持地区或启用计费；应按官方页面的当前要求操作。

## Anthropic

Claude.ai 订阅与 Claude API 凭据不是同一套访问方式。gm-science 的 `Anthropic` provider 使用 Claude API Key。

1. 注册或登录 [Claude Console](https://platform.claude.com/)。
2. 根据账号情况创建 Workspace，并配置 API 计费。
3. 在 `Settings > API keys` 创建 Key。
4. 在 General 中选择 `Anthropic`，然后到 Credentials 写入 Key。

官方说明：[Claude Platform authentication](https://platform.claude.com/docs/en/manage-claude/authentication)。

## OpenAlex

OpenAlex 当前 API 使用免费 API Key；旧的 `mailto` polite-pool 方式不应作为替代方案。

1. 注册或登录 OpenAlex。
2. 打开 [OpenAlex API settings](https://openalex.org/settings/api)。
3. 复制 API Key，在 gm-science Credentials 的 OpenAlex 区域写入。
4. 保存后，OpenAlex Connector 应从 `needs configuration` 变为 `ready`。

官方说明：[Authentication & Pricing](https://developers.openalex.org/guides/authentication)。免费额度、计费规则和限流以该页面为准。

## PubMed / NCBI E-utilities

gm-science 调用 PubMed 时会发送 `tool=gm-science` 和用户配置的联系邮箱。为避免匿名、不可联系的请求，当前产品要求填写有效联系邮箱。

### 基础使用

1. 在 Credentials 的 PubMed 区域填写有效联系邮箱。
2. 默认不需要 NCBI 账号或 API Key。
3. 无 Key 时，gm-science 按不超过约 3 次请求/秒的策略调用 E-utilities。

### 可选 API Key

需要更高的默认请求额度时：

1. 注册或登录 [My NCBI](https://www.ncbi.nlm.nih.gov/account/)。
2. 打开 Account Settings，在 `API Key Management` 中创建 API Key。
3. 在 gm-science Credentials 的 PubMed 区域写入该 Key。

NCBI 文档说明，无 Key 默认上限为每个 IP 每秒 3 次请求，Key 通常提高到每秒 10 次：[E-utilities usage guidelines](https://www.ncbi.nlm.nih.gov/books/NBK25497/)。

### 工具与邮箱注册

NCBI 还说明，持续开发或在发生违规封禁后的恢复场景中，软件开发者可能需要向 NCBI 注册 `tool` 和 `email` 值。gm-science 的默认工具名是 `gm-science`。具体流程和联系地址以同一份 [E-utilities usage guidelines](https://www.ncbi.nlm.nih.gov/books/NBK25497/) 为准。

## 无需第三方注册的路径

### arXiv

当前 arXiv Connector 使用公开接口，无需账号或 API Key。仍需遵守服务的访问策略和限流要求。

### 自定义 MCP Connector

gm-science 可以从 `Settings > Connectors` 创建 Remote URL 或本地 stdio command Connector：

- Remote URL 必须是没有用户名、密码、query 或 fragment 的 HTTP(S) 地址；
- Local command 会解析为 argv 并直接启动，不通过 shell；只应配置用户信任的本机程序；
- 需要 header 或环境变量鉴权时，先在 `Settings > Credentials > Custom` 创建 write-only Credential，再在 Connector 表单中把 header/环境变量名绑定到 Credential ID；
- Connector registry 只保存 Credential 引用，秘密值只在后端组装 MCP runtime 配置时解析，不回传到 renderer；
- 创建只写入 openppx 已有的 MCP registry，不会自动附加到任何 Project；
- catalog 中的 `Ready` 表示配置可由 runtime 构建，实际连接在工具加载时验证。

如果服务要求 API Key、header token 或环境变量，用户需要按服务提供方要求注册和申请凭据，再使用上述 Custom Credential 引用。当前不提供通用第三方 OAuth 回调管理；需要交互式 OAuth 的 MCP 服务必须由其自身客户端完成登录，或等待未来专用 OAuth adapter。不要把 token 放进 URL、命令参数、项目文档或对话。

### Custom OpenAI-compatible

gm-science 不要求第三方账号，但用户必须自行准备可访问的 OpenAI-compatible endpoint。该端点是否需要注册或 API Key，取决于端点运营方；不要使用来源不明的代理服务。

### vLLM/Local

本地 vLLM 不需要第三方注册。用户需要自行启动兼容服务并配置可访问的本地地址；是否启用 API Key 由本地部署策略决定。

### 私有 package mirror

组织内 pip/conda mirror 通常由管理员提供基础 URL、网络访问权限和可选 CA bundle。gm-science 当前只接受不含凭据、query 和 fragment 的 HTTP(S) URL，并把脱敏后的 URL 注入受管本地 TaskRun。不要把用户名、密码或 token 嵌入 mirror URL；需要鉴权的 mirror 必须等待后续独立的 write-only credential contract。

## 可选 Compute 服务

以下项目均不是 gm-science 本地科研闭环的必需条件。Phase 13 只保存脱敏配置并执行显式健康检查，尚未实现远程 TaskRun 提交、取消、重试、日志或 Artifact 回收。

### Modal

1. 注册或登录 Modal。
2. 按 Modal 官方流程创建 account token。
3. 让启动 gm-science 的环境可读取 `MODAL_TOKEN_ID` 和 `MODAL_TOKEN_SECRET`。
4. `Settings > Compute` 只会显示凭据是否存在；当前不会向 Modal 提交任务。

Modal 官方说明：[Invoking deployed Functions](https://modal.com/docs/guide/trigger-deployed-functions)。

### NVIDIA 托管 NIM

1. 注册或登录 NVIDIA Developer/NGC。
2. 如果调用 NVIDIA 托管 NIM API，在 build.nvidia.com 创建 NVIDIA API Key，并确保账号具有对应 endpoint 权限。
3. 让启动 gm-science 的环境可读取 `NVIDIA_API_KEY`。
4. 该 key 与用于拉取 NGC 容器的 NGC personal key 用途不同，不应混用。

NVIDIA 官方说明：[Authentication and API keys](https://docs.nvidia.com/nemo/retriever/latest/extraction/ngc-api-key/index.html)。

### SSH Compute Target

SSH 不要求特定第三方注册，但用户需要自行准备：可解析的 host、端口、用户名、网络访问权限和本机 SSH identity 文件。gm-science 不读取或回传 identity 文件内容；当前只检查目标端口是否可达。

### 自定义 Model endpoint

用户需要自行准备 HTTP(S) endpoint、无 query/fragment 的基础 URL、健康检查路径和可选 bearer API Key。API Key 采用 write-only 更新，不从公共设置 API 返回。当前健康检查只表示 endpoint 能响应，不表示 gm-science 已能用它执行科研任务。

## 维护要求

新增模型 provider、Connector、云计算或存储服务时，如果包含以下任一操作，必须先更新本文档再视为功能完成：

- 创建第三方账号或组织；
- 登录或 OAuth 授权；
- 创建、申请或审核 API Key；
- 开通计费、额度或模型权限；
- 注册应用标识、联系邮箱、回调地址或网络白名单；
- 人工部署并配置本地/远程兼容端点。
