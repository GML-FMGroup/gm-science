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

## Skills

gm-science 的 Skills 设置页直接读取 openppx `SkillRegistry`，不再维护单独的静态 Skill 清单。它会显示随 runtime 提供的内置 Skills，以及当前 `science-research` agent 的本地 Skills。

本地 Skill 放在：

```text
~/.gm-science/science-research/skills/<skill-id>/SKILL.md
```

添加或修改后，在 Project 的 `Customize > Skills` 页面点击 Refresh。页面支持按名称、ID、说明和来源搜索，并展示来源、版本、许可和相对文件清单；client-api 不返回 Skill 的本机绝对路径。

- Skill 目录名是 Project `enabledSkills` 中保存的稳定 ID。
- 内置 Skill 与本地 Skill 同名时以内置版本为准，避免本地文件静默覆盖运行时行为。
- `version` 和 `license` 来自 `SKILL.md` frontmatter；未声明时页面会明确显示未声明。
- 当前支持发现和附加本地 Skill，不包含 GitHub marketplace 安装、升级或依赖安装流程。

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

## 数据集与 Data Analyst

Project 工作区的 `Data` 面板支持导入 UTF-8 编码的 CSV、TSV、JSON、JSONL 和 NDJSON。源文件会先复制到当前 Project workspace，再生成：

- `dataset` Artifact：保存 Project 内副本、SHA-256、行列数和 schema 摘要。
- `dataset_profile` Artifact：保存类型推断、缺失值、常见值、数值摘要、预览和 profiling 警告。
- 可审阅的 Analysis draft：自然语言目标会被编译成明确步骤和独立 Python 源码，创建草案时不会启动 TaskRun。
- Analysis outputs：用户点击 `Approve & run` 后才创建 `data_analysis` TaskRun，并登记分析报告、JSON 摘要和 SVG 图表。

CSV/TSV 的空列名与重复列名会确定性规范化，超出表头的额外字段会被截断；导入画像和批准后的分析使用同一套读取语义。Markdown 报告会直接呈现描述统计、IQR 异常值、Pearson 相关、描述性分组比较和图表引用，JSON 摘要保留结构化完整结果。

内置确定性分析支持数据质量、描述统计、直方图、IQR 异常值、Pearson 相关和描述性分组比较。回归、显著性检验、因果和生存分析不会伪装成已完成，而会在草案中提示使用经过审阅的自定义 Python Run。

主智能体可以调用 `science_list_datasets` 和 `science_plan_data_analysis` 生成草案，但没有“直接运行分析”的模型工具；执行审批只在 Data 面板中完成。

相关设置位于 `~/.gm-science/science-research/config.json`：

```json
{
  "science": {
    "data": {
      "enabled": true,
      "maxFileSizeBytes": 100000000,
      "profileRowLimit": 50000,
      "previewRows": 20,
      "maxColumns": 200,
      "topValuesLimit": 10
    },
    "analysis": {
      "enabled": true,
      "maxDatasets": 3,
      "maxObjectiveChars": 4000,
      "maxNumericColumns": 20,
      "maxGroupCategories": 20
    }
  }
}
```

当前基础版本不读取 Excel、Parquet、HDF5，不自动安装 pandas/scipy，也不自动运行统计推断。导入大小和 profiling 行数分别受配置限制；总行数仍会完整计数。

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
