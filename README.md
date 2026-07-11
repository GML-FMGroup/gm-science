# gm-science

`gm-science` is a local-first personal research agent workspace built on top of the existing openppx runtime and desktop client architecture.

## Repository Layout

- `gm-science-runtime/`: Python runtime derived from `open-ppx`, including the gm-science project/artifact store and client-api endpoints.
- `gm-science-desktop/`: Electron + React desktop client derived from `ppx-client`, adapted for the gm-science project workspace UI.
- `docs/`: Project documentation placeholder for repo-local design and implementation notes.

## Local Data

The application stores gm-science project data under `~/.gm-science` by default. Set `GM_SCIENCE_DATA_DIR` to override this location.

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
