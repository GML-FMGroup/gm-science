# gm-science

`gm-science` is a local-first personal research agent workspace built on top of the existing openppx runtime and desktop client architecture.

## Repository Layout

- `gm-science-runtime/`: Python runtime derived from `open-ppx`, including the gm-science project/artifact store and client-api endpoints.
- `gm-science-desktop/`: Electron + React desktop client derived from `ppx-client`, adapted for the gm-science project workspace UI.
- `docs/`: Project documentation placeholder for repo-local design and implementation notes.

## Local Data

The application stores gm-science project data under `~/.gm-science` by default. Set `GM_SCIENCE_DATA_DIR` to override this location.

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
../.venv/bin/python -m pytest tests/test_gm_science_store.py tests/test_gm_science_bootstrap.py tests/test_gm_science_client_api.py -q
```

Desktop:

```bash
cd gm-science-desktop
pnpm test
pnpm build
```
