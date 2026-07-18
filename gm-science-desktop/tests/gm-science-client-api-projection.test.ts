import {
  normalizeGmScienceArtifact,
  normalizeGmScienceAnalysis,
  normalizeGmScienceCapability,
  normalizeGmScienceProject,
  normalizeGmScienceDataset,
  normalizeGmScienceRun,
} from "../app/src/lib/client-api-projection";

describe("gm-science client-api projection", () => {
  it("normalizes project payloads from snake_case client-api responses", () => {
    const project = normalizeGmScienceProject({
      id: "proj_123",
      name: "Protein design",
      description: "Shown in project lists.",
      agent_context: "Always cite sources.",
      workspace_path: "/tmp/workspace",
      sessions_count: 2,
      artifacts_count: 5,
      enabled_skills: ["Literature Review"],
      enabled_connectors: ["OpenAlex"],
      enabled_specialists: ["Reviewer"],
      created_at: "2026-07-10T10:00:00.000Z",
      updated_at: "2026-07-10T11:00:00.000Z",
    });

    expect(project).toEqual({
      id: "proj_123",
      name: "Protein design",
      description: "Shown in project lists.",
      agentContext: "Always cite sources.",
      workspacePath: "/tmp/workspace",
      sessionsCount: 2,
      artifactsCount: 5,
      enabledSkills: ["Literature Review"],
      enabledConnectors: ["OpenAlex"],
      enabledSpecialists: ["Reviewer"],
      createdAt: "2026-07-10T10:00:00.000Z",
      updatedAt: "2026-07-10T11:00:00.000Z",
    });
  });

  it("normalizes artifact payloads and preserves metadata", () => {
    const artifact = normalizeGmScienceArtifact({
      id: "art_123",
      project_id: "proj_123",
      session_id: "session-1",
      type: "paper",
      title: "Attention Is All You Need",
      path_or_url: "https://example.test/paper",
      mime_type: "text/html",
      metadata: { source: "manual" },
      provenance: { created_by: "science-research" },
      created_at: "2026-07-10T10:00:00.000Z",
      updated_at: "2026-07-10T11:00:00.000Z",
    });

    expect(artifact).toEqual({
      id: "art_123",
      projectId: "proj_123",
      sessionId: "session-1",
      type: "paper",
      title: "Attention Is All You Need",
      pathOrUrl: "https://example.test/paper",
      mimeType: "text/html",
      metadata: { source: "manual" },
      provenance: { created_by: "science-research" },
      createdAt: "2026-07-10T10:00:00.000Z",
      updatedAt: "2026-07-10T11:00:00.000Z",
    });
  });

  it("normalizes capability status without leaking unknown fields", () => {
    expect(
      normalizeGmScienceCapability({
        id: "pubmed",
        kind: "connector",
        name: "PubMed",
        description: "Biomedical literature",
        available: true,
        default_enabled: true,
        project_enabled: false,
        status: "needs_configuration",
        status_detail: "Set science.literature.pubmed.email.",
        metadata: { source: "built_in" },
        api_key: "must-not-project",
      }),
    ).toEqual({
      id: "pubmed",
      kind: "connector",
      name: "PubMed",
      description: "Biomedical literature",
      available: true,
      defaultEnabled: true,
      projectEnabled: false,
      status: "needs_configuration",
      statusDetail: "Set science.literature.pubmed.email.",
      metadata: { source: "built_in" },
    });
  });

  it("normalizes Project run controls and artifact links", () => {
    expect(
      normalizeGmScienceRun({
        task_id: "task-1",
        project_id: "proj-1",
        session_id: "session-1",
        parent_task_id: "",
        kind: "local_python",
        title: "Analyze",
        status: "running",
        progress_summary: "Loading data",
        terminal_summary: "",
        last_error: "",
        created_at: "2026-07-14T10:00:00Z",
        updated_at: "2026-07-14T10:00:01Z",
        created_at_ms: 10,
        updated_at_ms: 20,
        ended_at_ms: null,
        controls: { can_cancel: true },
        can_retry: false,
        log_preview: "[stdout] Loading data",
        artifact_ids: ["art-code"],
      }),
    ).toEqual({
      taskId: "task-1",
      projectId: "proj-1",
      sessionId: "session-1",
      parentTaskId: "",
      kind: "local_python",
      title: "Analyze",
      status: "running",
      progressSummary: "Loading data",
      terminalSummary: "",
      lastError: "",
      createdAt: "2026-07-14T10:00:00Z",
      updatedAt: "2026-07-14T10:00:01Z",
      createdAtMs: 10,
      updatedAtMs: 20,
      endedAtMs: null,
      canCancel: true,
      canRetry: false,
      logPreview: "[stdout] Loading data",
      artifactIds: ["art-code"],
    });
  });

  it("normalizes dataset profiles and analysis plans", () => {
    const dataset = normalizeGmScienceDataset({
      artifact_id: "art-data",
      project_id: "proj-1",
      title: "Study",
      path: "/workspace/source.csv",
      format: "csv",
      row_count: 3,
      profiled_row_count: 3,
      column_count: 1,
      column_names: ["value"],
      profile_artifact_id: "art-profile",
      profile: {
        version: 1,
        format: "csv",
        row_count: 3,
        profiled_row_count: 3,
        column_count: 1,
        columns: [
          {
            name: "value",
            inferred_type: "number",
            non_null_count: 2,
            missing_count: 1,
            missing_fraction: 0.333333,
            unique_count: 2,
            unique_count_capped: false,
            type_counts: { number: 2 },
            top_values: [{ value: "1", count: 1 }],
            numeric: { count: 2, min: 1, max: 3, mean: 2, standard_deviation: 1.414 },
          },
        ],
        preview: [{ value: 1 }],
        warnings: [],
      },
    });
    expect(dataset?.profile?.columns[0]).toMatchObject({
      name: "value",
      inferredType: "number",
      missingCount: 1,
      numeric: { mean: 2, standardDeviation: 1.414 },
    });

    const analysis = normalizeGmScienceAnalysis({
      id: "analysis-1",
      project_id: "proj-1",
      title: "Analyze",
      objective: "Summarize data",
      dataset_artifact_ids: ["art-data"],
      plan: {
        version: 1,
        objective: "Summarize data",
        operations: ["data_quality"],
        steps: [{ id: "data_quality", title: "Data Quality", description: "Check data." }],
        datasets: [],
        assumptions: ["Missing values are excluded."],
        warnings: [],
      },
      source: "print('ok')",
      task_id: "",
      status: "draft",
      run: null,
      artifact_ids: [],
    });
    expect(analysis).toMatchObject({
      id: "analysis-1",
      status: "draft",
      datasetArtifactIds: ["art-data"],
      source: "print('ok')",
      plan: { operations: ["data_quality"] },
    });
  });
});
