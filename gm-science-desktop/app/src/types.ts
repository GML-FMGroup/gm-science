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
  provider: string;
  model: string;
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

export interface GmScienceSessionPolicyValues {
  delegationEnabled: boolean;
  autoReviewEnabled: boolean;
  memoryEnabled: boolean;
  specialistId: string;
  reviewerModel: "default";
  computeTarget: "local";
}

export interface GmScienceSessionPolicyOption {
  id: string;
  name: string;
}

export interface GmScienceSessionPolicySpecialist extends GmScienceSessionPolicyOption {
  description: string;
  status: GmScienceCapabilityStatus;
}

export interface GmScienceSessionPolicy extends GmScienceSessionPolicyValues {
  sessionId: string;
  projectId: string;
  specialists: GmScienceSessionPolicySpecialist[];
  reviewerAvailable: boolean;
  reviewerModels: GmScienceSessionPolicyOption[];
  computeTargets: GmScienceSessionPolicyOption[];
  issues: string[];
}

export interface UpdateGmScienceSessionPolicyInput {
  delegationEnabled?: boolean;
  autoReviewEnabled?: boolean;
  memoryEnabled?: boolean;
  specialistId?: string;
  reviewerModel?: "default";
  computeTarget?: "local";
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
  sessionPolicyDefaults: GmScienceSessionPolicyValues;
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
  sessionPolicyDefaults?: Partial<GmScienceSessionPolicyValues>;
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

export type GmScienceProviderAuthType = "oauth" | "api_key" | "optional_api_key";

export type GmScienceCredentialSource = "none" | "local_config" | "environment" | "oauth_cache";

export interface GmScienceProviderOption {
  id: string;
  name: string;
  defaultModel: string;
  authType: GmScienceProviderAuthType;
  credentialRequired: boolean;
  credentialConfigured: boolean;
  credentialSource: GmScienceCredentialSource;
  active: boolean;
}

export type GmScienceInfrastructureStatus =
  | "ready"
  | "needs_configuration"
  | "unavailable"
  | "disabled"
  | "blocked"
  | "reachable"
  | "unreachable";

export interface GmSciencePermissionGrant {
  id: string;
  name: string;
  description: string;
  category: "registry_writes";
  granted: boolean;
  scope: "global";
  source: "default" | "user";
  updatedAt: string;
}

export interface GmScienceNetworkCategory {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  domains: string[];
}

export interface GmScienceNetworkSettings {
  enabled: boolean;
  enforceAllowlist: boolean;
  allowPrivateNetworks: boolean;
  packageMirrors: {
    condaChannelMirror: string;
    pythonPackageIndex: string;
    caBundlePath: string;
  };
  categories: GmScienceNetworkCategory[];
  customDomains: string[];
  enforcementBoundary: string;
}

export type GmScienceComputeTargetType = "local" | "ssh" | "cloud_provider" | "model_endpoint";

export interface GmScienceComputeTarget {
  id: string;
  type: GmScienceComputeTargetType;
  name: string;
  enabled: boolean;
  configured: boolean;
  executable: boolean;
  status: GmScienceInfrastructureStatus;
  statusDetail: string;
  metadata: Record<string, unknown>;
}

export interface GmScienceComputeHealth {
  targetId: string;
  status: GmScienceInfrastructureStatus;
  reachable: boolean;
  executable: boolean;
  detail: string;
  checkedAt: string;
}

export interface GmScienceSettings {
  model: {
    provider: string;
    model: string;
  };
  memory: {
    enabled: boolean;
  };
  providers: GmScienceProviderOption[];
  permissions: {
    items: GmSciencePermissionGrant[];
  };
  network: GmScienceNetworkSettings;
  compute: {
    targets: GmScienceComputeTarget[];
  };
  literature: {
    arxiv: {
      status: GmScienceCapabilityStatus;
      statusDetail: string;
    };
    pubmed: {
      email: string;
      apiKeyConfigured: boolean;
      status: GmScienceCapabilityStatus;
      statusDetail: string;
    };
    openalex: {
      apiKeyConfigured: boolean;
      status: GmScienceCapabilityStatus;
      statusDetail: string;
    };
  };
}

export interface GmScienceSecretMutation {
  operation: "replace" | "remove";
  value?: string;
}

export interface UpdateGmScienceSettingsInput {
  projectId?: string;
  memoryEnabled?: boolean;
  model?: {
    provider: string;
    model: string;
  };
  providerApiKey?: GmScienceSecretMutation;
  pubmedEmail?: string;
  pubmedApiKey?: GmScienceSecretMutation;
  openalexApiKey?: GmScienceSecretMutation;
  permissionGrants?: Record<string, boolean>;
  network?: {
    enabled?: boolean;
    enforceAllowlist?: boolean;
    allowPrivateNetworks?: boolean;
    condaChannelMirror?: string;
    pythonPackageIndex?: string;
    caBundlePath?: string;
    categoryEnabled?: Record<string, boolean>;
    customDomains?: string[];
  };
  computeTarget?: {
    operation: "upsert" | "remove";
    id?: string;
    target?: {
      id: string;
      type: "ssh" | "model_endpoint";
      name: string;
      enabled: boolean;
      host?: string;
      port?: number;
      username?: string;
      identityFile?: string;
      url?: string;
      healthPath?: string;
      apiKey?: GmScienceSecretMutation;
    };
  };
}

export type GmScienceMemoryScope = "user" | "project";

export interface GmScienceMemoryUsage {
  count: number;
  sessionIds: string[];
  lastUsedAtMs: number;
}

export interface GmScienceMemoryNote {
  id: string;
  scope: GmScienceMemoryScope;
  category: string;
  text: string;
  createdAt: string;
  updatedAt: string;
  provenance: {
    source: string;
    projectId: string;
    sessionId: string;
    model: string;
    candidateId: string;
    rationale: string;
  };
  usage: GmScienceMemoryUsage;
}

export type GmScienceMemoryCandidateStatus = "pending" | "approved" | "rejected";

export interface GmScienceMemoryCandidate {
  id: string;
  scope: GmScienceMemoryScope;
  category: string;
  text: string;
  rationale: string;
  status: GmScienceMemoryCandidateStatus;
  projectId: string;
  sourceSessionId: string;
  model: string;
  approvedNoteId: string;
  createdAt: string;
  reviewedAt: string;
}

export interface GmScienceMemoryWorkspace {
  projectId: string;
  notes: GmScienceMemoryNote[];
  candidates: GmScienceMemoryCandidate[];
  categories: string[];
}

export interface CreateGmScienceMemoryNoteInput {
  scope: GmScienceMemoryScope;
  category: string;
  text: string;
}

export interface UpdateGmScienceMemoryNoteInput {
  category: string;
  text: string;
}

export interface GmScienceSettingsUpdateResult {
  settings: GmScienceSettings;
  agent: AgentProfile;
  projectId: string;
  capabilities: GmScienceCapability[];
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
export type GmScienceResourceContentStatus =
  | "included"
  | "binary_descriptor_only"
  | "external_descriptor_only"
  | "metadata_descriptor_only"
  | "budget_exhausted_descriptor_only"
  | "unavailable_descriptor_only";
export type GmScienceArtifactRelationDirection = "outgoing" | "incoming";

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

export interface GmScienceResourcePreview {
  content: string;
  contentStatus: GmScienceResourceContentStatus;
  contentIncluded: boolean;
  contentChars: number;
  truncated: boolean;
}

export interface GmScienceArtifactDetail {
  id: string;
  sessionId: string;
  type: string;
  title: string;
  mimeType: string;
  metadata: Record<string, unknown>;
  provenance: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface GmScienceArtifactRelation {
  artifactId: string;
  resourceId: string;
  sessionId: string;
  title: string;
  artifactType: string;
  relation: string;
  direction: GmScienceArtifactRelationDirection;
}

export interface GmScienceResourceDetail {
  resource: GmScienceResource;
  preview: GmScienceResourcePreview;
  artifact: GmScienceArtifactDetail | null;
  relations: GmScienceArtifactRelation[];
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
  getGmScienceSettings(): Promise<GmScienceSettings>;
  updateGmScienceSettings(input: UpdateGmScienceSettingsInput): Promise<GmScienceSettingsUpdateResult>;
  checkGmScienceComputeTarget(targetId: string): Promise<GmScienceComputeHealth>;
  getGmScienceMemory(projectId: string): Promise<GmScienceMemoryWorkspace>;
  createGmScienceMemoryNote(
    projectId: string,
    input: CreateGmScienceMemoryNoteInput,
  ): Promise<GmScienceMemoryNote>;
  updateGmScienceMemoryNote(
    projectId: string,
    noteId: string,
    input: UpdateGmScienceMemoryNoteInput,
  ): Promise<GmScienceMemoryNote>;
  deleteGmScienceMemoryNote(projectId: string, noteId: string): Promise<void>;
  clearGmScienceMemory(projectId: string, scope: GmScienceMemoryScope): Promise<number>;
  reviewGmScienceMemoryCandidate(
    projectId: string,
    candidateId: string,
    decision: "approve" | "reject",
  ): Promise<GmScienceMemoryCandidate>;
  getGmScienceSessionPolicy(sessionId: string): Promise<GmScienceSessionPolicy>;
  updateGmScienceSessionPolicy(
    sessionId: string,
    input: UpdateGmScienceSessionPolicyInput,
  ): Promise<GmScienceSessionPolicy>;
  listGmScienceArtifacts(projectId: string): Promise<{ artifacts: GmScienceArtifact[] }>;
  listGmScienceResources(projectId: string, query?: string): Promise<{ resources: GmScienceResource[] }>;
  getGmScienceResourceDetail(projectId: string, resourceId: string): Promise<{ detail: GmScienceResourceDetail }>;
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
