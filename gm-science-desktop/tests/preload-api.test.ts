import { describe, expect, it, vi } from "vitest";
import preloadSource from "../electron/preload/index.cjs?raw";

type PreloadApi = Record<string, (...args: unknown[]) => unknown>;

function loadPreloadApi() {
  let exposedApi: PreloadApi | null = null;
  const invoke = vi.fn((channel: string, ...args: unknown[]) => ({ channel, args }));
  const on = vi.fn();
  const removeListener = vi.fn();

  const fakeRequire = (moduleName: string) => {
    if (moduleName !== "electron") {
      throw new Error(`Unexpected module: ${moduleName}`);
    }
    return {
      contextBridge: {
        exposeInMainWorld: (_name: string, api: PreloadApi) => {
          exposedApi = api;
        },
      },
      ipcRenderer: {
        invoke,
        on,
        removeListener,
      },
    };
  };

  new Function("require", preloadSource)(fakeRequire);

  if (!exposedApi) {
    throw new Error("preload API was not exposed");
  }
  return { api: exposedApi as PreloadApi, invoke };
}

describe("preload API", () => {
  it("exposes gm-science project and artifact methods", () => {
    const { api, invoke } = loadPreloadApi();

    expect(api.createSession("science-research", "proj-1")).toEqual({
      channel: "ppx-client:create-session",
      args: ["science-research", "proj-1"],
    });

    expect(api.listGmScienceProjects()).toEqual({
      channel: "ppx-client:list-gm-science-projects",
      args: [],
    });
    expect(api.createGmScienceProject({ name: "Paper search" })).toEqual({
      channel: "ppx-client:create-gm-science-project",
      args: [{ name: "Paper search" }],
    });
    expect(api.getGmScienceProject("proj-1")).toEqual({
      channel: "ppx-client:get-gm-science-project",
      args: ["proj-1"],
    });
    expect(api.listGmScienceCapabilities("proj-1")).toEqual({
      channel: "ppx-client:list-gm-science-capabilities",
      args: ["proj-1"],
    });
    expect(
      api.updateGmScienceProjectCapabilities("proj-1", {
        enabledSkills: [],
        enabledConnectors: ["arxiv"],
        enabledSpecialists: [],
      }),
    ).toEqual({
      channel: "ppx-client:update-gm-science-project-capabilities",
      args: [
        "proj-1",
        { enabledSkills: [], enabledConnectors: ["arxiv"], enabledSpecialists: [] },
      ],
    });
    expect(api.listGmScienceArtifacts("proj-1")).toEqual({
      channel: "ppx-client:list-gm-science-artifacts",
      args: ["proj-1"],
    });
    expect(api.listGmScienceResources("proj-1", "figure")).toEqual({
      channel: "ppx-client:list-gm-science-resources",
      args: ["proj-1", "figure"],
    });
    expect(api.createGmScienceArtifact("proj-1", { title: "note" })).toEqual({
      channel: "ppx-client:create-gm-science-artifact",
      args: ["proj-1", { title: "note" }],
    });
    expect(api.listGmScienceRuns("proj-1")).toEqual({
      channel: "ppx-client:list-gm-science-runs",
      args: ["proj-1"],
    });
    expect(api.getGmScienceRun("proj-1", "task-1")).toEqual({
      channel: "ppx-client:get-gm-science-run",
      args: ["proj-1", "task-1"],
    });
    expect(api.createGmSciencePythonRun("proj-1", { title: "Run", source: "print(1)" })).toEqual({
      channel: "ppx-client:create-gm-science-python-run",
      args: ["proj-1", { title: "Run", source: "print(1)" }],
    });
    expect(api.cancelGmScienceRun("proj-1", "task-1")).toEqual({
      channel: "ppx-client:cancel-gm-science-run",
      args: ["proj-1", "task-1"],
    });
    expect(api.retryGmScienceRun("proj-1", "task-1")).toEqual({
      channel: "ppx-client:retry-gm-science-run",
      args: ["proj-1", "task-1"],
    });
    expect(api.selectGmScienceDatasetFile()).toEqual({
      channel: "ppx-client:select-gm-science-dataset-file",
      args: [],
    });
    expect(api.listGmScienceDatasets("proj-1")).toEqual({
      channel: "ppx-client:list-gm-science-datasets",
      args: ["proj-1"],
    });
    expect(api.getGmScienceDataset("proj-1", "art-data")).toEqual({
      channel: "ppx-client:get-gm-science-dataset",
      args: ["proj-1", "art-data"],
    });
    expect(api.importGmScienceDataset("proj-1", { sourcePath: "/tmp/data.csv" })).toEqual({
      channel: "ppx-client:import-gm-science-dataset",
      args: ["proj-1", { sourcePath: "/tmp/data.csv" }],
    });
    expect(api.listGmScienceAnalyses("proj-1")).toEqual({
      channel: "ppx-client:list-gm-science-analyses",
      args: ["proj-1"],
    });
    expect(api.getGmScienceAnalysis("proj-1", "analysis-1")).toEqual({
      channel: "ppx-client:get-gm-science-analysis",
      args: ["proj-1", "analysis-1"],
    });
    expect(api.createGmScienceAnalysis("proj-1", { objective: "Analyze", datasetArtifactIds: ["art-data"] })).toEqual({
      channel: "ppx-client:create-gm-science-analysis",
      args: ["proj-1", { objective: "Analyze", datasetArtifactIds: ["art-data"] }],
    });
    expect(api.runGmScienceAnalysis("proj-1", "analysis-1")).toEqual({
      channel: "ppx-client:run-gm-science-analysis",
      args: ["proj-1", "analysis-1"],
    });
    expect(invoke).toHaveBeenCalledTimes(22);
  });
});
