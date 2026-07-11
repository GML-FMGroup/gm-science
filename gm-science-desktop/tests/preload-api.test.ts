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
    expect(api.listGmScienceArtifacts("proj-1")).toEqual({
      channel: "ppx-client:list-gm-science-artifacts",
      args: ["proj-1"],
    });
    expect(api.createGmScienceArtifact("proj-1", { title: "note" })).toEqual({
      channel: "ppx-client:create-gm-science-artifact",
      args: ["proj-1", { title: "note" }],
    });
    expect(invoke).toHaveBeenCalledTimes(5);
  });
});
