"""Project-scoped local execution support for gm-science."""

from .config import ScienceExecutionConfig, load_execution_config
from .service import ScienceExecutionService

__all__ = ["ScienceExecutionConfig", "ScienceExecutionService", "load_execution_config"]
