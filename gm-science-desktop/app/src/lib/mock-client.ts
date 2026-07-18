import type {
  AgentProfile,
  BootstrapPayload,
  ChatMessage,
  ClientDiagnostics,
  ConnectionSettings,
  CreateGmScienceAnalysisInput,
  CreateGmScienceArtifactInput,
  CreateGmSciencePythonRunInput,
  CreateGmScienceProjectInput,
  GmScienceArtifact,
  GmScienceAnalysis,
  GmScienceCapability,
  GmScienceCapabilityCatalog,
  GmScienceProject,
  GmScienceDataset,
  GmScienceRun,
  ImportGmScienceDatasetInput,
  MessagePart,
  RuntimeCommand,
  RuntimeStatus,
  RunEvent,
  SendMessageInput,
  SessionSummary,
  UpdateGmScienceCapabilitiesInput,
} from "../types";

interface StoreState {
  runtime: RuntimeStatus;
  agents: AgentProfile[];
  projects: GmScienceProject[];
  artifactsByProject: Record<string, GmScienceArtifact[]>;
  datasetsByProject: Record<string, GmScienceDataset[]>;
  analysesByProject: Record<string, GmScienceAnalysis[]>;
  runsByProject: Record<string, GmScienceRun[]>;
  sessionsByAgent: Record<string, SessionSummary[]>;
  messagesBySession: Record<string, ChatMessage[]>;
  selectedAgentId: string;
  selectedSessionId: string;
}

type EventSink = (event: RunEvent) => void;

const now = () => new Date().toISOString();

function compactSessionTitle(text: string): string {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (normalized.length <= 64) {
    return normalized;
  }
  return `${normalized.slice(0, 61).trimEnd()}...`;
}

function isGenericSessionTitle(title: string): boolean {
  const normalized = title.trim();
  return (
    !normalized ||
    normalized === "New local session" ||
    normalized === "New chat" ||
    normalized === "新对话" ||
    normalized.startsWith("Session ")
  );
}

const firstAgentId = "builder";
const firstSessionId = "builder-session-1";
const firstProjectId = "proj_mock_research";

const state: StoreState = {
  runtime: {
    target: {
      id: "local-default",
      type: "local",
      name: "This Mac",
    },
    state: "healthy",
    summary: "Local openppx runtime is ready.",
    detail: "Renderer talks to Electron host API. Runtime adapter is local-only in v1.",
  },
  agents: [
    {
      id: "builder",
      name: "Builder",
      description: "General local execution agent for planning and implementation.",
      enabled: true,
      status: "healthy",
      tags: ["default", "coding"],
    },
    {
      id: "operator",
      name: "Operator",
      description: "Operational agent focused on diagnostics and orchestration.",
      enabled: true,
      status: "idle",
      tags: ["ops", "runtime"],
    },
  ],
  projects: [
    {
      id: firstProjectId,
      name: "Example research project",
      description: "A local-first personal science workspace.",
      agentContext: "Keep claims linked to citations and prefer reproducible notes.",
      workspacePath: "~/.gm-science/workspaces/proj_mock_research",
      sessionsCount: 1,
      artifactsCount: 0,
      enabledSkills: ["literature-review"],
      enabledConnectors: ["arxiv", "pubmed", "openalex"],
      enabledSpecialists: ["paper_reader", "research_reviewer"],
      createdAt: now(),
      updatedAt: now(),
    },
  ],
  artifactsByProject: {
    [firstProjectId]: [],
  },
  datasetsByProject: {
    [firstProjectId]: [],
  },
  analysesByProject: {
    [firstProjectId]: [],
  },
  runsByProject: {
    [firstProjectId]: [],
  },
  sessionsByAgent: {
    builder: [
      {
        id: firstSessionId,
        agentId: "builder",
        projectId: firstProjectId,
        title: "Build the first ppx-client shell",
        updatedAt: now(),
        lastMessagePreview: "Start from a local-first Electron desktop shell.",
      },
    ],
    operator: [
      {
        id: "operator-session-1",
        agentId: "operator",
        title: "Runtime diagnostics",
        updatedAt: now(),
        lastMessagePreview: "Local runtime is healthy and waiting.",
      },
    ],
  },
  messagesBySession: {
    [firstSessionId]: [
      {
        id: "msg-welcome",
        sessionId: firstSessionId,
        role: "assistant",
        status: "completed",
        createdAt: now(),
        parts: [
          {
            type: "markdown",
            text: "### Ready for local mode\n\nChoose an agent, open a session, and send a task. This first version keeps the machine model but runs everything locally.",
          },
          {
            type: "step_ref",
            stepId: "boot-local",
            title: "Local adapter online",
            status: "completed",
            detail: "The initial client uses an Electron-hosted local adapter so the UI contract stays stable while the real runtime API is added.",
          },
        ],
      },
    ],
    "operator-session-1": [
      {
        id: "msg-operator",
        sessionId: "operator-session-1",
        role: "assistant",
        status: "completed",
        createdAt: now(),
        parts: [
          {
            type: "markdown",
            text: "Runtime diagnostics are available here. The first version focuses on status, sessions, and chat.",
          },
        ],
      },
    ],
  },
  selectedAgentId: firstAgentId,
  selectedSessionId: firstSessionId,
};

let listeners = new Set<EventSink>();

function emit(event: RunEvent): void {
  listeners.forEach((listener) => listener(event));
}

function getSessions(agentId: string): SessionSummary[] {
  return [...(state.sessionsByAgent[agentId] ?? [])].sort((left, right) =>
    right.updatedAt.localeCompare(left.updatedAt),
  );
}

function getMessages(sessionId: string): ChatMessage[] {
  return [...(state.messagesBySession[sessionId] ?? [])];
}

function createAssistantMessage(sessionId: string): ChatMessage {
  return {
    id: `assistant-${crypto.randomUUID()}`,
    sessionId,
    role: "assistant",
    status: "streaming",
    createdAt: now(),
    parts: [],
  };
}

function formatReplyParts(text: string): MessagePart[] {
  const trimmed = text.trim();
  return [
    {
      type: "markdown",
      text: `我已经收到任务：**${trimmed || "未命名任务"}**。\n\n第一版客户端目前通过本地模式连接运行时，所以我会先在本机完成执行与反馈。`,
    },
    {
      type: "step_ref",
      stepId: `step-${crypto.randomUUID()}`,
      title: "Analyze request",
      status: "completed",
      detail: "Parsed the request and selected the local-only execution path.",
    },
    {
      type: "tool_result",
      toolName: "client_api_hint",
      summary: "本地 client-api 启动命令已经准备好了。",
      detail: "这只是一个 mock 示例，用来预览 tool response 卡片的展示效果。",
      rawText: JSON.stringify({ command: "ppx client-api serve --host 127.0.0.1 --port 8876" }, null, 2),
    },
    {
      type: "file",
      text: "Planned artifact",
      fileName: "client_session_notes.md",
      mimeType: "text/markdown",
      sizeBytes: 2048,
    },
    {
      type: "image",
      text: "Runtime architecture preview",
      url:
        "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='640' height='360'><rect width='100%25' height='100%25' rx='28' fill='%23f3f4f6'/><rect x='28' y='28' width='180' height='64' rx='18' fill='%23ffffff' stroke='%23d1d5db'/><text x='48' y='68' font-size='22' fill='%23111827'>Client</text><rect x='230' y='120' width='180' height='64' rx='18' fill='%23ffffff' stroke='%23d1d5db'/><text x='250' y='160' font-size='22' fill='%23111827'>Gateway</text><rect x='432' y='212' width='180' height='64' rx='18' fill='%23ffffff' stroke='%23d1d5db'/><text x='452' y='252' font-size='22' fill='%23111827'>Agent</text><path d='M208 60 C250 80 250 120 230 152' stroke='%236b7280' stroke-width='4' fill='none'/><path d='M410 152 C452 174 452 212 432 244' stroke='%236b7280' stroke-width='4' fill='none'/></svg>",
      mimeType: "image/svg+xml",
    },
  ];
}

export async function bootstrap(): Promise<BootstrapPayload> {
  return {
    runtime: state.runtime,
    agents: [...state.agents],
    sessions: getSessions(state.selectedAgentId),
    messages: getMessages(state.selectedSessionId),
    selectedAgentId: state.selectedAgentId,
    selectedSessionId: state.selectedSessionId,
  };
}

export async function runRuntimeCommand(command: RuntimeCommand): Promise<RuntimeStatus> {
  if (command === "start") {
    state.runtime = {
      ...state.runtime,
      state: "healthy",
      summary: "Local openppx runtime is running.",
      detail: "The local adapter is ready to serve sessions and message streams.",
      lastError: undefined,
    };
  } else if (command === "stop") {
    state.runtime = {
      ...state.runtime,
      state: "stopped",
      summary: "Local openppx runtime is stopped.",
      detail: "Start it again from the runtime card to continue chatting.",
    };
  } else {
    state.runtime = {
      ...state.runtime,
      state: "healthy",
      summary: "Local openppx runtime restarted.",
      detail: "The runtime card restarted the local adapter successfully.",
      lastError: undefined,
    };
  }
  return state.runtime;
}

export async function createSession(agentId: string, projectId?: string): Promise<{ session: SessionSummary }> {
  const session: SessionSummary = {
    id: `${agentId}-${crypto.randomUUID()}`,
    agentId,
    projectId,
    title: "新对话",
    updatedAt: now(),
    lastMessagePreview: "",
  };
  state.sessionsByAgent[agentId] = [session, ...(state.sessionsByAgent[agentId] ?? [])];
  state.messagesBySession[session.id] = [];
  state.selectedAgentId = agentId;
  state.selectedSessionId = session.id;
  if (projectId) {
    state.projects = state.projects.map((project) =>
      project.id === projectId
        ? { ...project, sessionsCount: project.sessionsCount + 1, updatedAt: session.updatedAt }
        : project,
    );
  }
  return { session };
}

export async function listSessions(agentId: string): Promise<{ sessions: SessionSummary[] }> {
  return { sessions: getSessions(agentId) };
}

export async function loadSession(sessionId: string): Promise<{ messages: ChatMessage[] }> {
  return { messages: getMessages(sessionId) };
}

export async function getDiagnostics(): Promise<ClientDiagnostics> {
  return {
    mode: "mock",
    target: { id: "mock-default", type: "local", name: "Mock Runtime" },
    openppxRoot: "",
    openppxRootExists: false,
    pythonBin: "",
    globalConfigPath: "",
    globalConfigExists: false,
    clientApiBaseUrl: "http://127.0.0.1:8876",
    clientApiManagedByClient: false,
    clientApiHealthy: false,
    clientApiProcessRunning: false,
    agentCount: state.agents.length,
    sessionCacheEntries: 0,
    messageCacheEntries: 0,
    debugEnabled: false,
  };
}

export async function saveConnectionSettings(_settings: ConnectionSettings): Promise<ClientDiagnostics> {
  return getDiagnostics();
}

export async function listGmScienceProjects(): Promise<{ projects: GmScienceProject[] }> {
  return { projects: state.projects.map((project) => ({ ...project })) };
}

export async function createGmScienceProject(
  input: CreateGmScienceProjectInput,
): Promise<{ project: GmScienceProject }> {
  const project: GmScienceProject = {
    id: `proj_${crypto.randomUUID()}`,
    name: input.name.trim(),
    description: input.description ?? "",
    agentContext: input.agentContext ?? "",
    workspacePath: `~/.gm-science/workspaces/proj_${crypto.randomUUID()}`,
    sessionsCount: 0,
    artifactsCount: 0,
    enabledSkills: input.enabledSkills ?? ["literature-review"],
    enabledConnectors: input.enabledConnectors ?? ["arxiv", "pubmed", "openalex"],
    enabledSpecialists: input.enabledSpecialists ?? ["paper_reader", "research_reviewer"],
    createdAt: now(),
    updatedAt: now(),
  };
  state.projects = [project, ...state.projects];
  state.artifactsByProject[project.id] = [];
  state.datasetsByProject[project.id] = [];
  state.analysesByProject[project.id] = [];
  state.runsByProject[project.id] = [];
  return { project };
}

export async function getGmScienceProject(projectId: string): Promise<{ project: GmScienceProject }> {
  const project = state.projects.find((item) => item.id === projectId);
  if (!project) {
    throw new Error(`Project ${projectId} was not found.`);
  }
  return { project: { ...project } };
}

const capabilityDefinitions: Omit<GmScienceCapability, "projectEnabled">[] = [
  {
    id: "literature-review",
    kind: "skill",
    name: "Literature Review",
    description: "Search scholarly sources, build an evidence matrix, and register a cited review in gm-science.",
    source: "built_in",
    version: "",
    license: "",
    files: ["SKILL.md"],
    available: true,
    defaultEnabled: true,
    status: "ready",
    statusDetail: "",
    metadata: { registry_source: "builtin", file_count: 1, files_truncated: false },
  },
  {
    id: "docx",
    kind: "skill",
    name: "DOCX",
    description: "Create and edit Word documents.",
    source: "built_in",
    version: "",
    license: "Proprietary",
    files: ["LICENSE.txt", "SKILL.md"],
    available: true,
    defaultEnabled: false,
    status: "ready",
    statusDetail: "",
    metadata: { registry_source: "builtin", file_count: 2, files_truncated: false },
  },
  {
    id: "local-analysis",
    kind: "skill",
    name: "Local Analysis",
    description: "Analyze local tabular datasets.",
    source: "local",
    version: "0.1.0",
    license: "Private",
    files: ["SKILL.md", "scripts/analyze.py"],
    available: true,
    defaultEnabled: false,
    status: "ready",
    statusDetail: "",
    metadata: { registry_source: "workspace", file_count: 2, files_truncated: false },
  },
  {
    id: "arxiv",
    kind: "connector",
    name: "arXiv",
    description: "Search open-access preprints across scientific and technical fields.",
    source: "built_in",
    version: "",
    license: "",
    files: [],
    available: true,
    defaultEnabled: true,
    status: "ready",
    statusDetail: "",
    metadata: {},
  },
  {
    id: "pubmed",
    kind: "connector",
    name: "PubMed",
    description: "Search biomedical literature indexed by the NCBI PubMed service.",
    source: "built_in",
    version: "",
    license: "",
    files: [],
    available: true,
    defaultEnabled: true,
    status: "needs_configuration",
    statusDetail: "Set science.literature.pubmed.email.",
    metadata: {},
  },
  {
    id: "openalex",
    kind: "connector",
    name: "OpenAlex",
    description: "Search scholarly works and citation metadata from OpenAlex.",
    source: "built_in",
    version: "",
    license: "",
    files: [],
    available: true,
    defaultEnabled: true,
    status: "needs_configuration",
    statusDetail: "Set science.literature.openalex.apiKey.",
    metadata: {},
  },
  {
    id: "mcp:filesystem",
    kind: "connector",
    name: "Filesystem",
    description: "Configured MCP server over stdio.",
    source: "local",
    version: "",
    license: "",
    files: [],
    available: true,
    defaultEnabled: false,
    status: "ready",
    statusDetail: "Configured; connection is verified when runtime tools load.",
    metadata: {
      connector_type: "mcp",
      server_name: "filesystem",
      transport: "stdio",
      tool_prefix: "science_fs",
      tool_filter: ["read_file", "list_directory"],
      require_confirmation: true,
      progress_events: false,
      long_task_proxy: true,
      inline_budget_ms: 5000,
      job_protocol: false,
      command_name: "mcp-filesystem",
      endpoint_origin: "",
      configured_env_names: ["FILESYSTEM_TOKEN", "WORKSPACE_ROOT"],
      configured_header_names: [],
      runtime_header_names: ["X-Project-Id"],
    },
  },
  {
    id: "paper_reader",
    kind: "specialist",
    name: "Paper Reader",
    description: "Analyze saved paper artifacts and compare evidence across papers.",
    source: "built_in",
    version: "",
    license: "",
    files: [],
    available: true,
    defaultEnabled: true,
    status: "ready",
    statusDetail: "",
    metadata: { auto_dispatch: true, read_only: true },
  },
  {
    id: "research_reviewer",
    kind: "specialist",
    name: "Research Reviewer",
    description: "Review saved reports and reading notes with findings-first critique.",
    source: "built_in",
    version: "",
    license: "",
    files: [],
    available: true,
    defaultEnabled: true,
    status: "ready",
    statusDetail: "",
    metadata: { auto_dispatch: true, read_only: true },
  },
];

function projectCapabilityIds(project: GmScienceProject, kind: GmScienceCapability["kind"]): string[] {
  if (kind === "skill") {
    return project.enabledSkills;
  }
  if (kind === "connector") {
    return project.enabledConnectors;
  }
  return project.enabledSpecialists;
}

export async function listGmScienceCapabilities(projectId?: string): Promise<GmScienceCapabilityCatalog> {
  const project = projectId ? state.projects.find((item) => item.id === projectId) : undefined;
  if (projectId && !project) {
    throw new Error(`Project ${projectId} was not found.`);
  }
  return {
    projectId: project?.id ?? "",
    items: capabilityDefinitions.map((item) => ({
      ...item,
      metadata: { ...item.metadata },
      projectEnabled: project ? projectCapabilityIds(project, item.kind).includes(item.id) : null,
    })),
  };
}

export async function updateGmScienceProjectCapabilities(
  projectId: string,
  input: UpdateGmScienceCapabilitiesInput,
): Promise<{ project: GmScienceProject; capabilities: GmScienceCapability[] }> {
  const projectIndex = state.projects.findIndex((item) => item.id === projectId);
  if (projectIndex < 0) {
    throw new Error(`Project ${projectId} was not found.`);
  }
  const project = {
    ...state.projects[projectIndex],
    enabledSkills: [...input.enabledSkills],
    enabledConnectors: [...input.enabledConnectors],
    enabledSpecialists: [...input.enabledSpecialists],
    updatedAt: now(),
  };
  state.projects[projectIndex] = project;
  const catalog = await listGmScienceCapabilities(projectId);
  return { project: { ...project }, capabilities: catalog.items };
}

export async function listGmScienceArtifacts(projectId: string): Promise<{ artifacts: GmScienceArtifact[] }> {
  return { artifacts: (state.artifactsByProject[projectId] ?? []).map((artifact) => ({ ...artifact })) };
}

export async function createGmScienceArtifact(
  projectId: string,
  input: CreateGmScienceArtifactInput,
): Promise<{ artifact: GmScienceArtifact }> {
  const artifacts = state.artifactsByProject[projectId] ?? [];
  const artifact: GmScienceArtifact = {
    id: `art_${crypto.randomUUID()}`,
    projectId,
    sessionId: input.sessionId ?? "",
    type: input.type,
    title: input.title,
    pathOrUrl: input.pathOrUrl ?? "",
    mimeType: input.mimeType ?? "",
    metadata: input.metadata ?? {},
    provenance: input.provenance ?? { created_by: "mock-client" },
    createdAt: now(),
    updatedAt: now(),
  };
  state.artifactsByProject[projectId] = [artifact, ...artifacts];
  state.projects = state.projects.map((project) =>
    project.id === projectId
      ? {
          ...project,
          artifactsCount: (state.artifactsByProject[projectId] ?? []).length,
          updatedAt: artifact.updatedAt,
        }
      : project,
  );
  return { artifact };
}

export async function listGmScienceRuns(projectId: string): Promise<{ runs: GmScienceRun[] }> {
  return { runs: (state.runsByProject[projectId] ?? []).map((run) => ({ ...run })) };
}

export async function getGmScienceRun(projectId: string, taskId: string): Promise<{ run: GmScienceRun }> {
  const run = (state.runsByProject[projectId] ?? []).find((item) => item.taskId === taskId);
  if (!run) {
    throw new Error(`Run ${taskId} was not found.`);
  }
  return { run: { ...run } };
}

export async function createGmSciencePythonRun(
  projectId: string,
  input: CreateGmSciencePythonRunInput,
): Promise<{ run: GmScienceRun }> {
  const timestamp = now();
  const run: GmScienceRun = {
    taskId: `task_${crypto.randomUUID()}`,
    projectId,
    sessionId: input.sessionId ?? "",
    parentTaskId: "",
    kind: "local_python",
    title: input.title || "Python run",
    status: "completed",
    progressSummary: "Mock Python run completed.",
    terminalSummary: "Mock Python run completed.",
    lastError: "",
    createdAt: timestamp,
    updatedAt: timestamp,
    createdAtMs: Date.now(),
    updatedAtMs: Date.now(),
    endedAtMs: Date.now(),
    canCancel: false,
    canRetry: true,
    logPreview: "[stdout] Mock Python run completed.\n",
    artifactIds: [],
  };
  state.runsByProject[projectId] = [run, ...(state.runsByProject[projectId] ?? [])];
  return { run: { ...run } };
}

export async function cancelGmScienceRun(projectId: string, taskId: string): Promise<{ run: GmScienceRun }> {
  const payload = await getGmScienceRun(projectId, taskId);
  const run = { ...payload.run, status: "cancelled" as const, canCancel: false, canRetry: true, endedAtMs: Date.now() };
  state.runsByProject[projectId] = (state.runsByProject[projectId] ?? []).map((item) =>
    item.taskId === taskId ? run : item,
  );
  return { run };
}

export async function retryGmScienceRun(projectId: string, taskId: string): Promise<{ run: GmScienceRun }> {
  const previous = (await getGmScienceRun(projectId, taskId)).run;
  const created = await createGmSciencePythonRun(projectId, {
    title: previous.title,
    source: "print('mock retry')",
    sessionId: previous.sessionId,
  });
  const run = { ...created.run, parentTaskId: taskId };
  state.runsByProject[projectId] = (state.runsByProject[projectId] ?? []).map((item) =>
    item.taskId === run.taskId ? run : item,
  );
  return { run };
}

export async function selectGmScienceDatasetFile(): Promise<null> {
  return null;
}

export async function listGmScienceDatasets(projectId: string): Promise<{ datasets: GmScienceDataset[] }> {
  return { datasets: (state.datasetsByProject[projectId] ?? []).map((dataset) => ({ ...dataset })) };
}

export async function getGmScienceDataset(
  projectId: string,
  artifactId: string,
): Promise<{ dataset: GmScienceDataset }> {
  const dataset = (state.datasetsByProject[projectId] ?? []).find((item) => item.artifactId === artifactId);
  if (!dataset) {
    throw new Error(`Dataset ${artifactId} was not found.`);
  }
  return { dataset: { ...dataset } };
}

export async function importGmScienceDataset(
  projectId: string,
  input: ImportGmScienceDatasetInput,
): Promise<{ dataset: GmScienceDataset }> {
  const timestamp = now();
  const artifactId = `art_dataset_${crypto.randomUUID()}`;
  const title = input.title?.trim() || input.sourcePath.split(/[\\/]/).pop()?.replace(/\.[^.]+$/, "") || "Dataset";
  const dataset: GmScienceDataset = {
    artifactId,
    projectId,
    sessionId: input.sessionId ?? "",
    title,
    path: input.sourcePath,
    mimeType: "text/csv",
    format: "csv",
    sourceName: input.sourcePath.split(/[\\/]/).pop() ?? "dataset.csv",
    sizeBytes: 128,
    rowCount: 4,
    profiledRowCount: 4,
    columnCount: 3,
    columnNames: ["group", "x", "y"],
    profileArtifactId: `art_profile_${crypto.randomUUID()}`,
    profile: {
      version: 1,
      format: "csv",
      rowCount: 4,
      profiledRowCount: 4,
      columnCount: 3,
      columns: [
        {
          name: "group",
          inferredType: "string",
          nonNullCount: 4,
          missingCount: 0,
          missingFraction: 0,
          uniqueCount: 2,
          uniqueCountCapped: false,
          typeCounts: { string: 4 },
          topValues: [{ value: "A", count: 2 }, { value: "B", count: 2 }],
        },
        ...["x", "y"].map((name) => ({
          name,
          inferredType: "number",
          nonNullCount: 4,
          missingCount: 0,
          missingFraction: 0,
          uniqueCount: 4,
          uniqueCountCapped: false,
          typeCounts: { number: 4 },
          topValues: [],
          numeric: { count: 4, min: 1, max: 4, mean: 2.5, standardDeviation: 1.29 },
        })),
      ],
      preview: [{ group: "A", x: 1, y: 2 }],
      warnings: [],
    },
    createdAt: timestamp,
    updatedAt: timestamp,
  };
  state.datasetsByProject[projectId] = [dataset, ...(state.datasetsByProject[projectId] ?? [])];
  const artifact: GmScienceArtifact = {
    id: artifactId,
    projectId,
    sessionId: input.sessionId ?? "",
    type: "dataset",
    title,
    pathOrUrl: input.sourcePath,
    mimeType: "text/csv",
    metadata: { row_count: 4, column_count: 3, dataset_format: "csv" },
    provenance: { created_by: "mock-dataset-importer" },
    createdAt: timestamp,
    updatedAt: timestamp,
  };
  state.artifactsByProject[projectId] = [artifact, ...(state.artifactsByProject[projectId] ?? [])];
  return { dataset: { ...dataset } };
}

export async function listGmScienceAnalyses(projectId: string): Promise<{ analyses: GmScienceAnalysis[] }> {
  return { analyses: (state.analysesByProject[projectId] ?? []).map((analysis) => ({ ...analysis })) };
}

export async function getGmScienceAnalysis(
  projectId: string,
  analysisId: string,
): Promise<{ analysis: GmScienceAnalysis }> {
  const analysis = (state.analysesByProject[projectId] ?? []).find((item) => item.id === analysisId);
  if (!analysis) {
    throw new Error(`Analysis ${analysisId} was not found.`);
  }
  return { analysis: { ...analysis } };
}

export async function createGmScienceAnalysis(
  projectId: string,
  input: CreateGmScienceAnalysisInput,
): Promise<{ analysis: GmScienceAnalysis }> {
  const timestamp = now();
  const analysis: GmScienceAnalysis = {
    id: `analysis_${crypto.randomUUID()}`,
    projectId,
    sessionId: input.sessionId ?? "",
    title: input.title?.trim() || input.objective,
    objective: input.objective,
    datasetArtifactIds: [...input.datasetArtifactIds],
    plan: {
      version: 1,
      objective: input.objective,
      operations: ["data_quality", "descriptive_statistics", "distribution"],
      steps: [
        { id: "data_quality", title: "Data Quality", description: "Count missing values and type coverage." },
        { id: "descriptive_statistics", title: "Descriptive Statistics", description: "Summarize numeric columns." },
        { id: "distribution", title: "Distribution", description: "Render a numeric histogram." },
      ],
      datasets: [],
      assumptions: ["Missing values are excluded per calculation."],
      warnings: [],
    },
    source: "# Generated by gm-science\nprint('mock analysis')\n",
    taskId: "",
    status: "draft",
    run: null,
    reportArtifactId: "",
    figureArtifactIds: [],
    artifactIds: [],
    createdAt: timestamp,
    updatedAt: timestamp,
  };
  state.analysesByProject[projectId] = [analysis, ...(state.analysesByProject[projectId] ?? [])];
  return { analysis: { ...analysis } };
}

export async function runGmScienceAnalysis(
  projectId: string,
  analysisId: string,
): Promise<{ analysis: GmScienceAnalysis }> {
  const current = (await getGmScienceAnalysis(projectId, analysisId)).analysis;
  if (current.taskId) {
    throw new Error(`Analysis ${analysisId} has already been approved for execution.`);
  }
  const createdRun = (await createGmSciencePythonRun(projectId, {
    title: current.title,
    source: current.source ?? "",
    sessionId: current.sessionId,
  })).run;
  const run: GmScienceRun = { ...createdRun, kind: "data_analysis" };
  state.runsByProject[projectId] = (state.runsByProject[projectId] ?? []).map((item) =>
    item.taskId === run.taskId ? run : item,
  );
  const updated: GmScienceAnalysis = {
    ...current,
    taskId: run.taskId,
    status: run.status,
    run,
    updatedAt: now(),
  };
  state.analysesByProject[projectId] = (state.analysesByProject[projectId] ?? []).map((item) =>
    item.id === analysisId ? updated : item,
  );
  return { analysis: updated };
}

export function subscribe(listener: EventSink): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export async function sendMessage(input: SendMessageInput): Promise<{ runId: string }> {
  const runId = `run-${crypto.randomUUID()}`;
  const userMessage: ChatMessage = {
    id: `user-${crypto.randomUUID()}`,
    sessionId: input.sessionId,
    role: "user",
    status: "completed",
    createdAt: now(),
    parts: [{ type: "markdown", text: input.text }],
  };
  const sessionList = state.sessionsByAgent[input.agentId] ?? [];
  const session = sessionList.find((item) => item.id === input.sessionId);
  if (session) {
    session.updatedAt = now();
    if (isGenericSessionTitle(session.title)) {
      session.title = compactSessionTitle(input.text);
    }
    session.lastMessagePreview = input.text.trim() || "Empty message";
  }
  state.messagesBySession[input.sessionId] = [...getMessages(input.sessionId), userMessage];
  const assistant = createAssistantMessage(input.sessionId);
  state.messagesBySession[input.sessionId] = [...state.messagesBySession[input.sessionId], assistant];
  emit({
    type: "message.created",
    runId,
    sessionId: input.sessionId,
    message: assistant,
  });

  const parts = formatReplyParts(input.text);
  parts.forEach((part, index) => {
    setTimeout(() => {
      emit({
        type: "message.updated",
        runId,
        sessionId: input.sessionId,
        messageId: assistant.id,
        appendParts: [part],
        status: index === parts.length - 1 ? "completed" : "streaming",
      });
      if (index === parts.length - 1 && session) {
        session.updatedAt = now();
        session.lastMessagePreview = "Assistant replied with local runtime guidance.";
        emit({
          type: "session.updated",
          runId,
          session: { ...session },
        });
        emit({
          type: "run.finished",
          runId,
          sessionId: input.sessionId,
        });
      }
    }, 250 * (index + 1));
  });

  return { runId };
}
