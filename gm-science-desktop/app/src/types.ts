export type RuntimeState = "stopped" | "starting" | "healthy" | "error";

export type MessageRole = "user" | "assistant" | "system" | "tool";

export type MessageStatus = "streaming" | "completed" | "failed" | "cancelled";

export type MessagePart =
  | { type: "markdown"; text: string }
  | { type: "code"; text: string; language?: string }
  | { type: "file"; text: string; fileName: string; sizeBytes?: number; mimeType?: string }
  | { type: "image"; text: string; url: string; mimeType?: string }
  | { type: "error"; text: string; errorCode?: string }
  | { type: "tool_result"; toolName: string; summary: string; detail?: string; rawText?: string }
  | {
      type: "resource_ref";
      resourceId: string;
      displayName: string;
      kind: GmScienceResourceKind;
      versionOrHash: string;
      mimeType: string;
      relativePath: string;
      url: string;
      contentStatus: string;
      truncated: boolean;
    }
  | { type: "step_ref"; stepId: string; title: string; status: "running" | "completed" | "failed"; detail: string };

export interface ConnectionTarget {
  id: string;
  type: "local" | "remote";
  name: string;
}

export interface RuntimeStatus {
  target: ConnectionTarget;
  state: RuntimeState;
  summary: string;
  detail?: string;
  lastError?: string;
}

export interface ClientDiagnostics {
  mode: "local" | "remote" | "mock";
  target: ConnectionTarget;
  openppxRoot: string;
  openppxRootExists: boolean;
  pythonBin: string;
  globalConfigPath: string;
  globalConfigExists: boolean;
  clientApiBaseUrl: string;
  clientApiManagedByClient: boolean;
  clientApiHealthy: boolean;
  clientApiProcessRunning: boolean;
  agentCount: number;
  sessionCacheEntries: number;
  messageCacheEntries: number;
  debugEnabled: boolean;
}

export interface ConnectionSettings {
  targetType: "local" | "remote";
  targetId: string;
  targetName: string;
  clientApiBaseUrl: string;
}

export interface AgentProfile {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  status: "healthy" | "idle" | "starting" | "disabled";
  tags: string[];
}

export interface SessionSummary {
  id: string;
  agentId: string;
  projectId?: string;
  title: string;
  updatedAt: string;
  lastMessagePreview: string;
}

export interface GmScienceProject {
  id: string;
  name: string;
  description: string;
  agentContext: string;
  workspacePath: string;
  sessionsCount: number;
  artifactsCount: number;
  enabledSkills: string[];
  enabledConnectors: string[];
  enabledSpecialists: string[];
  createdAt: string;
  updatedAt: string;
}

export interface CreateGmScienceProjectInput {
  name: string;
  description?: string;
  agentContext?: string;
  enabledSkills?: string[];
  enabledConnectors?: string[];
  enabledSpecialists?: string[];
}

export type GmScienceCapabilityKind = "skill" | "connector" | "specialist";

export type GmScienceCapabilityStatus = "ready" | "needs_configuration" | "disabled";

export type GmScienceCapabilitySource = "built_in" | "local" | "external";

export interface GmScienceCapability {
  id: string;
  kind: GmScienceCapabilityKind;
  name: string;
  description: string;
  source: GmScienceCapabilitySource;
  version: string;
  license: string;
  files: string[];
  available: boolean;
  defaultEnabled: boolean;
  projectEnabled: boolean | null;
  status: GmScienceCapabilityStatus;
  statusDetail: string;
  metadata: Record<string, unknown>;
}

export interface GmScienceCapabilityCatalog {
  projectId: string;
  items: GmScienceCapability[];
}

export interface UpdateGmScienceCapabilitiesInput {
  enabledSkills: string[];
  enabledConnectors: string[];
  enabledSpecialists: string[];
}

export interface GmScienceArtifact {
  id: string;
  projectId: string;
  sessionId: string;
  type: string;
  title: string;
  pathOrUrl: string;
  mimeType: string;
  metadata: Record<string, unknown>;
  provenance: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export type GmScienceResourceKind = "artifact" | "dataset" | "run_output" | "project_file";
export type GmScienceResourceAccessMode = "read" | "external" | "metadata_only";
export type GmScienceResourceSource = "artifact" | "workspace";

export interface GmScienceResource {
  id: string;
  kind: GmScienceResourceKind;
  projectId: string;
  sessionId: string;
  displayName: string;
  artifactType: string;
  mimeType: string;
  versionOrHash: string;
  accessMode: GmScienceResourceAccessMode;
  source: GmScienceResourceSource;
  artifactId: string;
  relativePath: string;
  url: string;
  sizeBytes: number | null;
  createdAt: string;
  updatedAt: string;
  metadata: Record<string, unknown>;
}

export interface GmScienceResourceSelection {
  id: string;
  versionOrHash: string;
}

export interface CreateGmScienceArtifactInput {
  type: string;
  title: string;
  pathOrUrl?: string;
  mimeType?: string;
  sessionId?: string;
  metadata?: Record<string, unknown>;
  provenance?: Record<string, unknown>;
}

export type GmScienceRunStatus =
  | "queued"
  | "running"
  | "paused"
  | "waiting_user"
  | "waiting_approval"
  | "interrupted"
  | "stale"
  | "completed"
  | "failed"
  | "cancelled"
  | "lost";

export interface GmScienceRun {
  taskId: string;
  projectId: string;
  sessionId: string;
  parentTaskId: string;
  kind: string;
  title: string;
  status: GmScienceRunStatus;
  progressSummary: string;
  terminalSummary: string;
  lastError: string;
  createdAt: string;
  updatedAt: string;
  createdAtMs: number;
  updatedAtMs: number;
  endedAtMs: number | null;
  canCancel: boolean;
  canRetry: boolean;
  logPreview: string;
  artifactIds: string[];
}

export interface CreateGmSciencePythonRunInput {
  title: string;
  source: string;
  sessionId?: string;
  input?: Record<string, unknown>;
}

export interface GmScienceDatasetColumnProfile {
  name: string;
  inferredType: string;
  nonNullCount: number;
  missingCount: number;
  missingFraction: number;
  uniqueCount: number;
  uniqueCountCapped: boolean;
  typeCounts: Record<string, number>;
  topValues: Array<{ value: string; count: number }>;
  numeric?: {
    count: number;
    min: number | null;
    max: number | null;
    mean: number | null;
    standardDeviation: number | null;
  };
}

export interface GmScienceDatasetProfile {
  version: number;
  format: string;
  rowCount: number;
  profiledRowCount: number;
  columnCount: number;
  columns: GmScienceDatasetColumnProfile[];
  preview: Array<Record<string, unknown>>;
  warnings: string[];
}

export interface GmScienceDataset {
  artifactId: string;
  projectId: string;
  sessionId: string;
  title: string;
  path: string;
  mimeType: string;
  format: string;
  sourceName: string;
  sizeBytes: number;
  rowCount: number;
  profiledRowCount: number;
  columnCount: number;
  columnNames: string[];
  profileArtifactId: string;
  profile?: GmScienceDatasetProfile;
  createdAt: string;
  updatedAt: string;
}

export interface GmScienceDatasetFileSelection {
  path: string;
  name: string;
}

export interface ImportGmScienceDatasetInput {
  sourcePath: string;
  title?: string;
  sessionId?: string;
}

export interface GmScienceAnalysisPlanStep {
  id: string;
  title: string;
  description: string;
}

export interface GmScienceAnalysisPlan {
  version: number;
  objective: string;
  operations: string[];
  steps: GmScienceAnalysisPlanStep[];
  datasets: Array<Record<string, unknown>>;
  assumptions: string[];
  warnings: string[];
}

export interface GmScienceAnalysis {
  id: string;
  projectId: string;
  sessionId: string;
  title: string;
  objective: string;
  datasetArtifactIds: string[];
  plan: GmScienceAnalysisPlan;
  source?: string;
  taskId: string;
  status: "draft" | GmScienceRunStatus;
  run: GmScienceRun | null;
  reportArtifactId: string;
  figureArtifactIds: string[];
  artifactIds: string[];
  createdAt: string;
  updatedAt: string;
}

export interface CreateGmScienceAnalysisInput {
  title?: string;
  objective: string;
  datasetArtifactIds: string[];
  sessionId?: string;
}

export interface ChatMessage {
  id: string;
  sessionId: string;
  role: MessageRole;
  status: MessageStatus;
  createdAt: string;
  parts: MessagePart[];
}

export interface BootstrapPayload {
  runtime: RuntimeStatus;
  agents: AgentProfile[];
  sessions: SessionSummary[];
  messages: ChatMessage[];
  selectedAgentId: string;
  selectedSessionId: string;
}

export type RuntimeCommand = "start" | "stop" | "restart";

export type RunEvent =
  | {
      type: "message.created";
      runId: string;
      sessionId: string;
      message: ChatMessage;
    }
  | {
      type: "message.updated";
      runId: string;
      sessionId: string;
      messageId: string;
      status?: MessageStatus;
      appendParts?: MessagePart[];
      replaceParts?: MessagePart[];
    }
  | {
      type: "session.updated";
      runId: string;
      session: SessionSummary;
    }
  | {
      type: "run.finished";
      runId: string;
      sessionId: string;
    };

export interface SendMessageInput {
  agentId: string;
  sessionId: string;
  text: string;
  projectId?: string;
  resourceRefs?: GmScienceResourceSelection[];
}

export interface PpxClientApi {
  bootstrap(): Promise<BootstrapPayload>;
  getDiagnostics(): Promise<ClientDiagnostics>;
  saveConnectionSettings(settings: ConnectionSettings): Promise<ClientDiagnostics>;
  runRuntimeCommand(command: RuntimeCommand): Promise<RuntimeStatus>;
  listSessions(agentId: string): Promise<{ sessions: SessionSummary[] }>;
  createSession(agentId: string, projectId?: string): Promise<{ session: SessionSummary }>;
  loadSession(sessionId: string): Promise<{ messages: ChatMessage[] }>;
  sendMessage(input: SendMessageInput): Promise<{ runId: string }>;
  listGmScienceProjects(): Promise<{ projects: GmScienceProject[] }>;
  createGmScienceProject(input: CreateGmScienceProjectInput): Promise<{ project: GmScienceProject }>;
  getGmScienceProject(projectId: string): Promise<{ project: GmScienceProject }>;
  listGmScienceCapabilities(projectId?: string): Promise<GmScienceCapabilityCatalog>;
  updateGmScienceProjectCapabilities(
    projectId: string,
    input: UpdateGmScienceCapabilitiesInput,
  ): Promise<{ project: GmScienceProject; capabilities: GmScienceCapability[] }>;
  listGmScienceArtifacts(projectId: string): Promise<{ artifacts: GmScienceArtifact[] }>;
  listGmScienceResources(projectId: string, query?: string): Promise<{ resources: GmScienceResource[] }>;
  createGmScienceArtifact(
    projectId: string,
    input: CreateGmScienceArtifactInput,
  ): Promise<{ artifact: GmScienceArtifact }>;
  listGmScienceRuns(projectId: string): Promise<{ runs: GmScienceRun[] }>;
  getGmScienceRun(projectId: string, taskId: string): Promise<{ run: GmScienceRun }>;
  createGmSciencePythonRun(
    projectId: string,
    input: CreateGmSciencePythonRunInput,
  ): Promise<{ run: GmScienceRun }>;
  cancelGmScienceRun(projectId: string, taskId: string): Promise<{ run: GmScienceRun }>;
  retryGmScienceRun(projectId: string, taskId: string): Promise<{ run: GmScienceRun }>;
  selectGmScienceDatasetFile(): Promise<GmScienceDatasetFileSelection | null>;
  listGmScienceDatasets(projectId: string): Promise<{ datasets: GmScienceDataset[] }>;
  getGmScienceDataset(projectId: string, artifactId: string): Promise<{ dataset: GmScienceDataset }>;
  importGmScienceDataset(
    projectId: string,
    input: ImportGmScienceDatasetInput,
  ): Promise<{ dataset: GmScienceDataset }>;
  listGmScienceAnalyses(projectId: string): Promise<{ analyses: GmScienceAnalysis[] }>;
  getGmScienceAnalysis(projectId: string, analysisId: string): Promise<{ analysis: GmScienceAnalysis }>;
  createGmScienceAnalysis(
    projectId: string,
    input: CreateGmScienceAnalysisInput,
  ): Promise<{ analysis: GmScienceAnalysis }>;
  runGmScienceAnalysis(projectId: string, analysisId: string): Promise<{ analysis: GmScienceAnalysis }>;
  onRunEvent(listener: (event: RunEvent) => void): () => void;
}
