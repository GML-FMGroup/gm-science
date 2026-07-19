import {
  bootstrap,
  checkGmScienceComputeTarget,
  createGmScienceAnalysis,
  createGmScienceArtifact,
  createGmScienceProject,
  createGmSciencePythonRun,
  createSession,
  getGmScienceSettings,
  getGmScienceResourceDetail,
  getGmScienceSessionPolicy,
  getGmScienceMemory,
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
  updateGmScienceSessionPolicy,
  updateGmScienceSettings,
  createGmScienceMemoryNote,
  updateGmScienceMemoryNote,
  deleteGmScienceMemoryNote,
  clearGmScienceMemory,
  reviewGmScienceMemoryCandidate,
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
    const created = await createSession("science-research", "proj_mock_research");
    expect(created.session.agentId).toBe("science-research");
    expect(created.session.projectId).toBe("proj_mock_research");

    const loaded = await loadSession(created.session.id);
    expect(loaded.messages).toHaveLength(0);
    expect(await getGmScienceSessionPolicy(created.session.id)).toMatchObject({
      delegationEnabled: false,
      autoReviewEnabled: false,
      memoryEnabled: false,
      specialistId: "",
      reviewerModel: "default",
      computeTarget: "local",
    });

    const updated = await updateGmScienceSessionPolicy(created.session.id, {
      delegationEnabled: true,
      specialistId: "paper_reader",
    });
    expect(updated).toMatchObject({ delegationEnabled: true, specialistId: "paper_reader" });
    await expect(updateGmScienceSessionPolicy(created.session.id, { specialistId: "missing" })).rejects.toThrow(
      "is not ready",
    );
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
      pathOrUrl: "https://user:secret@example.test/paper?token=secret#page",
      metadata: { source: "manual", summary: "Relevant evidence.", profile_path: "/private/profile.json" },
      provenance: { created_by: "mock-client", credential: "must-not-leak" },
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
        url: "https://example.test/paper",
      }),
    );
    const detail = await getGmScienceResourceDetail(created.project.id, `artifact:${artifact.artifact.id}`);
    expect(detail.detail).toMatchObject({
      preview: { contentStatus: "external_descriptor_only", content: "" },
      artifact: {
        id: artifact.artifact.id,
        metadata: { summary: "Relevant evidence." },
        provenance: { created_by: "mock-client" },
      },
    });
    expect(JSON.stringify(detail)).not.toContain("/private/profile.json");
    expect(JSON.stringify(detail)).not.toContain("must-not-leak");

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

  it("updates mock settings with explicit secret semantics", async () => {
    const initial = await getGmScienceSettings();
    expect(initial.model.provider).toBe("openai_codex");

    const updated = await updateGmScienceSettings({
      projectId: "proj_mock_research",
      model: { provider: "openai", model: "openai/gpt-5.5" },
      providerApiKey: { operation: "replace", value: "provider-secret" },
      pubmedEmail: "researcher@example.org",
      openalexApiKey: { operation: "replace", value: "openalex-secret" },
      memoryEnabled: false,
    });
    expect(updated.settings.model).toEqual({ provider: "openai", model: "openai/gpt-5.5" });
    expect(updated.settings.providers.find((provider) => provider.id === "openai")).toMatchObject({
      credentialConfigured: true,
      credentialSource: "local_config",
      active: true,
    });
    expect(updated.settings.literature.pubmed.status).toBe("ready");
    expect(updated.settings.literature.openalex.status).toBe("ready");
    expect(updated.settings.memory.enabled).toBe(false);
    expect(updated.capabilities.find((capability) => capability.id === "openalex")?.status).toBe("ready");

    const preserved = await updateGmScienceSettings({ projectId: "proj_mock_research" });
    expect(preserved.settings.providers.find((provider) => provider.id === "openai")?.credentialConfigured).toBe(true);
    const removed = await updateGmScienceSettings({
      projectId: "proj_mock_research",
      providerApiKey: { operation: "remove" },
      openalexApiKey: { operation: "remove" },
    });
    expect(removed.settings.providers.find((provider) => provider.id === "openai")?.credentialConfigured).toBe(false);
    expect(removed.settings.literature.openalex.status).toBe("needs_configuration");
    expect(JSON.stringify(removed)).not.toContain("provider-secret");
    expect(JSON.stringify(removed)).not.toContain("openalex-secret");
  });

  it("keeps infrastructure mock contracts aligned with the local adapter", async () => {
    const updated = await updateGmScienceSettings({
      permissionGrants: { attach_skill: false },
      network: {
        pythonPackageIndex: "https://packages.example.test/simple",
        categoryEnabled: { research_data: false },
        customDomains: ["data.example.test"],
      },
      computeTarget: {
        operation: "upsert",
        target: {
          id: "lab_cluster",
          type: "ssh",
          name: "Lab cluster",
          enabled: true,
          host: "cluster.example.test",
          port: 22,
          username: "researcher",
        },
      },
    });

    expect(updated.settings.permissions.items.find((item) => item.id === "attach_skill")).toMatchObject({
      granted: false,
      source: "user",
    });
    expect(updated.settings.network.packageMirrors.pythonPackageIndex).toBe(
      "https://packages.example.test/simple",
    );
    expect(updated.settings.network.categories.find((item) => item.id === "research_data")?.enabled).toBe(false);
    const remote = updated.settings.compute.targets.find((item) => item.id === "lab_cluster");
    expect(remote).toMatchObject({ configured: true, executable: false, status: "unavailable" });
    expect((await checkGmScienceComputeTarget("local")).executable).toBe(true);

    await updateGmScienceSettings({ permissionGrants: { attach_skill: true } });
    await updateGmScienceSettings({ computeTarget: { operation: "remove", id: "lab_cluster" } });
  });

  it("redacts credentials and query values from mock infrastructure URLs", async () => {
    const result = await updateGmScienceSettings({
      network: {
        condaChannelMirror: "https://user:password@packages.example.test/conda?token=secret",
        pythonPackageIndex: "https://token@packages.example.test/simple?key=secret",
      },
      computeTarget: {
        operation: "upsert",
        target: {
          id: "redacted_endpoint",
          type: "model_endpoint",
          name: "Redacted endpoint",
          enabled: true,
          url: "https://user:password@endpoint.example.test/v1?token=secret",
        },
      },
    });

    expect(result.settings.network.packageMirrors).toEqual({
      condaChannelMirror: "https://packages.example.test/conda",
      pythonPackageIndex: "https://packages.example.test/simple",
      caBundlePath: "",
    });
    const endpoint = result.settings.compute.targets.find((target) => target.id === "redacted_endpoint");
    expect(endpoint?.metadata.url).toBe("https://endpoint.example.test/v1");
    expect(JSON.stringify(result.settings)).not.toContain("password");
    expect(JSON.stringify(result.settings)).not.toContain("token=secret");

    await updateGmScienceSettings({ computeTarget: { operation: "remove", id: "redacted_endpoint" } });
  });

  it("supports reviewed User and Project Memory lifecycle", async () => {
    const projectId = "proj_mock_research";
    const initial = await getGmScienceMemory(projectId);
    const pending = initial.candidates.find((candidate) => candidate.status === "pending");
    expect(pending).toBeDefined();

    const reviewed = await reviewGmScienceMemoryCandidate(projectId, pending!.id, "approve");
    expect(reviewed.status).toBe("approved");
    const afterReview = await getGmScienceMemory(projectId);
    expect(afterReview.notes.find((note) => note.id === reviewed.approvedNoteId)).toMatchObject({
      scope: "project",
      provenance: { candidateId: pending!.id, sessionId: pending!.sourceSessionId },
    });

    const created = await createGmScienceMemoryNote(projectId, {
      scope: "user",
      category: "Preferences",
      text: "Prefer concise summaries.",
    });
    const updated = await updateGmScienceMemoryNote(projectId, created.id, {
      category: "Preferences",
      text: "Prefer concise summaries with uncertainty labels.",
    });
    expect(updated.text).toContain("uncertainty labels");
    await deleteGmScienceMemoryNote(projectId, created.id);
    expect((await getGmScienceMemory(projectId)).notes.some((note) => note.id === created.id)).toBe(false);
    expect(await clearGmScienceMemory(projectId, "project")).toBe(1);
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
