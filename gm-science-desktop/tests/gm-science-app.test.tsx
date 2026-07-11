import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { App } from "../app/src/App";
import type {
  BootstrapPayload,
  ClientDiagnostics,
  GmScienceProject,
  PpxClientApi,
  RuntimeStatus,
  SessionSummary,
} from "../app/src/types";

function runtime(): RuntimeStatus {
  return {
    target: { id: "local-default", type: "local", name: "This Mac" },
    state: "healthy",
    summary: "ready",
    detail: "detail",
  };
}

function session(): SessionSummary {
  return {
    id: "session-a",
    agentId: "science-research",
    title: "New local session",
    updatedAt: "2026-07-10T10:00:00.000Z",
    lastMessagePreview: "",
  };
}

function project(overrides: Partial<GmScienceProject> = {}): GmScienceProject {
  return {
    id: "proj_123",
    name: "Protein design",
    description: "Binder discovery",
    agentContext: "Always cite sources.",
    workspacePath: "/tmp/gm-science/proj_123",
    sessionsCount: 0,
    artifactsCount: 0,
    enabledSkills: ["Literature Review"],
    enabledConnectors: ["OpenAlex"],
    enabledSpecialists: ["Reviewer"],
    createdAt: "2026-07-10T10:00:00.000Z",
    updatedAt: "2026-07-10T10:00:00.000Z",
    ...overrides,
  };
}

function bootstrapPayload(): BootstrapPayload {
  return {
    runtime: runtime(),
    agents: [
      {
        id: "science-research",
        name: "science-research",
        description: "Local science agent",
        enabled: true,
        status: "healthy",
        tags: ["local"],
      },
    ],
    sessions: [session()],
    messages: [],
    selectedAgentId: "science-research",
    selectedSessionId: "session-a",
  };
}

function diagnostics(): ClientDiagnostics {
  return {
    mode: "local",
    target: { id: "local-default", type: "local", name: "This Mac" },
    openppxRoot: "/tmp/gm-science-runtime",
    openppxRootExists: true,
    pythonBin: "/tmp/gm-science-runtime/.venv/bin/python",
    globalConfigPath: "/tmp/.gm-science/global_config.json",
    globalConfigExists: true,
    clientApiBaseUrl: "http://127.0.0.1:8765",
    clientApiManagedByClient: true,
    clientApiHealthy: true,
    clientApiProcessRunning: true,
    bridgeScriptPath: "/tmp/gm-science-desktop/scripts/openppx_bridge.py",
    bridgeScriptExists: true,
    agentCount: 1,
    sessionCacheEntries: 1,
    messageCacheEntries: 1,
    debugEnabled: false,
  };
}

function installClient(overrides: Partial<PpxClientApi> = {}): PpxClientApi {
  const client: PpxClientApi = {
    bootstrap: async () => bootstrapPayload(),
    getDiagnostics: async () => diagnostics(),
    saveConnectionSettings: async () => diagnostics(),
    runRuntimeCommand: async () => runtime(),
    listSessions: async () => ({ sessions: [session()] }),
    createSession: async () => ({ session: session() }),
    loadSession: async () => ({ messages: [] }),
    sendMessage: async () => ({ runId: "run-1" }),
    listGmScienceProjects: async () => ({ projects: [project()] }),
    createGmScienceProject: async (input) => ({ project: project({ id: "proj_new", name: input.name }) }),
    getGmScienceProject: async (projectId) => ({ project: project({ id: projectId }) }),
    listGmScienceArtifacts: async () => ({ artifacts: [] }),
    createGmScienceArtifact: async (projectId, input) => ({
      artifact: {
        id: "art-test",
        projectId,
        sessionId: input.sessionId ?? "",
        type: input.type,
        title: input.title,
        pathOrUrl: input.pathOrUrl ?? "",
        mimeType: input.mimeType ?? "",
        metadata: input.metadata ?? {},
        provenance: input.provenance ?? {},
        createdAt: "2026-07-10T10:00:00.000Z",
        updatedAt: "2026-07-10T10:00:00.000Z",
      },
    }),
    onRunEvent: () => () => undefined,
    ...overrides,
  };
  window.ppxClient = client;
  return client;
}

describe("gm-science App", () => {
  it("renders the Projects home", async () => {
    installClient();

    render(<App />);

    await screen.findByText("gm-science");
    expect(screen.getByRole("button", { name: /Protein design/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /\+ New project/ })).toBeInTheDocument();
  });

  it("creates a project from the New Project dialog and opens the workspace", async () => {
    const createGmScienceProject = vi.fn(async (input) => ({
      project: project({ id: "proj_new", name: input.name, description: input.description ?? "" }),
    }));
    installClient({
      listGmScienceProjects: async () => ({ projects: [] }),
      createGmScienceProject,
    });

    render(<App />);

    await screen.findByText("No projects yet");
    fireEvent.click(screen.getAllByRole("button", { name: /\+ New project/ })[0]);
    fireEvent.change(screen.getByPlaceholderText("Project name"), { target: { value: "Genome notes" } });
    fireEvent.change(screen.getByPlaceholderText("Describe what this project is about..."), {
      target: { value: "Cell line literature" },
    });
    fireEvent.change(screen.getByPlaceholderText("e.g., Always use GRCh38 for genome references..."), {
      target: { value: "Always use GRCh38." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => {
      expect(createGmScienceProject).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "Genome notes",
          description: "Cell line literature",
          agentContext: "Always use GRCh38.",
        }),
      );
    });
    await screen.findByText("Genome notes is ready");
  });

  it("sends project-scoped messages from the workspace", async () => {
    const sendMessage = vi.fn(async () => ({ runId: "run-1" }));
    installClient({ sendMessage });

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /Protein design/ }));
    await screen.findByText("Protein design is ready");
    fireEvent.change(screen.getByPlaceholderText("向本地 agent 发送任务..."), {
      target: { value: "Summarize the new papers" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => {
      expect(sendMessage).toHaveBeenCalledWith({
        agentId: "science-research",
        sessionId: "session-a",
        projectId: "proj_123",
        text: "Summarize the new papers",
      });
    });
  });
});
