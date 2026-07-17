# gm-science

`gm-science` is a local-first personal research agent workspace built on top of the existing openppx runtime and desktop client architecture.

## Repository Layout

- `gm-science-runtime/`: Python runtime derived from `open-ppx`, including the gm-science project/session/artifact store and client-api endpoints.
- `gm-science-desktop/`: Electron + React desktop client derived from `ppx-client`, adapted for the gm-science project workspace UI.
- `docs/`: Project documentation placeholder for repo-local design and implementation notes.

## Local Data

The application stores gm-science project data under `~/.gm-science` by default. Set `GM_SCIENCE_DATA_DIR` to override this location.

## 文献检索配置

gm-science 原生支持 arXiv、PubMed 和 OpenAlex。配置统一位于：

```text
~/.gm-science/science-research/config.json
```

首次启动后，编辑其中的 `science.literature`：

```json
{
  "science": {
    "literature": {
      "defaultSources": ["arxiv", "pubmed", "openalex"],
      "maxResultsPerSource": 10,
      "requestTimeoutSeconds": 20,
      "cacheTtlSeconds": 86400,
      "arxiv": {
        "enabled": true,
        "apiBase": "https://export.arxiv.org/api/query",
        "minIntervalSeconds": 3
      },
      "pubmed": {
        "enabled": true,
        "apiBase": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
        "tool": "gm-science",
        "email": "your-email@example.com",
        "apiKey": "",
        "minIntervalSeconds": 0.34
      },
      "openalex": {
        "enabled": true,
        "apiBase": "https://api.openalex.org",
        "apiKey": "your-openalex-api-key"
      }
    }
  }
}
```

- arXiv 不需要密钥。
- PubMed 要求填写联系邮箱；API key 可选。
- OpenAlex 要求填写 API key。
- 单个来源未配置或请求失败时，其他来源仍会继续检索。
- Project 的 `enabledConnectors` 会限制实际可请求来源；显式空列表禁用所有文献来源。只有未提供 Project 策略时才使用 `defaultSources`。
- 搜索结果会跨来源去重，并可保存为 Project 内的 `paper` artifact；综述可登记为 `report` 和 `citation` artifacts。
- citation artifact 包含 CSL JSON metadata，report artifact 保存关联的 paper/citation IDs。

配置文件可能包含密钥，不要提交到 Git 仓库。

## 专家智能体

`science-research` 是唯一直接与用户对话的主智能体。它可以按需调用两个受限专家：

- `paper_reader`：读取已保存的 paper artifacts，生成结构化 `reading_note`。
- `research_reviewer`：检查 `report` 或 `reading_note` 及其关联论文，生成 findings-first 的 `critique_report`。

专家只获得当前 Project 的显式 artifact IDs，不继承主对话内容，也没有 shell、网络或通用写文件工具。网络论文链接不会自动下载；没有 Project 内本地文本时，阅读结果必须标记为 `metadata_abstract`。

配置仍位于 `~/.gm-science/science-research/config.json`：

```json
{
  "science": {
    "projectDefaults": {
      "enabledSkills": ["literature-review"],
      "enabledConnectors": ["arxiv", "pubmed", "openalex"],
      "enabledSpecialists": ["paper_reader", "research_reviewer"]
    },
    "specialists": {
      "enabled": true,
      "model": "",
      "paperReader": {
        "enabled": true,
        "autoDispatch": true,
        "maxPapers": 6,
        "maxSourceChars": 30000
      },
      "reviewer": {
        "enabled": true,
        "autoDispatch": true,
        "reviewGate": "annotate",
        "maxFindings": 20,
        "maxSourceChars": 60000
      }
    }
  }
}
```

- `model` 为空时继承主模型；非空时沿用当前 provider 和凭据，只覆盖模型名。
- `reviewGate` 支持 `off` 和 `annotate`。`annotate` 只评审本轮最新的新 report，失败不会覆盖主回答，也不会自动修改报告或递归复审。
- Project 创建请求未显式传入能力列表时使用 `projectDefaults`；显式空数组会按请求保存，不会被默认值覆盖。connectors 显式空列表会禁用所有文献来源。
- 自动调度适用于论文阅读、比较和明确的评审请求；普通问答和单次来源状态查询不会触发 reviewer gate。

## Project Session

- ADK Session 仍由 openppx SessionService 保存；gm-science 使用独立映射表记录 Session 的 Project 和 Agent 归属。
- 一个 Session 只能属于一个 Project。Project 运行接口会拒绝未归属或归属其他 Project 的 Session。
- 桌面端启动不会自动创建 Session。用户点击 New 或在空 Project 中首次发送任务时，才会创建当前 Project 的 Session。
- Project 会话计数、工作区会话列表和 Recent Sessions 使用同一映射数据源，重启后可恢复。

## 本地 Python Run

Project 工作区的 `Runs` 面板可以提交本地 Python 源码，并查看运行状态、日志、产物、取消和重试操作。运行由 openppx `TaskRun` 统一管理；gm-science 只保存 Project、Session 与 TaskRun 的关联，不维护第二套任务状态。

每次运行都会在当前 Project workspace 下创建独立目录，保存：

- `main.py` 和 `input.json`。
- `stdout.log`、`stderr.log`、合并后的 `run.log` 和 `manifest.json`。
- `outputs/` 中由脚本声明生成的文件。
- 自动登记的源码、日志和输出 Artifacts，metadata 中包含 `task_id` 和 provenance。

脚本可以通过 `GM_SCIENCE_INPUT_PATH` 读取提交的 JSON，通过 `GM_SCIENCE_OUTPUT_DIR` 写入需要登记的输出。JSON 中的 `argv` 数组会作为命令行参数传给脚本。

运行设置位于 `~/.gm-science/science-research/config.json`：

```json
{
  "science": {
    "execution": {
      "enabled": true,
      "pythonExecutable": "",
      "maxConcurrentRuns": 1,
      "defaultTimeoutSeconds": 900,
      "maxSourceChars": 200000,
      "maxLogPreviewChars": 6000
    }
  }
}
```

`pythonExecutable` 为空时使用当前 gm-science runtime 的 Python。当前版本只开放受约束的 Python Run，不开放任意 shell、依赖安装、notebook、GPU、SSH 或远程计算。应用重启后已完成和失败的历史仍可查看；无法重新接管的活动进程会诚实标记为 `lost`，用户可以从保存的源码和输入重试。

## 一键启动

macOS 用户可以直接双击：

- `start-gm-science.command`

命令行用户可以运行：

```bash
./start-gm-science.sh
```

首次启动时，脚本会自动创建 `gm-science-runtime/.venv`，安装后端和桌面端依赖，然后启动本地桌面应用。

本机需要提前安装：

- Python 3.11 或更新版本
- Node.js LTS

默认数据目录是 `~/.gm-science`，本地 client-api 使用 `127.0.0.1:8876`。需要换目录或端口时，可以设置 `GM_SCIENCE_DATA_DIR` 或 `OPENPPX_CLIENT_API_PORT`。

## Development

Backend:

```bash
cd gm-science-runtime
../.venv/bin/python -m pytest tests/test_literature_config.py tests/test_literature_connectors.py tests/test_literature_service.py tests/test_literature_tools.py -q
```

Desktop:

```bash
cd gm-science-desktop
pnpm test
pnpm build
```
