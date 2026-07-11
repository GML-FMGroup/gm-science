"""Path helpers for gm-science local data."""

from __future__ import annotations

import os
from pathlib import Path

GM_SCIENCE_DATA_DIR_ENV = "GM_SCIENCE_DATA_DIR"


def get_gm_science_data_dir() -> Path:
    """Return the gm-science local data directory."""

    configured = os.getenv(GM_SCIENCE_DATA_DIR_ENV, "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".gm-science"
