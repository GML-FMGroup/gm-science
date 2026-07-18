import {
  bootstrap,
  createGmScienceAnalysis,
  createGmScienceArtifact,
  createGmScienceProject,
  createGmSciencePythonRun,
  createSession,
  listGmScienceCapabilities,
  listGmScienceArtifacts,
  importGmScienceDataset,
  listGmScienceAnalyses,
  listGmScienceDatasets,
  listGmScienceProjects,
  listGmScienceResources,
  listGmScienceRuns,
  loadSession,
  updateGmScienceProjectCapabilities,
  retryGmScienceRun,
  runGmScienceAnalysis,
} from "../app/src/lib/mock-client";

describe("mock client adapter", () => {
  it("returns initial local bootstrap payload", async () => {
    const payload = await bootstrap();
    expect(payload.runtime.target.type).toBe("local");
    expect(payload.agents.length).toBeGreaterThan(0);
    expect(payload.messages.length).toBeGreaterThan(0);
  });

  it("creates an empty session for the selected project", async () => {
    const created = await createSession("builder", "proj_mock_research");
    expect(created.session.agentId).toBe("builder");
    expect(created.session.projectId).toBe("proj_mock_research");

    const loaded = await loadSession(created.session.id);
    expect(loaded.messages).toHaveLength(0);
  });

  it("supports gm-science project and artifact APIs", async () => {
    const created = await createGmScienceProject({
      name: "Local literature review",
      description: "Track a narrow research question.",
      agentContext: "Prefer primary sources.",
    });

    expect(created.project.name).toBe("Local literature review");
    expect(created.project.agentContext).toBe("Prefer primary sources.");

    const projects = await listGmScienceProjects();
    expect(projects.projects.some((project) => project.id === created.project.id)).toBe(true);

    const artifact = await createGmScienceArtifact(created.project.id, {
      type: "paper",
      title: "A relevant paper",
      pathOrUrl: "https://example.test/paper",
      metadata: { source: "manual" },
    });

    expect(artifact.artifact.projectId).toBe(created.project.id);
    const artifacts = await listGmScienceArtifacts(created.project.id);
    expect(artifacts.artifacts).toContainEqual(artifact.artifact);
    const resources = await listGmScienceResources(created.project.id, "paper");
    expect(resources.resources).toContainEqual(
      expect.objectContaining({
        id: `artifact:${artifact.artifact.id}`,
        kind: "artifact",
        displayName: "A relevant paper",
      }),
    );

    const catalog = await listGmScienceCapabilities(created.project.id);
    expect(catalog.items.some((item) => item.id === "pubmed" && item.projectEnabled)).toBe(true);
    expect(catalog.items.find((item) => item.id === "local-analysis")).toMatchObject({
      source: "local",
      version: "0.1.0",
      license: "Private",
      files: ["SKILL.md", "scripts/analyze.py"],
    });
    expect(catalog.items.find((item) => item.id === "mcp:filesystem")).toMatchObject({
      kind: "connector",
      source: "local",
      projectEnabled: false,
      metadata: {
        connector_type: "mcp",
        transport: "stdio",
        command_name: "mcp-filesystem",
      },
    });

    const updated = await updateGmScienceProjectCapabilities(created.project.id, {
      enabledSkills: [],
      enabledConnectors: ["arxiv"],
      enabledSpecialists: ["research_reviewer"],
    });
    expect(updated.project.enabledConnectors).toEqual(["arxiv"]);
    expect(updated.capabilities.find((item) => item.id === "pubmed")?.projectEnabled).toBe(false);
  });

  it("supports gm-science local run APIs", async () => {
    const created = await createGmSciencePythonRun("proj_mock_research", {
      title: "Mock analysis",
      source: "print('ok')",
      sessionId: "builder-session-1",
    });

    expect(created.run.status).toBe("completed");
    const runs = await listGmScienceRuns("proj_mock_research");
    expect(runs.runs).toContainEqual(created.run);

    const retried = await retryGmScienceRun("proj_mock_research", created.run.taskId);
    expect(retried.run.parentTaskId).toBe(created.run.taskId);
  });

  it("supports mock dataset import and review-before-run analysis", async () => {
    const imported = await importGmScienceDataset("proj_mock_research", {
      sourcePath: "/tmp/study.csv",
      title: "Study",
    });
    expect(imported.dataset.profile?.columns).toHaveLength(3);
    expect((await listGmScienceDatasets("proj_mock_research")).datasets).toContainEqual(imported.dataset);

    const draft = await createGmScienceAnalysis("proj_mock_research", {
      objective: "Summarize Study",
      datasetArtifactIds: [imported.dataset.artifactId],
    });
    expect(draft.analysis.status).toBe("draft");
    const executed = await runGmScienceAnalysis("proj_mock_research", draft.analysis.id);
    expect(executed.analysis.status).toBe("completed");
    expect(executed.analysis.run?.kind).toBe("data_analysis");
    expect((await listGmScienceRuns("proj_mock_research")).runs.find(
      (run) => run.taskId === executed.analysis.taskId,
    )?.kind).toBe("data_analysis");
    expect((await listGmScienceAnalyses("proj_mock_research")).analyses).toContainEqual(executed.analysis);
    await expect(runGmScienceAnalysis("proj_mock_research", draft.analysis.id)).rejects.toThrow(
      "already been approved",
    );
  });
});
