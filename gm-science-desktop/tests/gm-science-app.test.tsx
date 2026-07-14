import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { App } from "../app/src/App";
import type {
  BootstrapPayload,
  ClientDiagnostics,
  GmScienceArtifact,
  GmScienceCapability,
  GmScienceProject,
  PpxClientApi,
  RunEvent,
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
    enabledSkills: ["literature-review"],
    enabledConnectors: ["arxiv", "pubmed", "openalex"],
    enabledSpecialists: ["paper_reader", "research_reviewer"],
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
    clientApiBaseUrl: "http://127.0.0.1:8876",
    clientApiManagedByClient: true,
    clientApiHealthy: true,
    clientApiProcessRunning: true,
    agentCount: 1,
    sessionCacheEntries: 1,
    messageCacheEntries: 1,
    debugEnabled: false,
  };
}

function capabilities(projectValue: GmScienceProject = project()): GmScienceCapability[] {
  const definitions: Array<Pick<GmScienceCapability, "id" | "kind" | "name" | "description" | "status">> = [
    { id: "literature-review", kind: "skill", name: "Literature Review", description: "Review papers", status: "ready" },
    { id: "arxiv", kind: "connector", name: "arXiv", description: "Search preprints", status: "ready" },
    { id: "pubmed", kind: "connector", name: "PubMed", description: "Search biomedical papers", status: "needs_configuration" },
    { id: "openalex", kind: "connector", name: "OpenAlex", description: "Search scholarly works", status: "needs_configuration" },
    { id: "paper_reader", kind: "specialist", name: "Paper Reader", description: "Read papers", status: "ready" },
    { id: "research_reviewer", kind: "specialist", name: "Research Reviewer", description: "Review reports", status: "ready" },
  ];
  return definitions.map((item) => ({
    ...item,
    available: true,
    defaultEnabled: true,
    projectEnabled:
      item.kind === "skill"
        ? projectValue.enabledSkills.includes(item.id)
        : item.kind === "connector"
          ? projectValue.enabledConnectors.includes(item.id)
          : projectValue.enabledSpecialists.includes(item.id),
    statusDetail: item.status === "needs_configuration" ? "Configuration required." : "",
    metadata: item.kind === "specialist" ? { auto_dispatch: true } : {},
  }));
}

function installClient(overrides: Partial<PpxClientApi> = {}): {
  client: PpxClientApi;
  emit: (event: RunEvent) => void;
} {
  let listener: ((event: RunEvent) => void) | null = null;
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
    listGmScienceCapabilities: async (projectId) => ({ projectId: projectId ?? "", items: capabilities() }),
    updateGmScienceProjectCapabilities: async (projectId, input) => {
      const updated = project({
        id: projectId,
        enabledSkills: input.enabledSkills,
        enabledConnectors: input.enabledConnectors,
        enabledSpecialists: input.enabledSpecialists,
      });
      return { project: updated, capabilities: capabilities(updated) };
    },
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
    onRunEvent: (next) => {
      listener = next;
      return () => {
        if (listener === next) {
          listener = null;
        }
      };
    },
    ...overrides,
  };
  window.ppxClient = client;
  return { client, emit: (event) => listener?.(event) };
}

function artifact(overrides: Partial<GmScienceArtifact>): GmScienceArtifact {
  return {
    id: "art-default",
    projectId: "proj_123",
    sessionId: "session-a",
    type: "paper",
    title: "Artifact",
    pathOrUrl: "",
    mimeType: "application/json",
    metadata: {},
    provenance: {},
    createdAt: "2026-07-10T10:00:00.000Z",
    updatedAt: "2026-07-10T10:00:00.000Z",
    ...overrides,
  };
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
      expect(createGmScienceProject).toHaveBeenCalledWith({
        name: "Genome notes",
        description: "Cell line literature",
        agentContext: "Always use GRCh38.",
      });
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

  it("updates the selected Project connector allowlist from Customize", async () => {
    const updateGmScienceProjectCapabilities = vi.fn(async (projectId, input) => {
      const updated = project({
        id: projectId,
        enabledSkills: input.enabledSkills,
        enabledConnectors: input.enabledConnectors,
        enabledSpecialists: input.enabledSpecialists,
      });
      return { project: updated, capabilities: capabilities(updated) };
    });
    installClient({ updateGmScienceProjectCapabilities });

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /Protein design/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Customize" }));
    fireEvent.click(await screen.findByRole("button", { name: "Connectors" }));
    const pubmedSwitch = await screen.findByRole("switch", { name: "Enable PubMed" });
    expect(pubmedSwitch).toHaveAttribute("aria-checked", "true");
    fireEvent.click(pubmedSwitch);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(updateGmScienceProjectCapabilities).toHaveBeenCalledWith("proj_123", {
        enabledSkills: ["literature-review"],
        enabledConnectors: ["arxiv", "openalex"],
        enabledSpecialists: ["paper_reader", "research_reviewer"],
      });
    });
  });

  it("does not allow an unavailable connector to be enabled", async () => {
    const projectValue = project({ enabledConnectors: ["arxiv", "openalex"] });
    const items = capabilities(projectValue).map((item) =>
      item.id === "pubmed"
        ? {
            ...item,
            available: false,
            projectEnabled: false,
            status: "disabled" as const,
            statusDetail: "Disabled in global configuration.",
          }
        : item,
    );
    installClient({
      listGmScienceProjects: async () => ({ projects: [projectValue] }),
      listGmScienceCapabilities: async (projectId) => ({ projectId: projectId ?? "", items }),
    });

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /Protein design/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Customize" }));
    fireEvent.click(await screen.findByRole("button", { name: "Connectors" }));

    expect(await screen.findByRole("switch", { name: "Enable PubMed" })).toBeDisabled();
  });

  it("renders research artifact details with metadata fallbacks", async () => {
    installClient({
      listGmScienceArtifacts: async () => ({
        artifacts: [
          artifact({
            id: "art-paper",
            title: "Reliable Protein Folding",
            pathOrUrl: "https://example.test/folding",
            metadata: {
              year: 2024,
              authors: ["Ada Lovelace", "Grace Hopper"],
              source_names: ["arxiv", "pubmed"],
              doi: "10.1000/folding",
              citation_count: 12,
            },
          }),
          artifact({
            id: "art-report",
            type: "report",
            title: "Folding review",
            pathOrUrl: "/tmp/folding.md",
            metadata: { paper_artifact_ids: ["art-paper"] },
          }),
          artifact({
            id: "art-citation",
            type: "citation",
            title: "Reliable Protein Folding citation",
            metadata: { paper_artifact_id: "art-paper", report_artifact_id: "art-report" },
          }),
          artifact({ id: "art-malformed", title: "Metadata-free paper", metadata: {} }),
          artifact({
            id: "art-reading-note",
            type: "reading_note",
            title: "Folding reading note",
            metadata: {
              source_artifact_ids: ["art-paper"],
              evidence_scopes: ["metadata_abstract"],
              focus: "protein folding reliability",
              confidence_note: "Limited to abstract metadata.",
            },
          }),
          artifact({
            id: "art-critique",
            type: "critique_report",
            title: "Folding critique",
            metadata: {
              verdict: "revise",
              target_artifact_id: "art-report",
              findings: [
                {
                  severity: "major",
                  category: "evidence",
                  claim: "The central claim needs stronger support.",
                },
                {
                  severity: "minor",
                  category: "clarity",
                  claim: "Define the evaluation metric.",
                },
              ],
            },
          }),
        ],
      }),
    });

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Protein design/ }));

    expect(await screen.findByText("Reliable Protein Folding")).toBeInTheDocument();
    expect(screen.getByText("Ada Lovelace, Grace Hopper")).toBeInTheDocument();
    expect(screen.getByText("2024 · arxiv + pubmed · 12 citations")).toBeInTheDocument();
    expect(screen.getByText("DOI 10.1000/folding")).toBeInTheDocument();
    expect(screen.getByText(/folding\.md · 1 cited paper/)).toBeInTheDocument();
    expect(screen.getByText("Linked to report")).toBeInTheDocument();
    expect(screen.getByText("Metadata-free paper")).toBeInTheDocument();
    expect(screen.getByText("1 source · Evidence: abstract metadata")).toBeInTheDocument();
    expect(screen.getByText("Focus: protein folding reliability")).toBeInTheDocument();
    expect(screen.getByText("Limited to abstract metadata.")).toBeInTheDocument();
    expect(screen.getByText("revise")).toBeInTheDocument();
    expect(screen.getByText("1 major · 1 minor")).toBeInTheDocument();
    expect(screen.getByText("Target: art-report")).toBeInTheDocument();
    expect(screen.getByText("The central claim needs stronger support.")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Open" })).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Open" })).toHaveAttribute("href", "https://example.test/folding");
  });

  it("filters artifacts by title, type, and metadata", async () => {
    installClient({
      listGmScienceArtifacts: async () => ({
        artifacts: [
          artifact({ id: "art-paper", title: "Protein atlas", metadata: { doi: "10.1000/atlas" } }),
          artifact({ id: "art-report", type: "report", title: "Genome review" }),
        ],
      }),
    });

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Protein design/ }));
    await screen.findByText("Protein atlas");

    fireEvent.change(screen.getByPlaceholderText("Search artifacts..."), { target: { value: "report" } });

    expect(screen.queryByText("Protein atlas")).not.toBeInTheDocument();
    expect(screen.getByText("Genome review")).toBeInTheDocument();
  });

  it("refreshes artifacts when a run finishes", async () => {
    const paper = artifact({ id: "art-new", title: "Newly indexed paper" });
    const listGmScienceArtifacts = vi
      .fn()
      .mockResolvedValueOnce({ artifacts: [] })
      .mockResolvedValueOnce({ artifacts: [paper] });
    const { emit } = installClient({ listGmScienceArtifacts });

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Protein design/ }));
    await screen.findByText("No artifacts yet");

    await act(async () => {
      emit({ type: "run.finished", runId: "run-1", sessionId: "session-a" });
    });

    expect(await screen.findByText("Newly indexed paper")).toBeInTheDocument();
    expect(listGmScienceArtifacts).toHaveBeenCalledTimes(2);
  });

  it("refreshes artifacts after a run request fails", async () => {
    const listGmScienceArtifacts = vi.fn(async () => ({ artifacts: [] }));
    installClient({
      listGmScienceArtifacts,
      sendMessage: async () => {
        throw new Error("run failed");
      },
    });

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Protein design/ }));
    await screen.findByText("No artifacts yet");
    fireEvent.change(screen.getByPlaceholderText("向本地 agent 发送任务..."), { target: { value: "search" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    await screen.findByText("run failed");
    await waitFor(() => expect(listGmScienceArtifacts).toHaveBeenCalledTimes(2));
  });
});
