#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$ROOT_DIR/gm-science-runtime"
DESKTOP_DIR="$ROOT_DIR/gm-science-desktop"
VENV_DIR="${GM_SCIENCE_VENV_DIR:-$RUNTIME_DIR/.venv}"
DATA_DIR="${GM_SCIENCE_DATA_DIR:-$HOME/.gm-science}"
CLIENT_API_PORT="${OPENPPX_CLIENT_API_PORT:-8876}"
PYTHON_BIN="$VENV_DIR/bin/python"
PYPROJECT_FILE="$RUNTIME_DIR/pyproject.toml"
BACKEND_STAMP="$VENV_DIR/.gm-science-runtime-installed"
FRONTEND_STAMP="$DESKTOP_DIR/node_modules/.modules.yaml"
DRY_RUN=0
DESKTOP_JOB_PID=""

log() {
  printf "\033[1;34m[gm-science]\033[0m %s\n" "$*"
}

warn() {
  printf "\033[1;33m[gm-science]\033[0m %s\n" "$*" >&2
}

fail() {
  printf "\033[1;31m[gm-science]\033[0m %s\n" "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
gm-science 一键启动器

用法：
  ./start-gm-science.sh
  ./start-gm-science.sh --dry-run

环境变量：
  GM_SCIENCE_DATA_DIR        修改默认数据目录（默认 ~/.gm-science）
  GM_SCIENCE_VENV_DIR        修改 Python 虚拟环境目录
  OPENPPX_CLIENT_API_PORT    修改本地 client-api 端口（默认 8876）
  GM_SCIENCE_REFRESH_DEPS=1  强制重新安装后端和前端依赖
EOF
}

for arg in "$@"; do
  case "$arg" in
    --dry-run)
      DRY_RUN=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "未知参数：$arg"
      ;;
  esac
done

require_dir() {
  local path="$1"
  local label="$2"
  if [ ! -d "$path" ]; then
    fail "$label not found: $path"
  fi
}

python_is_supported() {
  "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1
}

find_python() {
  local candidates=()
  if [ -n "${PYTHON:-}" ]; then
    candidates+=("$PYTHON")
  fi
  candidates+=(python3.14 python3.13 python3.12 python3.11 python3 python)

  local candidate
  for candidate in "${candidates[@]}"; do
    if command -v "$candidate" >/dev/null 2>&1 && python_is_supported "$candidate"; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

run_pnpm() {
  if command -v pnpm >/dev/null 2>&1; then
    pnpm "$@"
    return
  fi

  if command -v corepack >/dev/null 2>&1; then
    corepack pnpm "$@"
    return
  fi

  if command -v npx >/dev/null 2>&1; then
    npx --yes pnpm@10.30.3 "$@"
    return
  fi

  fail "检测到 Node.js，但没有找到 pnpm/corepack/npx。请安装 Node.js LTS 后重新运行。"
}

stop_desktop_process_group() {
  local pid="${DESKTOP_JOB_PID:-}"
  if [ -z "$pid" ]; then
    return
  fi

  if kill -0 "$pid" >/dev/null 2>&1; then
    kill -TERM -- "-$pid" >/dev/null 2>&1 || kill -TERM "$pid" >/dev/null 2>&1 || true
  fi
  wait "$pid" >/dev/null 2>&1 || true
  DESKTOP_JOB_PID=""
}

handle_desktop_interrupt() {
  stop_desktop_process_group
  exit 130
}

handle_desktop_termination() {
  stop_desktop_process_group
  exit 143
}

backend_runtime_ready() {
  "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import openppx
import sqlalchemy
from google.adk.sessions import DatabaseSessionService
PY
}

install_backend_deps() {
  log "正在安装后端依赖。首次运行可能需要几分钟。"
  "$PYTHON_BIN" -m pip install -e "$RUNTIME_DIR"
  mkdir -p "$(dirname "$BACKEND_STAMP")"
  date > "$BACKEND_STAMP"
}

prepare_backend() {
  if [ -x "$PYTHON_BIN" ]; then
    log "使用 Python 虚拟环境：$VENV_DIR"
  else
    local base_python
    base_python="$(find_python)" || fail "没有找到 Python 3.11+。请先安装 Python 3.11 或更新版本。"
    log "正在创建 Python 虚拟环境：$base_python"
    "$base_python" -m venv "$VENV_DIR"
  fi

  "$PYTHON_BIN" -m ensurepip --upgrade >/dev/null 2>&1 || true

  if [ "${GM_SCIENCE_REFRESH_DEPS:-0}" = "1" ] || [ ! -f "$BACKEND_STAMP" ] || [ "$PYPROJECT_FILE" -nt "$BACKEND_STAMP" ]; then
    install_backend_deps
  fi

  if backend_runtime_ready; then
    log "后端依赖已就绪。"
    return
  fi

  warn "后端依赖自检失败，正在重新安装依赖。"
  install_backend_deps
  backend_runtime_ready || fail "后端依赖仍不可用。请检查 Python/pip 输出后重试。"
  log "后端依赖已修复。"
}

prepare_frontend() {
  if ! command -v node >/dev/null 2>&1; then
    fail "没有找到 Node.js。请先从 https://nodejs.org 安装 Node.js LTS。"
  fi

  if [ "${GM_SCIENCE_REFRESH_DEPS:-0}" = "1" ] || [ ! -f "$FRONTEND_STAMP" ] || [ "$DESKTOP_DIR/pnpm-lock.yaml" -nt "$FRONTEND_STAMP" ]; then
    log "正在安装桌面端依赖。首次运行可能需要几分钟。"
    (cd "$DESKTOP_DIR" && run_pnpm install)
  else
    log "桌面端依赖已就绪。"
  fi
}

start_desktop() {
  mkdir -p "$DATA_DIR"

  export OPENPPX_ROOT="$RUNTIME_DIR"
  export GM_SCIENCE_MODE=1
  export GM_SCIENCE_DATA_DIR="$DATA_DIR"
  export OPENPPX_DATA_DIR="$DATA_DIR"
  export OPENPPX_CLIENT_API_PORT="$CLIENT_API_PORT"
  export OPENPPX_CLIENT_API_BASE_URL="http://127.0.0.1:$CLIENT_API_PORT"

  log "数据目录：$DATA_DIR"
  log "本地 client-api：http://127.0.0.1:$CLIENT_API_PORT"
  log "正在启动 gm-science 桌面端。关闭应用或在此窗口按 Ctrl+C 可以停止。"

  # Give the desktop process and every managed child one process group so a
  # launcher interrupt cannot orphan Electron or its local client-api.
  set -m
  (cd "$DESKTOP_DIR" && run_pnpm dev) &
  DESKTOP_JOB_PID=$!
  trap handle_desktop_interrupt INT
  trap handle_desktop_termination TERM
  trap stop_desktop_process_group EXIT

  local status=0
  wait "$DESKTOP_JOB_PID" || status=$?
  DESKTOP_JOB_PID=""
  trap - INT TERM EXIT
  set +m
  return "$status"
}

require_dir "$RUNTIME_DIR" "gm-science runtime 目录"
require_dir "$DESKTOP_DIR" "gm-science desktop 目录"

if [ "$DRY_RUN" = "1" ]; then
  log "dry-run 检查通过。"
  log "仓库目录：$ROOT_DIR"
  log "后端目录：$RUNTIME_DIR"
  log "桌面端目录：$DESKTOP_DIR"
  log "Python 虚拟环境：$VENV_DIR"
  log "数据目录：$DATA_DIR"
  log "本地 client-api 端口：$CLIENT_API_PORT"
  exit 0
fi

prepare_backend
prepare_frontend
start_desktop
