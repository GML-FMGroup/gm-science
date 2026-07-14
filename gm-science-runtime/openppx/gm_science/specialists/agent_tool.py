"""Project policy boundary around Google ADK AgentTool specialists."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.tools.agent_tool import AgentTool
from google.adk.utils._schema_utils import validate_schema
from google.adk.utils.context_utils import Aclosing
from google.genai import types

from ..store import GmScienceStore
from .artifacts import artifact_payload, save_critique_report, save_reading_note
from .config import load_specialist_config
from .models import PaperReaderInput, PaperReaderOutput, ReviewerInput, ReviewerOutput
from .registry import SpecialistSpec
from .tools import science_read_paper_bundle, validate_specialist_artifacts


def child_session_state(_parent_state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return the intentionally empty state used for every specialist run."""

    return {}


class ProjectSpecialistTool(AgentTool):
    """Run a specialist in fresh context after enforcing Project policy."""

    def __init__(self, *, spec: SpecialistSpec, agent: Any) -> None:
        self.spec = spec
        super().__init__(agent=agent, include_plugins=False)

    async def run_async(self, *, args: dict[str, Any], tool_context: Any) -> dict[str, Any]:
        """Validate, run, validate output, and persist one specialist artifact."""

        input_value = self.spec.input_schema.model_validate(args)
        store = GmScienceStore()
        project = store.get_project(input_value.project_id)
        if project is None:
            raise ValueError(f"Project '{input_value.project_id}' was not found.")
        config = load_specialist_config()
        spec_enabled = {
            "paper_reader": config.enabled and config.paper_reader.enabled,
            "research_reviewer": config.enabled and config.reviewer.enabled,
        }.get(self.spec.name, False)
        if not spec_enabled:
            raise ValueError(f"Specialist '{self.spec.name}' is disabled by configuration.")
        if self.spec.name not in project.enabled_specialists:
            raise ValueError(f"Specialist '{self.spec.name}' is not enabled for Project '{project.id}'.")

        evidence_scopes: dict[str, str] = {}
        if isinstance(input_value, PaperReaderInput):
            if len(input_value.paper_artifact_ids) > config.paper_reader.max_papers:
                raise ValueError(
                    f"paper-reader accepts at most {config.paper_reader.max_papers} papers per call."
                )
            validate_specialist_artifacts(
                store,
                project_id=project.id,
                artifact_ids=input_value.paper_artifact_ids,
                allowed_types={"paper"},
            )
            bundle = science_read_paper_bundle(project.id, input_value.paper_artifact_ids)
            evidence_scopes = {
                item["artifact_id"]: item["evidence_scope"] for item in bundle["papers"]
            }
        elif isinstance(input_value, ReviewerInput):
            validate_specialist_artifacts(
                store,
                project_id=project.id,
                artifact_ids=[input_value.target_artifact_id],
                allowed_types={"report", "reading_note"},
            )

        raw_output = await self._run_isolated(input_value, tool_context)
        output = self.spec.output_schema.model_validate(raw_output)
        artifact = self._persist_output(
            store,
            input_value=input_value,
            output=output,
            evidence_scopes=evidence_scopes,
            max_findings=config.reviewer.max_findings,
        )
        return {
            "output": output.model_dump(mode="json"),
            "artifact": artifact_payload(artifact),
        }

    async def _run_isolated(self, input_value: Any, tool_context: Any) -> Any:
        """Run the child with an empty in-memory session and isolated plugins/artifacts."""

        invocation_context = getattr(tool_context, "_invocation_context", None)
        user_id = str(getattr(invocation_context, "user_id", "") or "gm-science-specialist")
        app_name = str(getattr(invocation_context, "app_name", "") or self.agent.name)
        credential_service = getattr(invocation_context, "credential_service", None)
        runner = Runner(
            app_name=app_name,
            agent=self.agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
            credential_service=credential_service,
            plugins=None,
        )
        session = await runner.session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            state=child_session_state(),
        )
        content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=input_value.model_dump_json(exclude_none=True))],
        )
        last_content = None
        try:
            async with Aclosing(
                runner.run_async(user_id=user_id, session_id=session.id, new_message=content)
            ) as events:
                async for event in events:
                    if event.content:
                        last_content = event.content
        finally:
            await runner.close()
        if last_content is None or not last_content.parts:
            raise RuntimeError(f"Specialist '{self.spec.name}' returned no structured output.")
        merged_text = "\n".join(
            part.text
            for part in last_content.parts
            if not part.thought and isinstance(part.text, str) and part.text
        )
        return validate_schema(self.spec.output_schema, merged_text)

    def _persist_output(
        self,
        store: GmScienceStore,
        *,
        input_value: Any,
        output: Any,
        evidence_scopes: dict[str, str],
        max_findings: int,
    ):
        if isinstance(input_value, PaperReaderInput) and isinstance(output, PaperReaderOutput):
            output_ids = [reading.paper_artifact_id for reading in output.readings]
            if set(output_ids) != set(input_value.paper_artifact_ids) or len(output_ids) != len(set(output_ids)):
                raise ValueError("paper-reader output must contain each requested paper exactly once.")
            for reading in output.readings:
                if evidence_scopes.get(reading.paper_artifact_id) != reading.evidence_scope:
                    raise ValueError("paper-reader output changed the host-verified evidence scope.")
            return save_reading_note(
                store,
                project_id=input_value.project_id,
                session_id=input_value.session_id,
                output=output,
                source_artifact_ids=input_value.paper_artifact_ids,
                focus=input_value.focus,
                comparison_question=input_value.comparison_question,
                model_name=_agent_model_name(self.agent),
            )
        if isinstance(input_value, ReviewerInput) and isinstance(output, ReviewerOutput):
            if len(output.findings) > max_findings:
                raise ValueError(f"research-reviewer returned more than {max_findings} findings.")
            return save_critique_report(
                store,
                project_id=input_value.project_id,
                session_id=input_value.session_id,
                output=output,
                target_artifact_id=input_value.target_artifact_id,
                trigger=input_value.trigger,
                review_focus=input_value.review_focus,
                model_name=_agent_model_name(self.agent),
            )
        raise TypeError(f"Specialist '{self.spec.name}' returned an incompatible output schema.")


def _agent_model_name(agent: Any) -> str:
    """Return a stable, non-secret model label for artifact provenance."""

    model = getattr(agent, "model", "")
    if isinstance(model, str):
        return model
    return str(getattr(model, "model", "") or getattr(model, "model_name", "") or type(model).__name__)
