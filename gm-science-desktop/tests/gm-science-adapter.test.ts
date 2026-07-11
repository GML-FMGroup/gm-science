import {
  buildClientApiRunPath,
  buildClientApiSpawnEnv,
  resolveGmScienceDataRoot,
} from "../electron/main/gm-science-adapter-helpers";

describe("gm-science local adapter helpers", () => {
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
