"""Structured input and output contracts for gm-science specialists."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SpecialistModel(BaseModel):
    """Strict base model shared by specialist contracts."""

    model_config = ConfigDict(extra="forbid")


class PaperReaderInput(SpecialistModel):
    """Bounded request passed from the research agent to paper-reader."""

    project_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    paper_artifact_ids: list[str] = Field(min_length=1, max_length=20)
    focus: str = ""
    comparison_question: str = ""

    @field_validator("paper_artifact_ids")
    @classmethod
    def _deduplicate_artifact_ids(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if not normalized:
            raise ValueError("At least one paper artifact is required.")
        return normalized


class PaperReading(SpecialistModel):
    """Analysis of one paper constrained to its available evidence scope."""

    paper_artifact_id: str
    title: str
    evidence_scope: Literal["metadata_abstract", "local_text"]
    contribution: str
    methods: list[str]
    results: list[str]
    limitations: list[str]
    reproducibility_clues: list[str]
    confidence: Literal["low", "medium", "high"]


class PaperReaderOutput(SpecialistModel):
    """Structured reading note returned by paper-reader."""

    title: str
    synthesis: str
    readings: list[PaperReading] = Field(min_length=1, max_length=20)
    agreements: list[str]
    conflicts: list[str]
    open_questions: list[str]
    confidence_note: str


class ReviewerInput(SpecialistModel):
    """Bounded request passed from the research agent to reviewer."""

    project_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    target_artifact_id: str = Field(min_length=1)
    review_focus: str = ""
    trigger: Literal["explicit", "gate"] = "explicit"


class ReviewerFinding(SpecialistModel):
    """One actionable, evidence-grounded review finding."""

    severity: Literal["blocking", "major", "minor"]
    category: str
    claim: str
    issue: str
    evidence: str
    recommendation: str


class ReviewerOutput(SpecialistModel):
    """Findings-first critique returned by research-reviewer."""

    title: str
    verdict: Literal["clean", "revise", "flagged"]
    summary: str
    strengths: list[str]
    findings: list[ReviewerFinding] = Field(max_length=100)
    unsupported_claims: list[str]
    missing_evidence: list[str]
    evidence_scopes: list[Literal["metadata_abstract", "local_text"]]
    review_limitations: list[str]
