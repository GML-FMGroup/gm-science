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

export interface GmScienceCapability {
  id: string;
  kind: GmScienceCapabilityKind;
  name: string;
  description: string;
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

export interface CreateGmScienceArtifactInput {
  type: string;
  title: string;
  pathOrUrl?: string;
  mimeType?: string;
  sessionId?: string;
  metadata?: Record<string, unknown>;
  provenance?: Record<string, unknown>;
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
  createGmScienceArtifact(
    projectId: string,
    input: CreateGmScienceArtifactInput,
  ): Promise<{ artifact: GmScienceArtifact }>;
  onRunEvent(listener: (event: RunEvent) => void): () => void;
}
