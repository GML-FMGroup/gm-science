import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { vi } from "vitest";
import { App } from "../app/src/App";
import type {
  BootstrapPayload,
  ClientDiagnostics,
  GmScienceProject,
  GmScienceRun,
  GmScienceSessionPolicy,
  GmScienceSettings,
  PpxClientApi,
  RunEvent,
  RuntimeStatus,
  SessionSummary,
} from "../app/src/types";

function buildSettings(): GmScienceSettings {
  return {
    model: { provider: "openai_codex", model: "openai-codex/gpt-5.5" },
    memory: { enabled: true },
    providers: [{ id: "openai_codex", name: "OpenAI Codex", defaultModel: "openai-codex/gpt-5.5", authType: "oauth", credentialRequired: true, credentialConfigured: true, credentialSource: "oauth_cache", active: true }],
    permissions: { items: [] },
    network: {
      enabled: true,
      enforceAllowlist: true,
      allowPrivateNetworks: false,
      packageMirrors: { condaChannelMirror: "", pythonPackageIndex: "", caBundlePath: "" },
      categories: [],
      customDomains: [],
      enforcementBoundary: "Managed gm-science network clients.",
    },
    compute: {
      targets: [{ id: "local", type: "local", name: "This computer", enabled: true, configured: true, executable: true, status: "ready", statusDetail: "Local execution is available.", metadata: {} }],
    },
    literature: {
      arxiv: { status: "ready", statusDetail: "" },
      pubmed: { email: "", apiKeyConfigured: false, status: "needs_configuration", statusDetail: "Configuration required." },
      openalex: { apiKeyConfigured: false, status: "needs_configuration", statusDetail: "Configuration required." },
    },
  };
}

function buildBootstrapPayload(): BootstrapPayload {
  const runtime: RuntimeStatus = {
    target: { id: "local-default", type: "local", name: "This Mac" },
    state: "healthy",
    summary: "ready",
    detail: "detail",
  };
  const sessions: SessionSummary[] = [
    {
      id: "session-a",
      agentId: "agent-1",
      projectId: "proj-test",
      title: "Session A",
      updatedAt: "2026-04-02T10:00:00.000Z",
      lastMessagePreview: "Preview A should stay hidden",
    },
    {
      id: "session-b",
      agentId: "agent-1",
      projectId: "proj-test",
      title: "Session B",
      updatedAt: "2026-04-02T09:00:00.000Z",
      lastMessagePreview: "Preview B should stay hidden",
    },
  ];
  return {
    runtime,
    agents: [
      {
        id: "agent-1",
        name: "Agent 1",
        description: "Local test agent",
        provider: "openai_codex",
        model: "openai-codex/gpt-5.5",
        enabled: true,
        status: "healthy",
        tags: ["local"],
      },
    ],
    sessions,
    messages: [
      {
        id: "message-a",
        sessionId: "session-a",
        role: "assistant",
        status: "completed",
        createdAt: "2026-04-02T10:00:01.000Z",
        parts: [{ type: "markdown", text: "Loaded Session A" }],
      },
    ],
    selectedAgentId: "agent-1",
    selectedSessionId: "session-a",
  };
}

function buildDiagnostics(): ClientDiagnostics {
  return {
    mode: "local",
    target: { id: "local-default", type: "local", name: "This Mac" },
    openppxRoot: "/tmp/gm-science-runtime",
    openppxRootExists: true,
    pythonBin: "/tmp/gm-science-runtime/.venv/bin/python",
    globalConfigPath: "/tmp/.openppx/global_config.json",
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

function buildProject(overrides: Partial<GmScienceProject> = {}): GmScienceProject {
  return {
    id: "proj-test",
    name: "Test research project",
    description: "Project used by app tests.",
    agentContext: "Keep project context attached.",
    workspacePath: "/tmp/gm-science/proj-test",
    sessionsCount: 2,
    artifactsCount: 0,
    enabledSkills: ["Literature Review"],
    enabledConnectors: ["OpenAlex"],
    enabledSpecialists: ["Reviewer"],
    sessionPolicyDefaults: {
      delegationEnabled: false,
      autoReviewEnabled: false,
      memoryEnabled: false,
      specialistId: "",
      reviewerModel: "default",
      computeTarget: "local",
    },
    createdAt: "2026-04-02T10:00:00.000Z",
    updatedAt: "2026-04-02T10:00:00.000Z",
    ...overrides,
  };
}

function buildSessionPolicy(sessionId: string): GmScienceSessionPolicy {
  return {
    sessionId,
    projectId: "proj-test",
    delegationEnabled: false,
    autoReviewEnabled: false,
    memoryEnabled: false,
    specialistId: "",
    reviewerModel: "default",
    computeTarget: "local",
    specialists: [],
    reviewerAvailable: false,
    reviewerModels: [{ id: "default", name: "Default" }],
    computeTargets: [{ id: "local", name: "Local" }],
    issues: [],
  };
}

function buildScienceRun(overrides: Partial<GmScienceRun> = {}): GmScienceRun {
  return {
    taskId: "task-test",
    projectId: "proj-test",
    sessionId: "session-a",
    parentTaskId: "",
    kind: "local_python",
    title: "Python run",
    status: "completed",
    progressSummary: "Completed.",
    terminalSummary: "Completed.",
    lastError: "",
    createdAt: "2026-04-02T10:00:00.000Z",
    updatedAt: "2026-04-02T10:00:00.000Z",
    createdAtMs: 1,
    updatedAtMs: 2,
    endedAtMs: 2,
    canCancel: false,
    canRetry: true,
    logPreview: "",
    artifactIds: [],
    ...overrides,
  };
}

function installClient(overrides: Partial<PpxClientApi> = {}): { client: PpxClientApi; emit: (event: RunEvent) => void } {
  let listener: ((event: RunEvent) => void) | null = null;
  const client: PpxClientApi = {
    bootstrap: async () => buildBootstrapPayload(),
    getDiagnostics: async () => buildDiagnostics(),
    saveConnectionSettings: async () => buildDiagnostics(),
    runRuntimeCommand: async () => buildBootstrapPayload().runtime,
    listSessions: async () => ({ sessions: buildBootstrapPayload().sessions }),
    createSession: async () => ({ session: buildBootstrapPayload().sessions[0] }),
    loadSession: async (sessionId) => ({
      messages: buildBootstrapPayload().messages.filter((message) => message.sessionId === sessionId),
    }),
    sendMessage: async () => new Promise<{ runId: string }>(() => undefined),
    getGmScienceStorage: async () => { throw new Error("Unused in this test."); },
    getGmScienceUsage: async () => { throw new Error("Unused in this test."); },
    listGmScienceProjects: async () => ({ projects: [buildProject()] }),
    createGmScienceProject: async (input) => ({
      project: {
        id: "proj-test",
        name: input.name,
        description: input.description ?? "",
        agentContext: input.agentContext ?? "",
        workspacePath: "/tmp/gm-science/proj-test",
        sessionsCount: 0,
        artifactsCount: 0,
        enabledSkills: input.enabledSkills ?? [],
        enabledConnectors: input.enabledConnectors ?? [],
        enabledSpecialists: input.enabledSpecialists ?? [],
        sessionPolicyDefaults: buildProject().sessionPolicyDefaults,
        createdAt: "2026-04-02T10:00:00.000Z",
        updatedAt: "2026-04-02T10:00:00.000Z",
      },
    }),
    getGmScienceProject: async (projectId) => ({
      project: {
        id: projectId,
        name: "Project",
        description: "",
        agentContext: "",
        workspacePath: "/tmp/gm-science/project",
        sessionsCount: 0,
        artifactsCount: 0,
        enabledSkills: [],
        enabledConnectors: [],
        enabledSpecialists: [],
        sessionPolicyDefaults: buildProject().sessionPolicyDefaults,
        createdAt: "2026-04-02T10:00:00.000Z",
        updatedAt: "2026-04-02T10:00:00.000Z",
      },
    }),
    listGmScienceCapabilities: async (projectId) => ({ projectId: projectId ?? "", items: [] }),
    createGmScienceSkill: async (input) => ({
      id: input.id, kind: "skill", name: input.name, description: input.description,
      source: "local", version: "", license: "", files: ["SKILL.md"], available: true,
      defaultEnabled: false, projectEnabled: null, status: "ready", statusDetail: "", metadata: {},
    }),
    createGmScienceConnector: async (input) => ({
      id: `mcp:${input.id}`, kind: "connector", name: input.name, description: input.description,
      source: "local", version: "", license: "", files: [], available: true,
      defaultEnabled: false, projectEnabled: null, status: "ready", statusDetail: "", metadata: {},
    }),
    createGmScienceSpecialist: async (input) => ({
      id: input.id, kind: "specialist", name: input.name, description: input.description,
      source: "local", version: "", license: "", files: [], available: true,
      defaultEnabled: false, projectEnabled: null, status: "ready", statusDetail: "", metadata: {},
    }),
    updateGmScienceProjectCapabilities: async (projectId, input) => ({
      project: buildProject({
        id: projectId,
        enabledSkills: input.enabledSkills,
        enabledConnectors: input.enabledConnectors,
        enabledSpecialists: input.enabledSpecialists,
      }),
      capabilities: [],
    }),
    getGmScienceSettings: async () => buildSettings(),
    updateGmScienceSettings: async () => {
      throw new Error("Settings updates are not configured in this test");
    },
    checkGmScienceComputeTarget: async (targetId) => ({
      targetId,
      status: "ready",
      reachable: true,
      executable: true,
      detail: "Local execution is available.",
      checkedAt: "2026-04-02T10:00:00.000Z",
    }),
    getGmScienceMemory: async (projectId) => ({ projectId, notes: [], candidates: [], categories: [] }),
    createGmScienceMemoryNote: async () => {
      throw new Error("Memory creation is not configured in this test");
    },
    updateGmScienceMemoryNote: async () => {
      throw new Error("Memory updates are not configured in this test");
    },
    deleteGmScienceMemoryNote: async () => undefined,
    clearGmScienceMemory: async () => 0,
    reviewGmScienceMemoryCandidate: async () => {
      throw new Error("Memory review is not configured in this test");
    },
    getGmScienceSessionPolicy: async (sessionId) => buildSessionPolicy(sessionId),
    updateGmScienceSessionPolicy: async (sessionId, input) => ({ ...buildSessionPolicy(sessionId), ...input }),
    listGmScienceArtifacts: async () => ({ artifacts: [] }),
    listGmScienceResources: async () => ({ resources: [] }),
    getGmScienceResourceDetail: async () => {
      throw new Error("Resource detail is not configured in this test");
    },
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
        createdAt: "2026-04-02T10:00:00.000Z",
        updatedAt: "2026-04-02T10:00:00.000Z",
      },
    }),
    listGmScienceRuns: async () => ({ runs: [] }),
    getGmScienceRun: async (projectId, taskId) => ({ run: buildScienceRun({ projectId, taskId }) }),
    createGmSciencePythonRun: async (projectId, input) => ({
      run: buildScienceRun({ projectId, sessionId: input.sessionId ?? "", title: input.title }),
    }),
    cancelGmScienceRun: async (projectId, taskId) => ({
      run: buildScienceRun({ projectId, taskId, status: "cancelled" }),
    }),
    retryGmScienceRun: async (projectId, taskId) => ({
      run: buildScienceRun({ projectId, taskId: "task-retry", parentTaskId: taskId }),
    }),
    selectGmScienceDatasetFile: async () => null,
    listGmScienceDatasets: async () => ({ datasets: [] }),
    getGmScienceDataset: async () => {
      throw new Error("Dataset not found");
    },
    importGmScienceDataset: async () => {
      throw new Error("Dataset import is not configured in this test");
    },
    listGmScienceAnalyses: async () => ({ analyses: [] }),
    getGmScienceAnalysis: async () => {
      throw new Error("Analysis not found");
    },
    createGmScienceAnalysis: async () => {
      throw new Error("Analysis creation is not configured in this test");
    },
    runGmScienceAnalysis: async () => {
      throw new Error("Analysis execution is not configured in this test");
    },
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
  return {
    client,
    emit: (event) => listener?.(event),
  };
}

async function openDefaultProject(): Promise<void> {
  const projects = await screen.findByRole("region", { name: "Projects" });
  fireEvent.click(within(projects).getByRole("button", { name: /^Test research project/ }));
}

function messageComposer(): HTMLElement {
  return screen.getByRole("textbox", { name: "Message" });
}

function sendButton(): HTMLElement {
  return screen.getByRole("button", { name: "Send" });
}

describe("App sending state", () => {
  it("jumps to the latest reply when loading a session", async () => {
    const scrollTo = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: scrollTo,
    });

    installClient({
      loadSession: async (sessionId) =>
        sessionId === "session-b"
          ? {
              messages: [
                {
                  id: "message-b",
                  sessionId: "session-b",
                  role: "assistant",
                  status: "completed",
                  createdAt: "2026-04-02T10:00:02.000Z",
                  parts: [{ type: "markdown", text: "Loaded Session B" }],
                },
              ],
            }
          : { messages: buildBootstrapPayload().messages },
    });

    render(<App />);

    await openDefaultProject();
    await screen.findByText("Loaded Session A");
    fireEvent.click(screen.getByRole("button", { name: /Session B/ }));
    await screen.findByText("Loaded Session B");

    expect(scrollTo).toHaveBeenCalledWith(expect.objectContaining({ behavior: "auto" }));
  });

  it("keeps send disabled while the current agent still has a running reply", async () => {
    installClient();

    render(<App />);

    await openDefaultProject();

    fireEvent.change(messageComposer(), {
      target: { value: "hello world" },
    });
    fireEvent.click(sendButton());

    await waitFor(() => expect(sendButton()).toBeDisabled());

    fireEvent.click(screen.getByRole("button", { name: /Session B/ }));
    fireEvent.change(messageComposer(), {
      target: { value: "follow up" },
    });

    await waitFor(() => {
      expect(sendButton()).toBeDisabled();
    });
  });

  it("clears the current session sending state after a completed message event", async () => {
    const { emit } = installClient();

    render(<App />);

    await openDefaultProject();

    fireEvent.change(messageComposer(), {
      target: { value: "hello world" },
    });
    fireEvent.click(sendButton());

    await waitFor(() => expect(sendButton()).toBeDisabled());

    await act(async () => {
      emit({
        type: "message.updated",
        runId: "run-1",
        sessionId: "session-a",
        messageId: "assistant-1",
        status: "completed",
        replaceParts: [{ type: "markdown", text: "done" }],
      });
    });

    fireEvent.change(messageComposer(), {
      target: { value: "second try" },
    });

    await waitFor(() => {
      expect(sendButton()).toBeEnabled();
    });
  });

  it("sends on Enter and keeps Shift+Enter for newline", async () => {
    const sendMessage = vi.fn(async () => ({ runId: "run-1" }));
    installClient({ sendMessage });

    render(<App />);

    await openDefaultProject();

    const composer = messageComposer();

    fireEvent.change(composer, { target: { value: "first line" } });
    fireEvent.keyDown(composer, { key: "Enter", code: "Enter", charCode: 13 });

    await waitFor(() => {
      expect(sendMessage).toHaveBeenCalledWith({
        agentId: "agent-1",
        sessionId: "session-a",
        projectId: "proj-test",
        text: "first line",
      });
    });

    fireEvent.change(composer, { target: { value: "hello" } });
    fireEvent.keyDown(composer, { key: "Enter", code: "Enter", charCode: 13, shiftKey: true });

    expect(sendMessage).toHaveBeenCalledTimes(1);
  });

  it("does not create an orphan session on startup and creates one for the project on first send", async () => {
    const createdSession: SessionSummary = {
      id: "session-created",
      agentId: "agent-1",
      projectId: "proj-test",
      title: "New session",
      updatedAt: "2026-04-02T10:01:00.000Z",
      lastMessagePreview: "Start a task",
    };
    const createSession = vi.fn(async () => ({ session: createdSession }));
    const sendMessage = vi.fn(async () => ({ runId: "run-1" }));
    installClient({
      bootstrap: async () => ({
        ...buildBootstrapPayload(),
        sessions: [],
        messages: [],
        selectedSessionId: "",
      }),
      listSessions: async () => ({ sessions: [] }),
      createSession,
      sendMessage,
    });

    render(<App />);

    await openDefaultProject();
    await screen.findByText("Test research project is ready");
    expect(createSession).not.toHaveBeenCalled();

    fireEvent.change(messageComposer(), {
      target: { value: "first task" },
    });
    fireEvent.click(sendButton());

    await waitFor(() => {
      expect(createSession).toHaveBeenCalledWith("agent-1", "proj-test");
      expect(sendMessage).toHaveBeenCalledWith({
        agentId: "agent-1",
        sessionId: "session-created",
        projectId: "proj-test",
        text: "first task",
      });
    });
  });

  it("creates a session before sending if the active session was not selected yet", async () => {
    const createdSession: SessionSummary = {
      id: "session-on-send",
      agentId: "agent-1",
      projectId: "proj-test",
      title: "New session",
      updatedAt: "2026-04-02T10:01:00.000Z",
      lastMessagePreview: "Start a task",
    };
    const createSession = vi.fn(async () => ({ session: createdSession }));
    const sendMessage = vi.fn(async () => ({ runId: "run-1" }));
    installClient({
      bootstrap: async () => ({
        ...buildBootstrapPayload(),
        sessions: [],
        messages: [],
        selectedSessionId: "stale-session",
      }),
      listSessions: async () => ({ sessions: [] }),
      createSession,
      sendMessage,
    });

    render(<App />);

    await openDefaultProject();
    await screen.findByText("Test research project is ready");

    fireEvent.change(messageComposer(), {
      target: { value: "recover session" },
    });
    fireEvent.click(sendButton());

    await waitFor(() => {
      expect(createSession).toHaveBeenCalledWith("agent-1", "proj-test");
      expect(sendMessage).toHaveBeenCalledWith({
        agentId: "agent-1",
        sessionId: "session-on-send",
        projectId: "proj-test",
        text: "recover session",
      });
    });
  });

  it("shows a send error instead of failing silently", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    try {
      installClient({
        sendMessage: async () => {
          throw new Error("gateway refused the run");
        },
      });

      render(<App />);

      await openDefaultProject();

      fireEvent.change(messageComposer(), {
        target: { value: "will fail" },
      });
      fireEvent.click(sendButton());

      await screen.findByText("gateway refused the run");
    } finally {
      consoleError.mockRestore();
    }
  });

  it("renders an icon send button that activates when composer has text", async () => {
    installClient();

    render(<App />);

    await openDefaultProject();

    const button = sendButton();
    expect(button).toBeDisabled();

    fireEvent.change(messageComposer(), {
      target: { value: "hello world" },
    });

    await waitFor(() => {
      expect(button).toBeEnabled();
      expect(button.className).toContain("ready");
    });
  });

  it("does not render session preview subtitles in the session list", async () => {
    installClient();

    render(<App />);

    await openDefaultProject();
    await waitFor(() => {
      expect(screen.getAllByText("Session A").length).toBeGreaterThan(0);
    });

    expect(screen.queryByText("Preview A should stay hidden")).not.toBeInTheDocument();
    expect(screen.queryByText("Preview B should stay hidden")).not.toBeInTheDocument();
  });

  it("shows only sessions that belong to the selected project", async () => {
    const otherProject = buildProject({ id: "proj-other", name: "Other research project", sessionsCount: 1 });
    const otherSession: SessionSummary = {
      id: "session-other",
      agentId: "agent-1",
      projectId: otherProject.id,
      title: "Other project session",
      updatedAt: "2026-04-02T11:00:00.000Z",
      lastMessagePreview: "Other",
    };
    installClient({
      listGmScienceProjects: async () => ({ projects: [buildProject(), otherProject] }),
      listSessions: async () => ({ sessions: [...buildBootstrapPayload().sessions, otherSession] }),
      loadSession: async () => ({ messages: [] }),
    });

    render(<App />);

    await openDefaultProject();
    await screen.findByRole("button", { name: /Session A/ });
    expect(screen.queryByRole("button", { name: /Other project session/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Back to dashboard" }));
    const projects = await screen.findByRole("region", { name: "Projects" });
    fireEvent.click(within(projects).getByRole("button", { name: /^Other research project/ }));
    await screen.findByRole("button", { name: /Other project session/ });
    expect(screen.queryByRole("button", { name: /Session A/ })).not.toBeInTheDocument();
  });

  it("uses the first user message as the visible session title", async () => {
    const createdSession: SessionSummary = {
      id: "session-created",
      agentId: "agent-1",
      projectId: "proj-test",
      title: "New session",
      updatedAt: "2026-04-02T10:01:00.000Z",
      lastMessagePreview: "",
    };
    const sendMessage = vi.fn(async () => ({ runId: "run-1" }));
    installClient({
      bootstrap: async () => ({
        ...buildBootstrapPayload(),
        sessions: [],
        messages: [],
        selectedSessionId: "",
      }),
      listSessions: async () => ({ sessions: [] }),
      createSession: async () => ({ session: createdSession }),
      sendMessage,
    });

    render(<App />);

    await openDefaultProject();
    await screen.findByText("Test research project is ready");

    fireEvent.change(messageComposer(), {
      target: { value: "帮我查一下深圳到青岛的火车和费用" },
    });
    fireEvent.click(sendButton());

    await waitFor(() => {
      expect(screen.getAllByText("帮我查一下深圳到青岛的火车和费用").length).toBeGreaterThan(0);
    });
    expect(sendMessage).toHaveBeenCalledWith({
      agentId: "agent-1",
      sessionId: "session-created",
      projectId: "proj-test",
      text: "帮我查一下深圳到青岛的火车和费用",
    });
  });

  it("shows assistant identity only once across consecutive assistant replies", async () => {
    installClient({
      bootstrap: async () => ({
        ...buildBootstrapPayload(),
        messages: [
          {
            id: "message-a",
            sessionId: "session-a",
            role: "assistant",
            status: "completed",
            createdAt: "2026-04-02T10:00:01.000Z",
            parts: [{ type: "markdown", text: "First chunk" }],
          },
          {
            id: "message-b",
            sessionId: "session-a",
            role: "assistant",
            status: "streaming",
            createdAt: "2026-04-02T10:00:02.000Z",
            parts: [{ type: "step_ref", stepId: "step-1", title: "exec", status: "running", detail: "command: pwd" }],
          },
        ],
      }),
      loadSession: async () => ({
        messages: [
          {
            id: "message-a",
            sessionId: "session-a",
            role: "assistant",
            status: "completed",
            createdAt: "2026-04-02T10:00:01.000Z",
            parts: [{ type: "markdown", text: "First chunk" }],
          },
          {
            id: "message-b",
            sessionId: "session-a",
            role: "assistant",
            status: "streaming",
            createdAt: "2026-04-02T10:00:02.000Z",
            parts: [{ type: "step_ref", stepId: "step-1", title: "exec", status: "running", detail: "command: pwd" }],
          },
        ],
      }),
    });

    render(<App />);

    await openDefaultProject();
    await screen.findByText("First chunk");
    expect(screen.getAllByText("Agent")).toHaveLength(1);
  });

  it("clears previous messages immediately when switching sessions", async () => {
    let resolveLoad: ((value: { messages: BootstrapPayload["messages"] }) => void) | null = null;
    installClient({
      loadSession: async (sessionId) => {
        if (sessionId === "session-a") {
          return { messages: buildBootstrapPayload().messages };
        }
        return await new Promise<{ messages: BootstrapPayload["messages"] }>((resolve) => {
          resolveLoad = resolve;
        });
      },
    });

    render(<App />);

    await openDefaultProject();
    await screen.findByText("Loaded Session A");

    fireEvent.click(screen.getByRole("button", { name: /Session B/ }));

    await waitFor(() => {
      expect(screen.queryByText("Loaded Session A")).not.toBeInTheDocument();
    });

    await act(async () => {
      resolveLoad?.({
        messages: [
          {
            id: "message-b",
            sessionId: "session-b",
            role: "assistant",
            status: "completed",
            createdAt: "2026-04-02T10:00:02.000Z",
            parts: [{ type: "markdown", text: "Loaded Session B" }],
          },
        ],
      });
    });

    await screen.findByText("Loaded Session B");
  });

  it("renders live diagnostics in settings view", async () => {
    installClient();

    render(<App />);

    await screen.findByText("gm-science");

    fireEvent.click(screen.getByRole("button", { name: "Settings" }));

    await screen.findByText("Connection");
    expect(screen.getByText("http://127.0.0.1:8876")).toBeInTheDocument();
    expect(screen.getByText("This Mac (local)")).toBeInTheDocument();
  });

  it("shows Compute health-check failures in the settings view", async () => {
    installClient({
      checkGmScienceComputeTarget: async () => {
        throw new Error("Local Compute health check failed");
      },
    });

    render(<App />);
    await screen.findByText("gm-science");
    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    fireEvent.click(await screen.findByRole("button", { name: "Compute" }));
    fireEvent.click(await screen.findByRole("button", { name: "Check" }));

    await screen.findByText("Local Compute health check failed");
  });

  it("shows connection save failures in the settings view", async () => {
    installClient({
      saveConnectionSettings: async () => {
        throw new Error("Unable to save local connection");
      },
    });

    render(<App />);
    await screen.findByText("gm-science");
    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    fireEvent.click(await screen.findByRole("button", { name: "Save connection" }));

    await screen.findByText("Unable to save local connection");
  });

  it("renders remote target diagnostics when provided", async () => {
    installClient({
      getDiagnostics: async () => ({
        ...buildDiagnostics(),
        mode: "remote",
        target: { id: "remote-default", type: "remote", name: "Ops Gateway" },
        clientApiManagedByClient: false,
        clientApiBaseUrl: "http://10.0.0.8:8765",
        clientApiProcessRunning: false,
      }),
    });

    render(<App />);

    await screen.findByText("gm-science");
    fireEvent.click(screen.getByRole("button", { name: "Settings" }));

    await screen.findByText("Ops Gateway (remote)");
    expect(screen.getAllByText("remote").length).toBeGreaterThan(0);
  });

  it("saves connection settings from the settings form", async () => {
    const saveConnectionSettings = vi.fn(async () => ({
      ...buildDiagnostics(),
      mode: "remote" as const,
      target: { id: "remote-ops-gateway", type: "remote" as const, name: "Ops Gateway" },
      clientApiManagedByClient: false,
      clientApiBaseUrl: "http://10.0.0.8:8765",
    }));

    installClient({
      saveConnectionSettings,
      getDiagnostics: async () => buildDiagnostics(),
      bootstrap: async () => ({
        ...buildBootstrapPayload(),
        runtime: {
          ...buildBootstrapPayload().runtime,
          target: { id: "remote-ops-gateway", type: "remote", name: "Ops Gateway" },
        },
      }),
    });

    render(<App />);

    await screen.findByText("gm-science");
    fireEvent.click(screen.getByRole("button", { name: "Settings" }));

    fireEvent.change(screen.getByDisplayValue("This Mac"), {
      target: { value: "Ops Gateway" },
    });
    fireEvent.change(screen.getByDisplayValue("http://127.0.0.1:8876"), {
      target: { value: "http://10.0.0.8:8765" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "Target type" }), {
      target: { value: "remote" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save connection" }));

    await waitFor(() => {
      expect(saveConnectionSettings).toHaveBeenCalledWith({
        targetType: "remote",
        targetId: "remote-ops-gateway",
        targetName: "Ops Gateway",
        clientApiBaseUrl: "http://10.0.0.8:8765",
      });
    });
  });
});
