"""Subprocess wrapper that persists Python run logs and output manifests."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import mimetypes
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import IO, Any


def _iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _pump(
    source: IO[str],
    destination: IO[str],
    console: IO[str],
    combined: IO[str],
    label: str,
    lock: threading.Lock,
) -> None:
    """Copy one child stream to durable and live destinations."""

    for line in iter(source.readline, ""):
        destination.write(line)
        destination.flush()
        console.write(line)
        console.flush()
        with lock:
            combined.write(f"[{label}] {line}")
            combined.flush()


def _output_manifest(output_dir: Path) -> list[dict[str, Any]]:
    """Return stable metadata for files created in the declared output directory."""

    items: list[dict[str, Any]] = []
    for path in sorted(item for item in output_dir.rglob("*") if item.is_file() and not item.is_symlink()):
        relative = path.relative_to(output_dir).as_posix()
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        items.append({"relative_path": relative, "media_type": media_type, "size_bytes": path.stat().st_size})
    return items


def run_python_source(run_dir: Path, timeout_seconds: int) -> int:
    """Execute the saved source file and persist logs plus a terminal manifest."""

    source_path = run_dir / "main.py"
    input_path = run_dir / "input.json"
    output_dir = run_dir / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = json.loads(input_path.read_text(encoding="utf-8")) if input_path.exists() else {}
    raw_argv = payload.get("argv") if isinstance(payload, dict) else []
    argv = [str(item) for item in raw_argv] if isinstance(raw_argv, list) else []
    manifest_path = run_dir / "manifest.json"
    started_at = _iso_now()
    _write_json(
        manifest_path,
        {"status": "running", "exit_code": None, "started_at": started_at, "ended_at": None, "outputs": []},
    )
    env = os.environ.copy()
    env["GM_SCIENCE_INPUT_PATH"] = str(input_path)
    env["GM_SCIENCE_OUTPUT_DIR"] = str(output_dir)
    command = [sys.executable, "-u", str(source_path), *argv]
    status = "failed"
    exit_code = 1
    error = ""
    lock = threading.Lock()
    with (
        (run_dir / "stdout.log").open("w", encoding="utf-8") as stdout_log,
        (run_dir / "stderr.log").open("w", encoding="utf-8") as stderr_log,
        (run_dir / "run.log").open("w", encoding="utf-8") as combined_log,
    ):
        process = subprocess.Popen(
            command,
            cwd=run_dir,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None and process.stderr is not None
        stdout_thread = threading.Thread(
            target=_pump,
            args=(process.stdout, stdout_log, sys.stdout, combined_log, "stdout", lock),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=_pump,
            args=(process.stderr, stderr_log, sys.stderr, combined_log, "stderr", lock),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()
        try:
            exit_code = process.wait(timeout=max(1, timeout_seconds))
            status = "completed" if exit_code == 0 else "failed"
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            exit_code = 124
            error = f"Python run exceeded the {timeout_seconds}-second timeout."
            stderr_log.write(error + "\n")
            stderr_log.flush()
            sys.stderr.write(error + "\n")
            sys.stderr.flush()
        finally:
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)
    _write_json(
        manifest_path,
        {
            "status": status,
            "exit_code": exit_code,
            "error": error,
            "started_at": started_at,
            "ended_at": _iso_now(),
            "outputs": _output_manifest(output_dir),
        },
    )
    return exit_code


def main() -> int:
    """Run the gm-science local Python wrapper from command-line arguments."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--timeout-seconds", type=int, required=True)
    args = parser.parse_args()
    return run_python_source(Path(args.run_dir).resolve(strict=True), args.timeout_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
