import {
  normalizeGmScienceArtifact,
  normalizeGmScienceAnalysis,
  normalizeGmScienceCapability,
  normalizeGmScienceProject,
  normalizeGmScienceResource,
  normalizeGmScienceResourceDetail,
  normalizeGmScienceDataset,
  normalizeGmScienceRun,
  normalizeGmScienceSessionPolicy,
  normalizeGmScienceSettings,
  normalizeGmScienceMemoryWorkspace,
} from "../app/src/lib/client-api-projection";

describe("gm-science client-api projection", () => {
  it("normalizes public settings without projecting secret fields", () => {
    expect(
      normalizeGmScienceSettings({
        model: { provider: "openai_codex", model: "openai-codex/gpt-5.5" },
        memory: { enabled: true },
        providers: [
          {
            id: "openai_codex",
            name: "OpenAI Codex",
            default_model: "openai-codex/gpt-5.5",
            auth_type: "oauth",
            credential_required: true,
            credential_configured: true,
            credential_source: "oauth_cache",
            active: true,
            access_token: "must-not-project",
          },
        ],
        literature: {
          arxiv: { status: "ready", status_detail: "" },
          pubmed: {
            email: "researcher@example.test",
            api_key_configured: false,
            status: "ready",
            status_detail: "",
            api_key: "must-not-project",
          },
          openalex: {
            api_key_configured: false,
            status: "needs_configuration",
            status_detail: "Add an OpenAlex API key.",
          },
        },
      }),
    ).toEqual({
      model: { provider: "openai_codex", model: "openai-codex/gpt-5.5" },
      memory: { enabled: true },
      providers: [
        {
          id: "openai_codex",
          name: "OpenAI Codex",
          defaultModel: "openai-codex/gpt-5.5",
          authType: "oauth",
          credentialRequired: true,
          credentialConfigured: true,
          credentialSource: "oauth_cache",
          active: true,
        },
      ],
      literature: {
        arxiv: { status: "ready", statusDetail: "" },
        pubmed: {
          email: "researcher@example.test",
          apiKeyConfigured: false,
          status: "ready",
          statusDetail: "",
        },
        openalex: {
          apiKeyConfigured: false,
          status: "needs_configuration",
          statusDetail: "Add an OpenAlex API key.",
        },
      },
    });
  });

  it("normalizes reviewable Memory notes, candidates, and recall usage", () => {
    expect(normalizeGmScienceMemoryWorkspace({
      project_id: "proj-1",
      notes: [{
        id: "note-1",
        scope: "project",
        category: "Project context",
        text: "Use GRCh38.",
        created_at: "2026-07-19T01:00:00Z",
        updated_at: "2026-07-19T01:00:00Z",
        provenance: {
          source: "candidate_review",
          project_id: "proj-1",
          session_id: "session-1",
          model: "openai-codex/gpt-5.5",
          candidate_id: "candidate-1",
          rationale: "Durable convention.",
        },
        usage: {
          count: 2,
          session_ids: ["session-1", "session-2"],
          last_used_at_ms: 123,
        },
      }],
      candidates: [{
        id: "candidate-1",
        scope: "project",
        category: "Project context",
        text: "Use GRCh38.",
        rationale: "Durable convention.",
        status: "approved",
        project_id: "proj-1",
        source_session_id: "session-1",
        model: "openai-codex/gpt-5.5",
        approved_note_id: "note-1",
        created_at: "2026-07-19T01:00:00Z",
        reviewed_at: "2026-07-19T01:01:00Z",
      }],
      categories: ["Project context"],
    })).toMatchObject({
      projectId: "proj-1",
      notes: [{
        id: "note-1",
        scope: "project",
        provenance: { candidateId: "candidate-1", sessionId: "session-1" },
        usage: { count: 2, sessionIds: ["session-1", "session-2"], lastUsedAtMs: 123 },
      }],
      candidates: [{ id: "candidate-1", status: "approved", approvedNoteId: "note-1" }],
      categories: ["Project context"],
    });
    expect(normalizeGmScienceMemoryWorkspace({
      notes: [{ scope: "global" }],
      candidates: [],
    })).toBeNull();
  });

  it("rejects malformed public settings enumerations", () => {
    expect(
      normalizeGmScienceSettings({
        model: { provider: "openai", model: "gpt-5.5" },
        providers: [{ id: "openai", auth_type: "password", credential_source: "keychain" }],
        literature: {},
      }),
    ).toBeNull();
  });

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
      session_policy_defaults: {
        delegation_enabled: true,
        auto_review_enabled: false,
        memory_enabled: true,
        specialist_id: "paper_reader",
        reviewer_model: "default",
        compute_target: "local",
      },
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
      sessionPolicyDefaults: {
        delegationEnabled: true,
        autoReviewEnabled: false,
        memoryEnabled: true,
        specialistId: "paper_reader",
        reviewerModel: "default",
        computeTarget: "local",
      },
      createdAt: "2026-07-10T10:00:00.000Z",
      updatedAt: "2026-07-10T11:00:00.000Z",
    });
  });

  it("normalizes Session policy candidates and rejects unsupported targets", () => {
    expect(normalizeGmScienceSessionPolicy({
      session_id: "session-1",
      project_id: "proj-1",
      delegation_enabled: true,
      auto_review_enabled: false,
      memory_enabled: true,
      specialist_id: "paper_reader",
      reviewer_model: "default",
      compute_target: "local",
      specialists: [{ id: "paper_reader", name: "Paper Reader", description: "Read papers", status: "ready" }],
      reviewer_available: true,
      reviewer_models: [{ id: "default", name: "Default" }],
      compute_targets: [{ id: "local", name: "Local" }],
      issues: [],
    })).toEqual({
      sessionId: "session-1",
      projectId: "proj-1",
      delegationEnabled: true,
      autoReviewEnabled: false,
      memoryEnabled: true,
      specialistId: "paper_reader",
      reviewerModel: "default",
      computeTarget: "local",
      specialists: [{ id: "paper_reader", name: "Paper Reader", description: "Read papers", status: "ready" }],
      reviewerAvailable: true,
      reviewerModels: [{ id: "default", name: "Default" }],
      computeTargets: [{ id: "local", name: "Local" }],
      issues: [],
    });
    expect(normalizeGmScienceSessionPolicy({
      reviewer_model: "other",
      compute_target: "remote",
      specialists: [],
      reviewer_models: [],
      compute_targets: [],
    })).toBeNull();
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

  it("normalizes path-safe Project resource references", () => {
    expect(
      normalizeGmScienceResource({
        id: "artifact:art_123",
        kind: "run_output",
        project_id: "proj_123",
        session_id: "session-1",
        display_name: "Result figure",
        artifact_type: "figure",
        mime_type: "image/png",
        version_or_hash: "sha-123",
        access_mode: "read",
        source: "artifact",
        artifact_id: "art_123",
        relative_path: "runs/run-1/outputs/result.png",
        url: "",
        size_bytes: 2048,
        created_at: "2026-07-10T10:00:00.000Z",
        updated_at: "2026-07-10T11:00:00.000Z",
        metadata: { task_id: "task-1" },
        path_or_url: "/must/not/project",
      }),
    ).toEqual({
      id: "artifact:art_123",
      kind: "run_output",
      projectId: "proj_123",
      sessionId: "session-1",
      displayName: "Result figure",
      artifactType: "figure",
      mimeType: "image/png",
      versionOrHash: "sha-123",
      accessMode: "read",
      source: "artifact",
      artifactId: "art_123",
      relativePath: "runs/run-1/outputs/result.png",
      url: "",
      sizeBytes: 2048,
      createdAt: "2026-07-10T10:00:00.000Z",
      updatedAt: "2026-07-10T11:00:00.000Z",
      metadata: { task_id: "task-1" },
    });
    expect(normalizeGmScienceResource({ id: "bad", kind: "secret_file" })).toBeNull();
  });

  it("normalizes bounded resource detail, provenance, and relations", () => {
    const detail = normalizeGmScienceResourceDetail({
      resource: {
        id: "artifact:art_123",
        kind: "artifact",
        project_id: "proj_123",
        session_id: "session-1",
        display_name: "Summary report",
        artifact_type: "report",
        mime_type: "text/markdown",
        version_or_hash: "sha-123",
        access_mode: "read",
        source: "artifact",
        artifact_id: "art_123",
        relative_path: "reports/summary.md",
        url: "",
        size_bytes: 128,
        created_at: "2026-07-10T10:00:00.000Z",
        updated_at: "2026-07-10T11:00:00.000Z",
        metadata: {},
      },
      preview: {
        content: "# Summary\n",
        content_status: "included",
        content_included: true,
        content_chars: 10,
        truncated: false,
      },
      artifact: {
        id: "art_123",
        session_id: "session-1",
        type: "report",
        title: "Summary report",
        mime_type: "text/markdown",
        metadata: { paper_artifact_ids: ["art_paper"] },
        provenance: { created_by: "literature_review", model: "openai-codex/gpt-5.5" },
        created_at: "2026-07-10T10:00:00.000Z",
        updated_at: "2026-07-10T11:00:00.000Z",
      },
      relations: [
        {
          artifact_id: "art_paper",
          resource_id: "artifact:art_paper",
          session_id: "",
          title: "Evidence paper",
          artifact_type: "paper",
          relation: "paper",
          direction: "outgoing",
        },
      ],
    });

    expect(detail).toMatchObject({
      preview: { contentStatus: "included", contentChars: 10 },
      artifact: { id: "art_123", sessionId: "session-1" },
      relations: [{ resourceId: "artifact:art_paper", direction: "outgoing" }],
    });
    expect(normalizeGmScienceResourceDetail({
      resource: detail?.resource,
      preview: { content_status: "unsafe" },
      relations: [],
      artifact: null,
    })).toBeNull();
  });

  it("normalizes capability status without leaking unknown fields", () => {
    expect(
      normalizeGmScienceCapability({
        id: "pubmed",
        kind: "connector",
        name: "PubMed",
        description: "Biomedical literature",
        source: "built_in",
        version: "2026.7",
        license: "",
        files: [],
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
      source: "built_in",
      version: "2026.7",
      license: "",
      files: [],
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
