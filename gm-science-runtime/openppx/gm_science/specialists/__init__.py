"""Bounded specialist support for gm-science research projects."""

from .config import (
    PaperReaderConfig,
    ProjectCapabilityDefaults,
    ResearchReviewerConfig,
    SpecialistConfig,
    load_specialist_config,
    parse_specialist_config,
)
from .models import PaperReaderInput, PaperReaderOutput, ReviewerInput, ReviewerOutput
from .registry import SpecialistSpec, list_specialist_specs, science_list_specialists

__all__ = [
    "PaperReaderConfig",
    "PaperReaderInput",
    "PaperReaderOutput",
    "ProjectCapabilityDefaults",
    "ResearchReviewerConfig",
    "ReviewerInput",
    "ReviewerOutput",
    "SpecialistConfig",
    "SpecialistSpec",
    "load_specialist_config",
    "list_specialist_specs",
    "parse_specialist_config",
    "science_list_specialists",
]
