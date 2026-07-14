import {
  normalizeGmScienceArtifact,
  normalizeGmScienceCapability,
  normalizeGmScienceProject,
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
});
