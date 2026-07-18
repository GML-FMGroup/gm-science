"""Bounded specialist support for gm-science research projects."""

from .config import (
    CustomSpecialistConfig,
    PaperReaderConfig,
    ProjectCapabilityDefaults,
    ResearchReviewerConfig,
    SpecialistConfig,
    load_specialist_config,
    parse_specialist_config,
)
from .models import (
    ConfiguredSpecialistInput,
    ConfiguredSpecialistOutput,
    PaperReaderInput,
    PaperReaderOutput,
    ReviewerInput,
    ReviewerOutput,
)
from .registry import SpecialistSpec, list_specialist_specs, science_list_specialists

__all__ = [
    "ConfiguredSpecialistInput",
    "ConfiguredSpecialistOutput",
    "CustomSpecialistConfig",
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
