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
  CreateGmScienceMemoryNoteInput,
  GmScienceArtifact,
  GmScienceAnalysis,
  GmScienceCapability,
  GmScienceCapabilityCatalog,
  GmScienceProject,
  GmScienceResource,
  GmScienceResourceDetail,
  GmScienceDataset,
  GmScienceRun,
  GmScienceSessionPolicy,
  GmScienceSessionPolicyValues,
  GmScienceSettings,
  GmScienceSettingsUpdateResult,
  GmScienceStorageSnapshot,
  GmScienceUsageSnapshot,
  GmScienceUsageWindow,
  GmScienceComputeHealth,
  GmScienceMemoryCandidate,
  GmScienceMemoryNote,
  GmScienceMemoryScope,
  GmScienceMemoryWorkspace,
  ImportGmScienceDatasetInput,
  MessagePart,
  RuntimeCommand,
  RuntimeStatus,
  RunEvent,
  SendMessageInput,
  SessionSummary,
  UpdateGmScienceCapabilitiesInput,
  UpdateGmScienceSessionPolicyInput,
  UpdateGmScienceSettingsInput,
  UpdateGmScienceMemoryNoteInput,
} from "../types";

interface StoreState {
  runtime: RuntimeStatus;
  agents: AgentProfile[];
  settings: GmScienceSettings;
  storage: GmScienceStorageSnapshot;
  usage: GmScienceUsageSnapshot;
  memoryByProject: Record<string, GmScienceMemoryWorkspace>;
  projects: GmScienceProject[];
  artifactsByProject: Record<string, GmScienceArtifact[]>;
  datasetsByProject: Record<string, GmScienceDataset[]>;
  analysesByProject: Record<string, GmScienceAnalysis[]>;
  runsByProject: Record<string, GmScienceRun[]>;
  sessionsByAgent: Record<string, SessionSummary[]>;
  messagesBySession: Record<string, ChatMessage[]>;
  sessionPoliciesBySession: Record<string, GmScienceSessionPolicyValues>;
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
    normalized === "New session" ||
    normalized.startsWith("Session ")
  );
}

const firstAgentId = "science-research";
const firstSessionId = "science-research-session-1";
const firstProjectId = "proj_mock_research";
let memoryNoteSequence = 0;

const DEFAULT_SESSION_POLICY: GmScienceSessionPolicyValues = {
  delegationEnabled: false,
  autoReviewEnabled: false,
  memoryEnabled: false,
  specialistId: "",
  reviewerModel: "default",
  computeTarget: "local",
};

function cloneSessionPolicyValues(
  policy: Partial<GmScienceSessionPolicyValues> = {},
): GmScienceSessionPolicyValues {
  return { ...DEFAULT_SESSION_POLICY, ...policy };
}

const state: StoreState = {
  runtime: {
    target: {
      id: "local-default",
      type: "local",
      name: "This Mac",
    },
    state: "healthy",
    summary: "Local gm-science runtime is ready.",
    detail: "The local personal research agent is ready.",
  },
  agents: [
    {
      id: firstAgentId,
      name: "gm-science",
      description: "Local personal research agent.",
      provider: "openai_codex",
      model: "openai-codex/gpt-5.5",
      enabled: true,
      status: "healthy",
      tags: ["local", "science"],
    },
  ],
  settings: {
    model: { provider: "openai_codex", model: "openai-codex/gpt-5.5" },
    memory: { enabled: true },
    providers: [
      { id: "openai_codex", name: "OpenAI Codex", defaultModel: "openai-codex/gpt-5.5", authType: "oauth", credentialRequired: true, credentialConfigured: true, credentialSource: "oauth_cache", active: true },
      { id: "openai", name: "OpenAI", defaultModel: "openai/gpt-5.4", authType: "api_key", credentialRequired: true, credentialConfigured: false, credentialSource: "none", active: false },
      { id: "google", name: "Google Gemini", defaultModel: "gemini-3-flash-preview", authType: "api_key", credentialRequired: true, credentialConfigured: false, credentialSource: "none", active: false },
      { id: "anthropic", name: "Anthropic", defaultModel: "claude-3-7-sonnet", authType: "api_key", credentialRequired: true, credentialConfigured: false, credentialSource: "none", active: false },
      { id: "custom", name: "Custom OpenAI-Compatible", defaultModel: "openai/gpt-5.4", authType: "optional_api_key", credentialRequired: false, credentialConfigured: false, credentialSource: "none", active: false },
      { id: "vllm", name: "vLLM/Local", defaultModel: "meta-llama/Llama-3.1-8B-Instruct", authType: "optional_api_key", credentialRequired: false, credentialConfigured: false, credentialSource: "none", active: false },
    ],
    permissions: {
      items: [
        ["create_agent", "Create agent", "Create a persistent specialist Agent definition."],
        ["update_agent", "Update agent", "Update or attach a persistent specialist Agent definition."],
        ["publish_skill", "Publish skill", "Publish a Skill into the local registry."],
        ["edit_skill", "Edit skill", "Modify a Skill already stored in the local registry."],
        ["attach_skill", "Attach skill", "Attach a Skill to a Project."],
        ["detach_skill", "Detach skill", "Detach a Skill from a Project."],
        ["attach_connector", "Attach connector", "Attach a Connector to a Project."],
        ["detach_connector", "Detach connector", "Detach a Connector from a Project."],
      ].map(([id, name, description]) => ({
        id,
        name,
        description,
        category: "registry_writes" as const,
        granted: true,
        scope: "global" as const,
        source: "default" as const,
        updatedAt: "",
      })),
    },
    network: {
      enabled: true,
      enforceAllowlist: true,
      allowPrivateNetworks: false,
      packageMirrors: { condaChannelMirror: "", pythonPackageIndex: "", caBundlePath: "" },
      categories: [
        { id: "package_management", name: "Package management", description: "Package and source repositories.", enabled: true, domains: ["pypi.org", "github.com"] },
        { id: "research_data", name: "Research data", description: "Public scientific data services.", enabled: true, domains: ["export.arxiv.org", "eutils.ncbi.nlm.nih.gov", "api.openalex.org"] },
        { id: "model_providers", name: "Model providers", description: "Language and scientific model APIs.", enabled: true, domains: ["chatgpt.com", "api.openai.com"] },
        { id: "cloud_compute", name: "Cloud compute", description: "Optional compute providers.", enabled: true, domains: ["modal.com", "integrate.api.nvidia.com"] },
        { id: "configured_connectors", name: "Configured Connectors", description: "Configured remote MCP domains.", enabled: true, domains: [] },
      ],
      customDomains: [],
      enforcementBoundary: "Applied to gm-science managed network boundaries; not process-level isolation.",
    },
    compute: {
      targets: [
        { id: "local", type: "local", name: "This computer", enabled: true, configured: true, executable: true, status: "ready", statusDetail: "Managed local Python TaskRun.", metadata: {} },
        { id: "modal", type: "cloud_provider", name: "Modal", enabled: true, configured: false, executable: false, status: "needs_configuration", statusDetail: "Serverless GPU provider; execution adapter is not implemented.", metadata: {} },
        { id: "nvidia_bionemo_nim", type: "model_endpoint", name: "NVIDIA BioNeMo NIM", enabled: true, configured: false, executable: false, status: "needs_configuration", statusDetail: "Scientific model endpoint; execution adapter is not implemented.", metadata: {} },
      ],
    },
    literature: {
      arxiv: { status: "ready", statusDetail: "" },
      pubmed: { email: "", apiKeyConfigured: false, status: "needs_configuration", statusDetail: "Add a PubMed contact email." },
      openalex: { apiKeyConfigured: false, status: "needs_configuration", statusDetail: "Add an OpenAlex API key." },
    },
  },
  storage: {
    dataLocation: "~/.gm-science",
    exists: true,
    writable: true,
    scannedAt: now(),
    scanComplete: true,
    partialReason: "",
    entriesScanned: 73,
    elapsedMs: 5,
    totalBytes: 3_145_728,
    totalFiles: 54,
    categories: [
      { id: "workspaces", name: "Workspaces", bytes: 1_572_864, files: 19 },
      { id: "databases", name: "Databases", bytes: 1_048_576, files: 8 },
      { id: "cache", name: "Cache", bytes: 393_216, files: 17 },
      { id: "configuration", name: "Agent configuration", bytes: 65_536, files: 7 },
      { id: "logs", name: "Logs", bytes: 65_536, files: 3 },
      { id: "other", name: "Other", bytes: 0, files: 0 },
    ],
    issues: [],
    cloudStorage: {
      supported: false,
      configured: false,
      detail: "No cloud storage adapter is available in this build.",
    },
  },
  usage: {
    window: "7d",
    generatedAt: now(),
    since: now(),
    until: now(),
    localEstimate: true,
    cost: {
      available: false,
      reason: "Provider pricing and invoice reconciliation are not configured.",
    },
    tokens: {
      recordingStarted: true,
      requests: 4,
      inputTokens: 8_400,
      outputTokens: 1_920,
      inputTextTokens: 8_400,
      outputTextTokens: 1_920,
      inputImageTokens: 0,
      outputImageTokens: 0,
      totalTokens: 10_320,
      byModel: [
        {
          provider: "openai_codex",
          model: "openai-codex/gpt-5.5",
          requests: 4,
          inputTokens: 8_400,
          outputTokens: 1_920,
          totalTokens: 10_320,
        },
      ],
    },
    runs: {
      recordingStarted: true,
      runs: 2,
      activeRuns: 0,
      terminalRuns: 2,
      runtimeMs: 42_000,
      byStatus: [{ status: "completed", runs: 2, runtimeMs: 42_000 }],
      byKind: [{ kind: "data_analysis", runs: 2, runtimeMs: 42_000 }],
    },
  },
  memoryByProject: {
    [firstProjectId]: {
      projectId: firstProjectId,
      notes: [],
      candidates: [
        {
          id: "memory-candidate-1",
          scope: "project",
          category: "Project context",
          text: "Use GRCh38 for genome references.",
          rationale: "A durable convention stated for this Project.",
          status: "pending",
          projectId: firstProjectId,
          sourceSessionId: firstSessionId,
          model: "openai-codex/gpt-5.5",
          approvedNoteId: "",
          createdAt: now(),
          reviewedAt: "",
        },
      ],
      categories: ["Project context"],
    },
  },
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
      sessionPolicyDefaults: cloneSessionPolicyValues(),
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
    [firstAgentId]: [
      {
        id: firstSessionId,
        agentId: firstAgentId,
        projectId: firstProjectId,
        title: "Review recent literature",
        updatedAt: now(),
        lastMessagePreview: "Find and compare the most relevant evidence.",
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
            text: "### Ready for research\n\nStart with a research question, paper, dataset, or protocol.",
          },
          {
            type: "step_ref",
            stepId: "boot-local",
            title: "Research workspace ready",
            status: "completed",
            detail: "Project files, scientific sources, specialists, and reviewed analyses are available in this workspace.",
          },
        ],
      },
    ],
  },
  sessionPoliciesBySession: {
    [firstSessionId]: cloneSessionPolicyValues(),
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
      summary: "Local gm-science runtime is running.",
      detail: "The local adapter is ready to serve sessions and message streams.",
      lastError: undefined,
    };
  } else if (command === "stop") {
    state.runtime = {
      ...state.runtime,
      state: "stopped",
      summary: "Local gm-science runtime is stopped.",
      detail: "Start it again from the runtime card to continue chatting.",
    };
  } else {
    state.runtime = {
      ...state.runtime,
      state: "healthy",
      summary: "Local gm-science runtime restarted.",
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
    title: "New session",
    updatedAt: now(),
    lastMessagePreview: "",
  };
  state.sessionsByAgent[agentId] = [session, ...(state.sessionsByAgent[agentId] ?? [])];
  state.messagesBySession[session.id] = [];
  const project = state.projects.find((item) => item.id === projectId);
  state.sessionPoliciesBySession[session.id] = cloneSessionPolicyValues(project?.sessionPolicyDefaults);
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
    sessionPolicyDefaults: cloneSessionPolicyValues(input.sessionPolicyDefaults),
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

function buildMockSessionPolicy(sessionId: string): GmScienceSessionPolicy {
  const session = Object.values(state.sessionsByAgent).flat().find((item) => item.id === sessionId);
  const project = state.projects.find((item) => item.id === session?.projectId);
  const policy = state.sessionPoliciesBySession[sessionId];
  if (!session || !project || !policy) {
    throw new Error(`Session ${sessionId} is not attached to a Project.`);
  }
  const specialists = capabilityDefinitions
    .filter((item) => item.kind === "specialist" && item.id !== "research_reviewer")
    .filter((item) => project.enabledSpecialists.includes(item.id) && item.available && item.status === "ready")
    .map((item) => ({ id: item.id, name: item.name, description: item.description, status: item.status }));
  const reviewer = capabilityDefinitions.find((item) => item.id === "research_reviewer");
  return {
    sessionId,
    projectId: project.id,
    ...cloneSessionPolicyValues(policy),
    specialists,
    reviewerAvailable: Boolean(
      reviewer && project.enabledSpecialists.includes(reviewer.id) && reviewer.available && reviewer.status === "ready",
    ),
    reviewerModels: [{ id: "default", name: "Default" }],
    computeTargets: [{ id: "local", name: "Local" }],
    issues: [],
  };
}

export async function getGmScienceSessionPolicy(sessionId: string): Promise<GmScienceSessionPolicy> {
  return buildMockSessionPolicy(sessionId);
}

export async function updateGmScienceSessionPolicy(
  sessionId: string,
  input: UpdateGmScienceSessionPolicyInput,
): Promise<GmScienceSessionPolicy> {
  const current = buildMockSessionPolicy(sessionId);
  const next = cloneSessionPolicyValues({ ...current, ...input });
  if (next.specialistId && !current.specialists.some((item) => item.id === next.specialistId)) {
    throw new Error(`Specialist '${next.specialistId}' is not ready for this Project.`);
  }
  if (next.autoReviewEnabled && !current.reviewerAvailable) {
    throw new Error("Research Reviewer is not ready for this Project.");
  }
  state.sessionPoliciesBySession[sessionId] = next;
  return buildMockSessionPolicy(sessionId);
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
    metadata: {
      registry_source: "builtin",
      catalog_group: "featured",
      implementation_status: "installed",
      file_count: 1,
      files_truncated: false,
    },
  },
  {
    id: "boltz",
    kind: "skill",
    name: "Boltz",
    description: "Predict biomolecular structures and interactions with Boltz.",
    source: "built_in",
    version: "",
    license: "",
    files: [],
    available: false,
    defaultEnabled: false,
    status: "disabled",
    statusDetail: "Not available in this gm-science build.",
    metadata: {
      registry_source: "product_catalog",
      catalog_group: "featured",
      implementation_status: "not_installed",
    },
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
    metadata: {
      registry_source: "workspace",
      catalog_group: "personal",
      implementation_status: "installed",
      file_count: 2,
      files_truncated: false,
    },
  },
  {
    id: "biomart",
    kind: "connector",
    name: "BioMart",
    description: "Query federated biological datasets through BioMart.",
    source: "built_in",
    version: "",
    license: "",
    files: [],
    available: false,
    defaultEnabled: false,
    status: "disabled",
    statusDetail: "Not available in this gm-science build.",
    metadata: {
      registry_source: "product_catalog",
      catalog_group: "featured",
      implementation_status: "not_installed",
    },
  },
  {
    id: "arxiv",
    kind: "connector",
    name: "arXiv",
    description: "Search open-access preprints across scientific and technical fields.",
    source: "external",
    version: "",
    license: "",
    files: [],
    available: true,
    defaultEnabled: true,
    status: "ready",
    statusDetail: "",
    metadata: { catalog_group: "native", implementation_status: "native" },
  },
  {
    id: "pubmed",
    kind: "connector",
    name: "PubMed",
    description: "Search biomedical literature indexed by the NCBI PubMed service.",
    source: "external",
    version: "",
    license: "",
    files: [],
    available: true,
    defaultEnabled: true,
    status: "needs_configuration",
    statusDetail: "Set science.literature.pubmed.email.",
    metadata: { catalog_group: "directory", implementation_status: "native" },
  },
  {
    id: "openalex",
    kind: "connector",
    name: "OpenAlex",
    description: "Search scholarly works and citation metadata from OpenAlex.",
    source: "external",
    version: "",
    license: "",
    files: [],
    available: true,
    defaultEnabled: true,
    status: "needs_configuration",
    statusDetail: "Set science.literature.openalex.apiKey.",
    metadata: { catalog_group: "native", implementation_status: "native" },
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
      catalog_group: "custom",
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
    metadata: { catalog_group: "built_in", auto_dispatch: true, read_only: true },
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
    metadata: { catalog_group: "built_in", auto_dispatch: true, read_only: true },
  },
  {
    id: "literature_scout",
    kind: "specialist",
    name: "Literature Scout",
    description: "Find focused research evidence with assigned literature capabilities.",
    source: "local",
    version: "",
    license: "",
    files: [],
    available: true,
    defaultEnabled: false,
    status: "ready",
    statusDetail: "",
    metadata: {
      registry_source: "custom",
      catalog_group: "custom",
      auto_dispatch: false,
      read_only: true,
      network_access: true,
      shell_access: false,
      model: "inherit",
      assigned_skills: ["literature-review"],
      assigned_connectors: ["pubmed", "openalex"],
      execution_mode: "agent_tool",
      additional_instructions: "Prefer primary sources and state evidence limitations.",
    },
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

function cloneSettings(): GmScienceSettings {
  return structuredClone(state.settings);
}

export async function getGmScienceSettings(): Promise<GmScienceSettings> {
  return cloneSettings();
}

export async function getGmScienceStorage(): Promise<GmScienceStorageSnapshot> {
  return structuredClone(state.storage);
}

export async function getGmScienceUsage(window: GmScienceUsageWindow): Promise<GmScienceUsageSnapshot> {
  const usage = structuredClone(state.usage);
  usage.window = window;
  usage.generatedAt = now();
  usage.until = usage.generatedAt;
  const durationMs = window === "24h" ? 86_400_000 : window === "7d" ? 604_800_000 : 2_592_000_000;
  usage.since = new Date(Date.parse(usage.until) - durationMs).toISOString();
  return usage;
}

function applyMockSecretMutation(
  configured: boolean,
  mutation: UpdateGmScienceSettingsInput["providerApiKey"],
): boolean {
  if (!mutation) {
    return configured;
  }
  return mutation.operation === "replace";
}

export async function updateGmScienceSettings(
  input: UpdateGmScienceSettingsInput,
): Promise<GmScienceSettingsUpdateResult> {
  if (input.memoryEnabled !== undefined) {
    state.settings.memory.enabled = input.memoryEnabled;
  }
  if (input.model) {
    const selected = state.settings.providers.find((provider) => provider.id === input.model?.provider);
    if (!selected || !input.model.model.trim()) {
      throw new Error("Unsupported provider or model.");
    }
    state.settings.model = { ...input.model, model: input.model.model.trim() };
    state.settings.providers = state.settings.providers.map((provider) => ({
      ...provider,
      active: provider.id === input.model?.provider,
    }));
    state.agents = state.agents.map((agent) => ({
      ...agent,
      provider: input.model?.provider ?? agent.provider,
      model: input.model?.model.trim() ?? agent.model,
    }));
  }

  const activeProvider = state.settings.providers.find((provider) => provider.active);
  if (activeProvider && input.providerApiKey) {
    activeProvider.credentialConfigured = applyMockSecretMutation(
      activeProvider.credentialConfigured,
      input.providerApiKey,
    );
    activeProvider.credentialSource = activeProvider.credentialConfigured ? "local_config" : "none";
  }
  if (input.pubmedEmail !== undefined) {
    state.settings.literature.pubmed.email = input.pubmedEmail.trim();
  }
  state.settings.literature.pubmed.apiKeyConfigured = applyMockSecretMutation(
    state.settings.literature.pubmed.apiKeyConfigured,
    input.pubmedApiKey,
  );
  state.settings.literature.openalex.apiKeyConfigured = applyMockSecretMutation(
    state.settings.literature.openalex.apiKeyConfigured,
    input.openalexApiKey,
  );
  if (input.permissionGrants) {
    state.settings.permissions.items = state.settings.permissions.items.map((permission) => (
      Object.hasOwn(input.permissionGrants ?? {}, permission.id)
        ? {
            ...permission,
            granted: input.permissionGrants?.[permission.id] === true,
            source: "user",
            updatedAt: now(),
          }
        : permission
    ));
  }
  if (input.network) {
    state.settings.network = {
      ...state.settings.network,
      enabled: input.network.enabled ?? state.settings.network.enabled,
      enforceAllowlist: input.network.enforceAllowlist ?? state.settings.network.enforceAllowlist,
      allowPrivateNetworks: input.network.allowPrivateNetworks ?? state.settings.network.allowPrivateNetworks,
      packageMirrors: {
        condaChannelMirror: input.network.condaChannelMirror === undefined
          ? state.settings.network.packageMirrors.condaChannelMirror
          : safePublicUrl(input.network.condaChannelMirror),
        pythonPackageIndex: input.network.pythonPackageIndex === undefined
          ? state.settings.network.packageMirrors.pythonPackageIndex
          : safePublicUrl(input.network.pythonPackageIndex),
        caBundlePath: input.network.caBundlePath ?? state.settings.network.packageMirrors.caBundlePath,
      },
      categories: state.settings.network.categories.map((category) => ({
        ...category,
        enabled: input.network?.categoryEnabled?.[category.id] ?? category.enabled,
      })),
      customDomains: input.network.customDomains ?? state.settings.network.customDomains,
    };
  }
  if (input.computeTarget?.operation === "remove" && input.computeTarget.id) {
    state.settings.compute.targets = state.settings.compute.targets.filter(
      (target) => target.id !== input.computeTarget?.id,
    );
  }
  if (input.computeTarget?.operation === "upsert" && input.computeTarget.target) {
    const target = input.computeTarget.target;
    const metadata = target.type === "ssh"
      ? {
          host: target.host ?? "",
          port: target.port ?? 22,
          username: target.username ?? "",
          identity_configured: Boolean(target.identityFile),
        }
      : {
          url: safePublicUrl(target.url ?? ""),
          health_path: target.healthPath ?? "/health",
          api_key_configured: target.apiKey?.operation === "replace",
        };
    const nextTarget = {
      id: target.id,
      type: target.type,
      name: target.name,
      enabled: target.enabled,
      configured: Boolean(target.type === "ssh" ? target.host : target.url),
      executable: false,
      status: "unavailable" as const,
      statusDetail: "Configured; remote execution adapter is not implemented.",
      metadata,
    };
    state.settings.compute.targets = [
      ...state.settings.compute.targets.filter((item) => item.id !== target.id),
      nextTarget,
    ];
  }

  const pubmedReady = Boolean(state.settings.literature.pubmed.email);
  state.settings.literature.pubmed.status = pubmedReady ? "ready" : "needs_configuration";
  state.settings.literature.pubmed.statusDetail = pubmedReady ? "" : "Add a PubMed contact email.";
  const openalexReady = state.settings.literature.openalex.apiKeyConfigured;
  state.settings.literature.openalex.status = openalexReady ? "ready" : "needs_configuration";
  state.settings.literature.openalex.statusDetail = openalexReady ? "" : "Add an OpenAlex API key.";
  for (const capability of capabilityDefinitions) {
    if (capability.id === "pubmed") {
      capability.status = state.settings.literature.pubmed.status;
      capability.statusDetail = state.settings.literature.pubmed.statusDetail;
    }
    if (capability.id === "openalex") {
      capability.status = state.settings.literature.openalex.status;
      capability.statusDetail = state.settings.literature.openalex.statusDetail;
    }
  }

  const capabilities = (await listGmScienceCapabilities(input.projectId)).items;
  return {
    settings: cloneSettings(),
    agent: { ...state.agents[0] },
    projectId: input.projectId ?? "",
    capabilities,
  };
}

export async function checkGmScienceComputeTarget(targetId: string): Promise<GmScienceComputeHealth> {
  const target = state.settings.compute.targets.find((item) => item.id === targetId);
  if (!target) {
    throw new Error(`Compute Target ${targetId} was not found.`);
  }
  const reachable = target.id === "local";
  return {
    targetId,
    status: reachable ? "ready" : target.configured ? "unavailable" : "needs_configuration",
    reachable,
    executable: target.executable,
    detail: reachable ? "Local Python execution is available." : target.statusDetail,
    checkedAt: now(),
  };
}

function memoryWorkspace(projectId: string): GmScienceMemoryWorkspace {
  if (!state.projects.some((project) => project.id === projectId)) {
    throw new Error(`Project ${projectId} was not found.`);
  }
  state.memoryByProject[projectId] ??= {
    projectId,
    notes: [],
    candidates: [],
    categories: [],
  };
  return state.memoryByProject[projectId];
}

export async function getGmScienceMemory(projectId: string): Promise<GmScienceMemoryWorkspace> {
  return structuredClone(memoryWorkspace(projectId));
}

export async function createGmScienceMemoryNote(
  projectId: string,
  input: CreateGmScienceMemoryNoteInput,
): Promise<GmScienceMemoryNote> {
  const workspace = memoryWorkspace(projectId);
  const timestamp = now();
  const note: GmScienceMemoryNote = {
    id: `memory-note-${++memoryNoteSequence}`,
    scope: input.scope,
    category: input.category.trim(),
    text: input.text.trim(),
    createdAt: timestamp,
    updatedAt: timestamp,
    provenance: {
      source: "manual",
      projectId: input.scope === "project" ? projectId : "",
      sessionId: "",
      model: "",
      candidateId: "",
      rationale: "",
    },
    usage: { count: 0, sessionIds: [], lastUsedAtMs: 0 },
  };
  workspace.notes.unshift(note);
  workspace.categories = [...new Set([...workspace.categories, note.category])].sort();
  return structuredClone(note);
}

export async function updateGmScienceMemoryNote(
  projectId: string,
  noteId: string,
  input: UpdateGmScienceMemoryNoteInput,
): Promise<GmScienceMemoryNote> {
  const workspace = memoryWorkspace(projectId);
  const note = workspace.notes.find((item) => item.id === noteId);
  if (!note) {
    throw new Error("Memory note was not found in this Project.");
  }
  note.category = input.category.trim();
  note.text = input.text.trim();
  note.updatedAt = now();
  workspace.categories = [...new Set([...workspace.categories, note.category])].sort();
  return structuredClone(note);
}

export async function deleteGmScienceMemoryNote(projectId: string, noteId: string): Promise<void> {
  const workspace = memoryWorkspace(projectId);
  const before = workspace.notes.length;
  workspace.notes = workspace.notes.filter((item) => item.id !== noteId);
  if (workspace.notes.length === before) {
    throw new Error("Memory note was not found in this Project.");
  }
}

export async function clearGmScienceMemory(
  projectId: string,
  scope: GmScienceMemoryScope,
): Promise<number> {
  const workspace = memoryWorkspace(projectId);
  const before = workspace.notes.length;
  workspace.notes = workspace.notes.filter((item) => item.scope !== scope);
  return before - workspace.notes.length;
}

export async function reviewGmScienceMemoryCandidate(
  projectId: string,
  candidateId: string,
  decision: "approve" | "reject",
): Promise<GmScienceMemoryCandidate> {
  const workspace = memoryWorkspace(projectId);
  const candidate = workspace.candidates.find((item) => item.id === candidateId);
  if (!candidate || candidate.status !== "pending") {
    throw new Error("Memory candidate is unavailable for review.");
  }
  candidate.status = decision === "approve" ? "approved" : "rejected";
  candidate.reviewedAt = now();
  if (decision === "approve") {
    const note = await createGmScienceMemoryNote(projectId, {
      scope: candidate.scope,
      category: candidate.category,
      text: candidate.text,
    });
    const storedNote = workspace.notes.find((item) => item.id === note.id)!;
    storedNote.provenance.source = "candidate_review";
    storedNote.provenance.candidateId = candidate.id;
    storedNote.provenance.sessionId = candidate.sourceSessionId;
    storedNote.provenance.model = candidate.model;
    storedNote.provenance.rationale = candidate.rationale;
    candidate.approvedNoteId = note.id;
  }
  return structuredClone(candidate);
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

export async function listGmScienceResources(
  projectId: string,
  query = "",
): Promise<{ resources: GmScienceResource[] }> {
  const resources = (state.artifactsByProject[projectId] ?? []).map<GmScienceResource>((artifact) => ({
    id: `artifact:${artifact.id}`,
    kind:
      artifact.type === "dataset"
        ? "dataset"
        : artifact.metadata.task_id || artifact.provenance.task_id
          ? "run_output"
          : "artifact",
    projectId: artifact.projectId,
    sessionId: artifact.sessionId,
    displayName: artifact.title,
    artifactType: artifact.type,
    mimeType: artifact.mimeType,
    versionOrHash: artifact.updatedAt,
    accessMode: /^https?:\/\//i.test(artifact.pathOrUrl) ? "external" : "metadata_only",
    source: "artifact",
    artifactId: artifact.id,
    relativePath: "",
    url: safePublicUrl(artifact.pathOrUrl),
    sizeBytes: null,
    createdAt: artifact.createdAt,
    updatedAt: artifact.updatedAt,
    metadata: {},
  }));
  const needle = query.trim().toLowerCase();
  return {
    resources: needle
      ? resources.filter((resource) =>
          `${resource.displayName} ${resource.kind} ${resource.artifactType}`.toLowerCase().includes(needle),
        )
      : resources,
  };
}

const SAFE_DETAIL_METADATA_KEYS = new Set([
  "abstract",
  "authors",
  "canonical_id",
  "citation_artifact_ids",
  "dataset_artifact_id",
  "dataset_artifact_ids",
  "doi",
  "evidence_scope",
  "findings",
  "paper_artifact_id",
  "paper_artifact_ids",
  "pmid",
  "report_artifact_id",
  "science_run_role",
  "source_artifact_id",
  "source_artifact_ids",
  "status",
  "summary",
  "target_artifact_id",
  "task_id",
  "title",
  "venue",
  "year",
]);
const SAFE_DETAIL_PROVENANCE_KEYS = new Set([
  "created_by",
  "model",
  "query",
  "session_id",
  "source_artifact_id",
  "source_artifact_ids",
  "sources",
  "specialist_id",
  "target_artifact_id",
  "task_id",
  "trigger",
]);

export async function getGmScienceResourceDetail(
  projectId: string,
  resourceId: string,
): Promise<{ detail: GmScienceResourceDetail }> {
  if (!state.projects.some((project) => project.id === projectId)) {
    throw new Error(`Project ${projectId} was not found.`);
  }
  const resources = (await listGmScienceResources(projectId)).resources;
  const resource = resources.find((item) => item.id === resourceId);
  if (!resource) {
    throw new Error(`Resource ${resourceId} was not found.`);
  }
  const artifact = (state.artifactsByProject[projectId] ?? []).find((item) => item.id === resource.artifactId);
  const contentStatus = resource.accessMode === "external"
    ? "external_descriptor_only"
    : resource.accessMode === "metadata_only"
      ? "metadata_descriptor_only"
      : "binary_descriptor_only";
  return {
    detail: {
      resource,
      preview: {
        content: "",
        contentStatus,
        contentIncluded: false,
        contentChars: 0,
        truncated: false,
      },
      artifact: artifact
        ? {
            id: artifact.id,
            sessionId: artifact.sessionId,
            type: artifact.type,
            title: artifact.title,
            mimeType: artifact.mimeType,
            metadata: pickSafeDetailFields(artifact.metadata, SAFE_DETAIL_METADATA_KEYS),
            provenance: pickSafeDetailFields(artifact.provenance, SAFE_DETAIL_PROVENANCE_KEYS),
            createdAt: artifact.createdAt,
            updatedAt: artifact.updatedAt,
          }
        : null,
      relations: [],
    },
  };
}

function pickSafeDetailFields(
  source: Record<string, unknown>,
  allowedKeys: Set<string>,
): Record<string, unknown> {
  return Object.fromEntries(Object.entries(source).filter(([key]) => allowedKeys.has(key)));
}

function safePublicUrl(rawUrl: string): string {
  try {
    const parsed = new URL(rawUrl);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return "";
    }
    return `${parsed.protocol}//${parsed.host}${parsed.pathname}`;
  } catch {
    return "";
  }
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
