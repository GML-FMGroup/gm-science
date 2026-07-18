import {
  DEFAULT_GM_SCIENCE_CLIENT_API_PORT,
  appendClientApiLogTail,
  buildCreateGmScienceProjectPayload,
  buildClientApiRunPayload,
  buildClientApiRunPath,
  buildClientApiSpawnEnv,
  formatClientApiStartupError,
  isOpenPpxClientApiHealthPayload,
  managedProcessAfterClose,
  resolveClientApiPort,
  resolveGmScienceDataRoot,
} from "../electron/main/gm-science-adapter-helpers";

describe("gm-science local adapter helpers", () => {
  it("uses a gm-science-specific client-api port by default", () => {
    expect(DEFAULT_GM_SCIENCE_CLIENT_API_PORT).toBe(8876);
    expect(resolveClientApiPort({})).toBe(8876);
  });

  it("lets OPENPPX_CLIENT_API_PORT override the default port", () => {
    expect(resolveClientApiPort({ OPENPPX_CLIENT_API_PORT: "9123" })).toBe(9123);
  });

  it("accepts health payloads only from the openppx client-api", () => {
    expect(
      isOpenPpxClientApiHealthPayload({
        ok: true,
        data: { service: "openppx-client-api", state: "healthy" },
      }),
    ).toBe(true);
    expect(isOpenPpxClientApiHealthPayload({ ok: true, data: { service: "claude-science" } })).toBe(false);
    expect(isOpenPpxClientApiHealthPayload({ detail: "invalid bearer token" })).toBe(false);
  });

  it("surfaces the managed client-api stderr when startup fails", () => {
    expect(formatClientApiStartupError("OSError: [Errno 48] Address already in use\n", "")).toBe(
      "Local gm-science client-api failed to start: OSError: [Errno 48] Address already in use",
    );
  });

  it("keeps only a bounded tail of managed client-api output", () => {
    expect(appendClientApiLogTail("12345", "67890", 6)).toBe("567890");
  });

  it("does not clear a replacement process when an older process closes", () => {
    const oldProcess = { id: "old" };
    const newProcess = { id: "new" };

    expect(managedProcessAfterClose(newProcess, oldProcess)).toBe(newProcess);
    expect(managedProcessAfterClose(oldProcess, oldProcess)).toBeNull();
  });

  it("defaults gm-science data to the user's home directory", () => {
    expect(resolveGmScienceDataRoot({}, "/home/researcher")).toBe("/home/researcher/.gm-science");
  });

  it("lets GM_SCIENCE_DATA_DIR override the default local data directory", () => {
    expect(resolveGmScienceDataRoot({ GM_SCIENCE_DATA_DIR: "/tmp/gm-science" }, "/home/researcher")).toBe(
      "/tmp/gm-science",
    );
  });

  it("sets client-api process env for gm-science mode", () => {
    const env = buildClientApiSpawnEnv("/tmp/gm-science", { NODE_ENV: "test" });

    expect(env).toMatchObject({
      NODE_ENV: "test",
      GM_SCIENCE_MODE: "1",
      GM_SCIENCE_DATA_DIR: "/tmp/gm-science",
      OPENPPX_DATA_DIR: "/tmp/gm-science",
    });
  });

  it("uses project run endpoint when sendMessage receives a project id", () => {
    expect(
      buildClientApiRunPath({
        agentId: "science-research",
        sessionId: "session-1",
        projectId: "proj_123",
        text: "Summarize",
      }),
    ).toBe("/api/v1/gm-science/projects/proj_123/sessions/session-1/runs");
  });

  it("builds a compact versioned resource reference run payload", () => {
    expect(
      buildClientApiRunPayload({
        agentId: "science-research",
        sessionId: "session-1",
        projectId: "proj_123",
        text: "Compare",
        resourceRefs: [{ id: "project_file:abc", versionOrHash: "1:20" }],
      }),
    ).toEqual({
      text: "Compare",
      agent_id: "science-research",
      resource_refs: [{ id: "project_file:abc", version_or_hash: "1:20" }],
    });
  });

  it("rejects resource references on a non-Project run", () => {
    expect(() =>
      buildClientApiRunPayload({
        agentId: "writer",
        sessionId: "session-1",
        text: "Compare",
        resourceRefs: [{ id: "project_file:abc", versionOrHash: "1:20" }],
      }),
    ).toThrow("Project resource references require a Project-scoped run");
  });

  it("omits unspecified project capabilities so the runtime can apply config defaults", () => {
    expect(buildCreateGmScienceProjectPayload({ name: "New study" })).toEqual({
      name: "New study",
      description: "",
      agent_context: "",
    });
  });

  it("preserves explicit empty project capability allowlists", () => {
    expect(
      buildCreateGmScienceProjectPayload({
        name: "Minimal study",
        enabledSkills: [],
        enabledConnectors: [],
        enabledSpecialists: [],
      }),
    ).toMatchObject({
      enabled_skills: [],
      enabled_connectors: [],
      enabled_specialists: [],
    });
  });

  it("keeps the original agent run endpoint when no project id is present", () => {
    expect(
      buildClientApiRunPath({
        agentId: "science-research",
        sessionId: "session-1",
        text: "Summarize",
      }),
    ).toBe("/api/v1/agents/science-research/sessions/session-1/runs");
  });
});
