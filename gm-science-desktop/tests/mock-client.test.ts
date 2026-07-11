import {
  bootstrap,
  createGmScienceArtifact,
  createGmScienceProject,
  createSession,
  listGmScienceArtifacts,
  listGmScienceProjects,
  loadSession,
} from "../app/src/lib/mock-client";

describe("mock client adapter", () => {
  it("returns initial local bootstrap payload", async () => {
    const payload = await bootstrap();
    expect(payload.runtime.target.type).toBe("local");
    expect(payload.agents.length).toBeGreaterThan(0);
    expect(payload.messages.length).toBeGreaterThan(0);
  });

  it("creates an empty session for the selected agent", async () => {
    const created = await createSession("builder");
    expect(created.session.agentId).toBe("builder");

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
  });
});
