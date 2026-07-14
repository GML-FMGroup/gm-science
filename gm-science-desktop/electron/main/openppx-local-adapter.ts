import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import {
  bootstrap as mockBootstrap,
  createGmScienceArtifact as mockCreateGmScienceArtifact,
  createGmScienceProject as mockCreateGmScienceProject,
  createSession as mockCreateSession,
  getGmScienceProject as mockGetGmScienceProject,
  listGmScienceCapabilities as mockListGmScienceCapabilities,
  listGmScienceArtifacts as mockListGmScienceArtifacts,
  listGmScienceProjects as mockListGmScienceProjects,
  listSessions as mockListSessions,
  loadSession as mockLoadSession,
  runRuntimeCommand as mockRunRuntimeCommand,
  sendMessage as mockSendMessage,
  updateGmScienceProjectCapabilities as mockUpdateGmScienceProjectCapabilities,
  subscribe as subscribeMock,
} from "../../app/src/lib/mock-client";
import {
  normalizeClientApiMessage,
  normalizeClientApiPart,
  normalizeClientApiRuntime,
  normalizeClientApiSession,
  normalizeGmScienceArtifact,
  normalizeGmScienceCapability,
  normalizeGmScienceProject,
} from "../../app/src/lib/client-api-projection";
import { mergeAssistantParts } from "../../app/src/lib/openppx-projection";
import {
  appendClientApiLogTail,
  buildCreateGmScienceProjectPayload,
  buildClientApiRunPath,
  buildClientApiSpawnEnv,
  formatClientApiStartupError,
  isOpenPpxClientApiHealthPayload,
  managedProcessAfterClose,
  resolveClientApiPort,
  resolveGmScienceDataRoot,
} from "./gm-science-adapter-helpers";
import type {
  AgentProfile,
  BootstrapPayload,
  ChatMessage,
  ClientDiagnostics,
  ConnectionSettings,
  ConnectionTarget,
  CreateGmScienceArtifactInput,
  CreateGmScienceProjectInput,
  GmScienceArtifact,
  GmScienceCapability,
  GmScienceCapabilityCatalog,
  GmScienceProject,
  MessagePart,
  PpxClientApi,
  RunEvent,
  RuntimeCommand,
  RuntimeStatus,
  SendMessageInput,
  SessionSummary,
  UpdateGmScienceCapabilitiesInput,
} from "../../app/src/types";

type EventSink = (event: RunEvent) => void;
type StepPart = Extract<MessagePart, { type: "step_ref" }>;
type SessionCacheEntry = { sessions: SessionSummary[]; expiresAt: number };
type MessageCacheEntry = { messages: ChatMessage[]; expiresAt: number };

interface GlobalAgentConfigEntry {
  name?: string;
  id?: string;
  enabled?: boolean;
}

interface GlobalAgentConfig {
  agents?: GlobalAgentConfigEntry[] | { list?: GlobalAgentConfigEntry[] };
}

function now(): string {
  return new Date().toISOString();
}

function clientDebugEnabled(): boolean {
  const raw = process.env.OPENPPX_CLIENT_DEBUG ?? process.env.PPX_CLIENT_DEBUG ?? "";
  return ["1", "true", "yes", "on"].includes(raw.trim().toLowerCase());
}

function clientDebugLog(tag: string, payload: unknown): void {
  if (!clientDebugEnabled()) {
    return;
  }
  console.log(`[gm-science][debug] ${tag}`, payload);
}

function normalizeAgentName(input: string): string {
  return input
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function readJsonFile<T>(filePath: string): T | null {
  try {
    if (!fs.existsSync(filePath)) {
      return null;
    }
    return JSON.parse(fs.readFileSync(filePath, "utf-8")) as T;
  } catch {
    return null;
  }
}

function detectOpenPpxRoot(): string {
  if (process.env.OPENPPX_ROOT?.trim()) {
    return path.resolve(process.env.OPENPPX_ROOT);
  }
  return path.resolve(process.cwd(), "../gm-science-runtime");
}

function dataRootPath(): string {
  return path.resolve(resolveGmScienceDataRoot(process.env, os.homedir()));
}

function globalConfigPath(): string {
  return path.join(dataRootPath(), "global_config.json");
}

function agentConfigPath(agentId: string): string {
  return path.join(dataRootPath(), agentId, "config.json");
}

function resolvePythonBin(openppxRoot: string): string {
  const venvPython = path.join(openppxRoot, ".venv", "bin", "python");
  if (fs.existsSync(venvPython)) {
    return venvPython;
  }
  return "python3";
}

function normalizeAgentProfile(payload: Record<string, unknown>): AgentProfile {
  return {
    id: String(payload.id ?? ""),
    name: String(payload.name ?? payload.id ?? ""),
    description: String(payload.description ?? "Local openppx agent"),
    enabled: payload.enabled !== false,
    status: (String(payload.status ?? "healthy") as AgentProfile["status"]) || "healthy",
    tags: Array.isArray(payload.tags) ? payload.tags.map((tag) => String(tag)) : [],
  };
}

export class OpenPpxLocalAdapter implements PpxClientApi {
  private static readonly SESSION_CACHE_TTL_MS = 5_000;

  private static readonly MESSAGE_CACHE_TTL_MS = 5_000;

  private static readonly HEALTH_CACHE_TTL_MS = 1_500;

  private readonly listeners = new Set<EventSink>();

  private readonly openppxRoot = detectOpenPpxRoot();

  private readonly pythonBin = resolvePythonBin(this.openppxRoot);

  private readonly configuredClientApiBaseUrl = process.env.OPENPPX_CLIENT_API_BASE_URL?.trim() || "";

  private readonly clientApiHost = process.env.OPENPPX_CLIENT_API_HOST?.trim() || "127.0.0.1";

  private readonly clientApiPort = resolveClientApiPort(process.env);

  private target: ConnectionTarget;

  private clientApiBaseUrl: string;

  private clientApiProcess: ReturnType<typeof spawn> | null = null;

  private clientApiStartupError = "";

  private readonly sessionsCache = new Map<string, SessionCacheEntry>();

  private readonly messagesCache = new Map<string, MessageCacheEntry>();

  private healthyUntil = 0;

  private inflightHealthCheck: Promise<boolean> | null = null;

  private readonly mockUnsubscribe = subscribeMock((event) => {
    if (this.shouldUseMock()) {
      this.emit(event);
    }
  });

  public constructor(initialSettings?: ConnectionSettings) {
    this.target = this.buildTarget();
    this.clientApiBaseUrl =
      this.target.type === "remote" && this.configuredClientApiBaseUrl
        ? this.configuredClientApiBaseUrl
        : `http://${this.clientApiHost}:${this.clientApiPort}`;
    if (initialSettings) {
      this.applyConnectionSettings(initialSettings);
    }
  }

  private buildTarget(): ConnectionTarget {
    const rawType = (process.env.OPENPPX_TARGET_TYPE?.trim().toLowerCase() || "local") as "local" | "remote";
    if (rawType === "remote") {
      return {
        id: process.env.OPENPPX_TARGET_ID?.trim() || "remote-default",
        type: "remote",
        name: process.env.OPENPPX_TARGET_NAME?.trim() || "Remote Gateway",
      };
    }
    return {
      id: process.env.OPENPPX_TARGET_ID?.trim() || "local-default",
      type: "local",
      name: process.env.OPENPPX_TARGET_NAME?.trim() || "This Mac",
    };
  }

  private isRemoteTarget(): boolean {
    return this.target.type === "remote";
  }

  public applyConnectionSettings(settings: ConnectionSettings): void {
    this.target = {
      id: settings.targetId.trim() || (settings.targetType === "remote" ? "remote-default" : "local-default"),
      type: settings.targetType,
      name: settings.targetName.trim() || (settings.targetType === "remote" ? "Remote Gateway" : "This Mac"),
    };
    this.clientApiBaseUrl =
      settings.targetType === "remote"
        ? settings.clientApiBaseUrl.trim() || `http://${this.clientApiHost}:${this.clientApiPort}`
        : this.configuredClientApiBaseUrl || `http://${this.clientApiHost}:${this.clientApiPort}`;
    this.healthyUntil = 0;
    this.sessionsCache.clear();
    this.messagesCache.clear();
    this.stopManagedClientApiProcess();
  }

  private emit(event: RunEvent): void {
    this.applyEventToCache(event);
    this.listeners.forEach((listener) => listener(event));
  }

  private readSessionsCache(agentId: string): SessionSummary[] | null {
    const cached = this.sessionsCache.get(agentId);
    if (!cached || cached.expiresAt < Date.now()) {
      return null;
    }
    return cached.sessions.map((session) => ({ ...session }));
  }

  private writeSessionsCache(agentId: string, sessions: SessionSummary[]): void {
    this.sessionsCache.set(agentId, {
      sessions: sessions.map((session) => ({ ...session })),
      expiresAt: Date.now() + OpenPpxLocalAdapter.SESSION_CACHE_TTL_MS,
    });
  }

  private readMessagesCache(sessionId: string): ChatMessage[] | null {
    const cached = this.messagesCache.get(sessionId);
    if (!cached || cached.expiresAt < Date.now()) {
      return null;
    }
    return cached.messages.map((message) => ({
      ...message,
      parts: [...message.parts],
    }));
  }

  private writeMessagesCache(sessionId: string, messages: ChatMessage[]): void {
    this.messagesCache.set(sessionId, {
      messages: messages.map((message) => ({
        ...message,
        parts: [...message.parts],
      })),
      expiresAt: Date.now() + OpenPpxLocalAdapter.MESSAGE_CACHE_TTL_MS,
    });
  }

  private invalidateSessionCaches(agentId: string, sessionId?: string): void {
    this.sessionsCache.delete(agentId);
    if (sessionId) {
      this.messagesCache.delete(sessionId);
    }
  }

  private applyEventToCache(event: RunEvent): void {
    if (event.type === "message.created") {
      const cached = this.readMessagesCache(event.sessionId) ?? [];
      if (!cached.some((message) => message.id === event.message.id)) {
        this.writeMessagesCache(event.sessionId, [...cached, event.message]);
      }
      return;
    }
    if (event.type === "message.updated") {
      const cached = this.readMessagesCache(event.sessionId);
      if (!cached) {
        return;
      }
      const next = cached.map((message) =>
        message.id === event.messageId
          ? {
              ...message,
              status: event.status ?? message.status,
              parts: event.replaceParts ?? [...message.parts, ...(event.appendParts ?? [])],
            }
          : message,
      );
      this.writeMessagesCache(event.sessionId, next);
      return;
    }
    if (event.type === "session.updated") {
      const cached = this.readSessionsCache(event.session.agentId) ?? [];
      const next = [event.session, ...cached.filter((session) => session.id !== event.session.id)].sort((left, right) =>
        right.updatedAt.localeCompare(left.updatedAt),
      );
      this.writeSessionsCache(event.session.agentId, next);
    }
  }

  private async fetchClientApiJson(pathname: string, init?: RequestInit): Promise<Record<string, unknown>> {
    const response = await fetch(`${this.clientApiBaseUrl}${pathname}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
    const payload = (await response.json()) as Record<string, unknown>;
    if (!response.ok || payload.ok === false) {
      const error = (payload.error as Record<string, unknown> | undefined) ?? {};
      throw new Error(String(error.message ?? `Client API request failed: ${response.status}`));
    }
    return payload;
  }

  private async isClientApiHealthy(): Promise<boolean> {
    if (Date.now() < this.healthyUntil) {
      return true;
    }
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 500);
      const response = await fetch(`${this.clientApiBaseUrl}/api/v1/health`, {
        signal: controller.signal,
      });
      clearTimeout(timeout);
      if (!response.ok) {
        return false;
      }
      const payload = (await response.json()) as unknown;
      const healthy = isOpenPpxClientApiHealthPayload(payload);
      if (healthy) {
        this.healthyUntil = Date.now() + OpenPpxLocalAdapter.HEALTH_CACHE_TTL_MS;
      }
      return healthy;
    } catch {
      return false;
    }
  }

  private async ensureClientApiAvailable(): Promise<boolean> {
    if (Date.now() < this.healthyUntil) {
      return true;
    }
    if (this.inflightHealthCheck) {
      return this.inflightHealthCheck;
    }
    this.inflightHealthCheck = this.ensureClientApiAvailableImpl();
    try {
      return await this.inflightHealthCheck;
    } finally {
      this.inflightHealthCheck = null;
    }
  }

  private async ensureClientApiAvailableImpl(): Promise<boolean> {
    if (await this.isClientApiHealthy()) {
      clientDebugLog("client-api.health", {
        baseUrl: this.clientApiBaseUrl,
        status: "healthy",
      });
      return true;
    }
    if (this.isRemoteTarget()) {
      clientDebugLog("client-api.health", {
        baseUrl: this.clientApiBaseUrl,
        status: "remote-unreachable",
        target: this.target,
      });
      return false;
    }
    if (!fs.existsSync(this.openppxRoot)) {
      clientDebugLog("client-api.health", {
        baseUrl: this.clientApiBaseUrl,
        status: "openppx-root-missing",
        openppxRoot: this.openppxRoot,
      });
      return false;
    }
    let managedProcess = this.clientApiProcess;
    if (!managedProcess) {
      this.clientApiStartupError = "";
      clientDebugLog("client-api.spawn", {
        baseUrl: this.clientApiBaseUrl,
        pythonBin: this.pythonBin,
        openppxRoot: this.openppxRoot,
      });
      const child = spawn(
        this.pythonBin,
        ["-m", "openppx.cli", "client-api", "serve", "--host", this.clientApiHost, "--port", String(this.clientApiPort)],
        {
          cwd: this.openppxRoot,
          env: buildClientApiSpawnEnv(dataRootPath(), process.env),
          stdio: ["ignore", "pipe", "pipe"],
        },
      );
      this.clientApiProcess = child;
      managedProcess = child;
      let stdout = "";
      let stderr = "";
      child.stdout?.on("data", (chunk: Buffer | string) => {
        const text = chunk.toString();
        stdout = appendClientApiLogTail(stdout, text);
        clientDebugLog("client-api.stdout", text.trim());
      });
      child.stderr?.on("data", (chunk: Buffer | string) => {
        const text = chunk.toString();
        stderr = appendClientApiLogTail(stderr, text);
        clientDebugLog("client-api.stderr", text.trim());
      });
      child.on("error", (error) => {
        if (this.clientApiProcess === child) {
          this.clientApiStartupError = formatClientApiStartupError(error.message, stdout);
        }
      });
      child.on("close", (code) => {
        if (this.clientApiProcess === child && code !== 0 && !this.clientApiStartupError) {
          this.clientApiStartupError = formatClientApiStartupError(stderr, stdout);
        }
        clientDebugLog("client-api.close", { baseUrl: this.clientApiBaseUrl, code });
        this.clientApiProcess = managedProcessAfterClose(this.clientApiProcess, child);
        this.healthyUntil = 0;
      });
    }
    for (let attempt = 0; attempt < 12; attempt += 1) {
      await delay(250);
      if (await this.isClientApiHealthy()) {
        clientDebugLog("client-api.health", {
          baseUrl: this.clientApiBaseUrl,
          status: "healthy-after-spawn",
          attempt: attempt + 1,
        });
        return true;
      }
    }
    clientDebugLog("client-api.health", {
      baseUrl: this.clientApiBaseUrl,
      status: "unreachable",
    });
    if (managedProcess && this.clientApiProcess === managedProcess) {
      if (managedProcess.exitCode === null) {
        managedProcess.kill();
      }
      this.clientApiProcess = null;
    }
    throw new Error(
      this.clientApiStartupError || formatClientApiStartupError("", ""),
    );
  }

  private shouldUseMock(): boolean {
    if (this.isRemoteTarget()) {
      return false;
    }
    return !fs.existsSync(this.openppxRoot);
  }

  private listRealAgents(): AgentProfile[] {
    if (this.isRemoteTarget()) {
      return [];
    }
    const raw = readJsonFile<GlobalAgentConfig>(globalConfigPath());
    if (!raw) {
      return [];
    }

    const entries = Array.isArray(raw.agents)
      ? raw.agents
      : Array.isArray(raw.agents?.list)
        ? raw.agents.list
        : [];

    const agents: Array<AgentProfile | null> = entries.map((entry) => {
      const name = normalizeAgentName(String(entry.name ?? entry.id ?? ""));
      if (!name || entry.enabled === false) {
        return null;
      }
      const config = readJsonFile<{ agent?: { workspace?: string } }>(agentConfigPath(name));
      const workspace = config?.agent?.workspace?.trim() ?? "";
      return {
        id: name,
        name,
        description: workspace ? `Workspace: ${workspace}` : "Local openppx agent",
        enabled: true,
        status: "healthy",
        tags: ["local", "openppx"],
      };
    });
    return agents.filter((item): item is AgentProfile => item !== null);
  }

  private getFallbackRuntimeStatus(): RuntimeStatus {
    if (this.isRemoteTarget()) {
      return {
        target: this.target,
        state: "error",
        summary: "Remote client-api gateway is unavailable.",
        detail: `Check the remote gateway at ${this.clientApiBaseUrl}. The desktop client is not yet starting remote runtimes on demand.`,
        lastError: "REMOTE_GATEWAY_UNAVAILABLE",
      };
    }
    if (!fs.existsSync(this.openppxRoot)) {
      return {
        target: this.target,
        state: "error",
        summary: "openppx root was not found.",
        detail: "Set OPENPPX_ROOT or keep gm-science-desktop beside gm-science-runtime.",
        lastError: "OPENPPX_ROOT_NOT_FOUND",
      };
    }
    if (!fs.existsSync(globalConfigPath())) {
      return {
        target: this.target,
        state: "starting",
        summary: "openppx config is not initialized yet.",
        detail: "Run gm-science setup first so ~/.gm-science/global_config.json exists.",
      };
    }
    return {
      target: this.target,
      state: "healthy",
      summary: "Local openppx runtime is available.",
      detail: "The desktop client uses the managed local client-api gateway.",
    };
  }

  private async fetchRuntimeStatus(): Promise<RuntimeStatus> {
    if (await this.ensureClientApiAvailable()) {
      const payload = await this.fetchClientApiJson("/api/v1/runtime/status");
      const runtime = normalizeClientApiRuntime((payload.data as Record<string, unknown> | undefined) ?? {});
      if (runtime) {
        return runtime;
      }
    }
    return this.getFallbackRuntimeStatus();
  }

  public async bootstrap(): Promise<BootstrapPayload> {
    if (this.shouldUseMock()) {
      return mockBootstrap();
    }

    const runtime = await this.fetchRuntimeStatus();
    const payload = await this.fetchClientApiJson("/api/v1/agents");
    const items = Array.isArray((payload.data as Record<string, unknown> | undefined)?.items)
      ? ((payload.data as Record<string, unknown>).items as Array<Record<string, unknown>>)
      : [];
    const agents = items.map((item) => normalizeAgentProfile(item));

    const selectedAgentId = agents[0]?.id ?? "";
    const sessions = selectedAgentId ? (await this.listSessions(selectedAgentId)).sessions : [];
    const selectedSessionId = sessions[0]?.id ?? "";
    const messages = selectedSessionId ? (await this.loadSession(selectedSessionId)).messages : [];
    return {
      runtime,
      agents,
      sessions,
      messages,
      selectedAgentId,
      selectedSessionId,
    };
  }

  public async getDiagnostics(): Promise<ClientDiagnostics> {
    const realAgents = this.listRealAgents();
    return {
      mode: this.shouldUseMock() ? "mock" : this.isRemoteTarget() ? "remote" : "local",
      target: this.target,
      openppxRoot: this.openppxRoot,
      openppxRootExists: fs.existsSync(this.openppxRoot),
      pythonBin: this.pythonBin,
      globalConfigPath: globalConfigPath(),
      globalConfigExists: fs.existsSync(globalConfigPath()),
      clientApiBaseUrl: this.clientApiBaseUrl,
      clientApiManagedByClient: !this.isRemoteTarget(),
      clientApiHealthy: await this.isClientApiHealthy(),
      clientApiProcessRunning: !!this.clientApiProcess && this.clientApiProcess.exitCode === null,
      agentCount: realAgents.length,
      sessionCacheEntries: this.sessionsCache.size,
      messageCacheEntries: this.messagesCache.size,
      debugEnabled: clientDebugEnabled(),
    };
  }

  public async saveConnectionSettings(settings: ConnectionSettings): Promise<ClientDiagnostics> {
    this.applyConnectionSettings(settings);
    return this.getDiagnostics();
  }

  public async listGmScienceProjects(): Promise<{ projects: GmScienceProject[] }> {
    if (this.shouldUseMock()) {
      return mockListGmScienceProjects();
    }
    if (!(await this.ensureClientApiAvailable())) {
      return { projects: [] };
    }
    const payload = await this.fetchClientApiJson("/api/v1/gm-science/projects");
    const items = Array.isArray((payload.data as Record<string, unknown> | undefined)?.items)
      ? ((payload.data as Record<string, unknown>).items as unknown[])
      : [];
    const projects = items
      .map((item) => normalizeGmScienceProject(item))
      .filter((item): item is GmScienceProject => item !== null);
    return { projects };
  }

  public async createGmScienceProject(
    input: CreateGmScienceProjectInput,
  ): Promise<{ project: GmScienceProject }> {
    if (this.shouldUseMock()) {
      return mockCreateGmScienceProject(input);
    }
    if (!(await this.ensureClientApiAvailable())) {
      throw new Error("Local gm-science client-api is unavailable.");
    }
    const payload = await this.fetchClientApiJson("/api/v1/gm-science/projects", {
      method: "POST",
      body: JSON.stringify(buildCreateGmScienceProjectPayload(input)),
    });
    const project = normalizeGmScienceProject((payload.data as Record<string, unknown> | undefined)?.project);
    if (!project) {
      throw new Error("Client API returned an invalid project payload.");
    }
    return { project };
  }

  public async getGmScienceProject(projectId: string): Promise<{ project: GmScienceProject }> {
    if (this.shouldUseMock()) {
      return mockGetGmScienceProject(projectId);
    }
    if (!(await this.ensureClientApiAvailable())) {
      throw new Error("Local gm-science client-api is unavailable.");
    }
    const payload = await this.fetchClientApiJson(`/api/v1/gm-science/projects/${encodeURIComponent(projectId)}`);
    const project = normalizeGmScienceProject((payload.data as Record<string, unknown> | undefined)?.project);
    if (!project) {
      throw new Error("Client API returned an invalid project payload.");
    }
    return { project };
  }

  public async listGmScienceCapabilities(projectId?: string): Promise<GmScienceCapabilityCatalog> {
    if (this.shouldUseMock()) {
      return mockListGmScienceCapabilities(projectId);
    }
    if (!(await this.ensureClientApiAvailable())) {
      throw new Error("Local gm-science client-api is unavailable.");
    }
    const path = projectId
      ? `/api/v1/gm-science/projects/${encodeURIComponent(projectId)}/capabilities`
      : "/api/v1/gm-science/capabilities";
    const payload = await this.fetchClientApiJson(path);
    const data = (payload.data as Record<string, unknown> | undefined) ?? {};
    const items = Array.isArray(data.items) ? data.items : [];
    return {
      projectId: String(data.project_id ?? ""),
      items: items
        .map((item) => normalizeGmScienceCapability(item))
        .filter((item): item is GmScienceCapability => item !== null),
    };
  }

  public async updateGmScienceProjectCapabilities(
    projectId: string,
    input: UpdateGmScienceCapabilitiesInput,
  ): Promise<{ project: GmScienceProject; capabilities: GmScienceCapability[] }> {
    if (this.shouldUseMock()) {
      return mockUpdateGmScienceProjectCapabilities(projectId, input);
    }
    if (!(await this.ensureClientApiAvailable())) {
      throw new Error("Local gm-science client-api is unavailable.");
    }
    const payload = await this.fetchClientApiJson(
      `/api/v1/gm-science/projects/${encodeURIComponent(projectId)}/capabilities`,
      {
        method: "PATCH",
        body: JSON.stringify({
          enabled_skills: input.enabledSkills,
          enabled_connectors: input.enabledConnectors,
          enabled_specialists: input.enabledSpecialists,
        }),
      },
    );
    const data = (payload.data as Record<string, unknown> | undefined) ?? {};
    const project = normalizeGmScienceProject(data.project);
    const rawCapabilities = Array.isArray(data.capabilities) ? data.capabilities : [];
    const capabilities = rawCapabilities
      .map((item) => normalizeGmScienceCapability(item))
      .filter((item): item is GmScienceCapability => item !== null);
    if (!project) {
      throw new Error("Client API returned an invalid project capability payload.");
    }
    return { project, capabilities };
  }

  public async listGmScienceArtifacts(projectId: string): Promise<{ artifacts: GmScienceArtifact[] }> {
    if (this.shouldUseMock()) {
      return mockListGmScienceArtifacts(projectId);
    }
    if (!(await this.ensureClientApiAvailable())) {
      return { artifacts: [] };
    }
    const payload = await this.fetchClientApiJson(
      `/api/v1/gm-science/projects/${encodeURIComponent(projectId)}/artifacts`,
    );
    const items = Array.isArray((payload.data as Record<string, unknown> | undefined)?.items)
      ? ((payload.data as Record<string, unknown>).items as unknown[])
      : [];
    const artifacts = items
      .map((item) => normalizeGmScienceArtifact(item))
      .filter((item): item is GmScienceArtifact => item !== null);
    return { artifacts };
  }

  public async createGmScienceArtifact(
    projectId: string,
    input: CreateGmScienceArtifactInput,
  ): Promise<{ artifact: GmScienceArtifact }> {
    if (this.shouldUseMock()) {
      return mockCreateGmScienceArtifact(projectId, input);
    }
    if (!(await this.ensureClientApiAvailable())) {
      throw new Error("Local gm-science client-api is unavailable.");
    }
    const payload = await this.fetchClientApiJson(
      `/api/v1/gm-science/projects/${encodeURIComponent(projectId)}/artifacts`,
      {
        method: "POST",
        body: JSON.stringify({
          type: input.type,
          title: input.title,
          path_or_url: input.pathOrUrl ?? "",
          mime_type: input.mimeType ?? "",
          session_id: input.sessionId ?? "",
          metadata: input.metadata ?? {},
          provenance: input.provenance ?? {},
        }),
      },
    );
    const artifact = normalizeGmScienceArtifact((payload.data as Record<string, unknown> | undefined)?.artifact);
    if (!artifact) {
      throw new Error("Client API returned an invalid artifact payload.");
    }
    return { artifact };
  }

  public async runRuntimeCommand(command: RuntimeCommand): Promise<RuntimeStatus> {
    if (this.shouldUseMock()) {
      return mockRunRuntimeCommand(command);
    }
    if (this.isRemoteTarget()) {
      return {
        ...this.getFallbackRuntimeStatus(),
        summary: "Remote gateway control is not supported from the desktop client yet.",
        detail: `This target is configured as remote. Manage the gateway directly at ${this.clientApiBaseUrl}.`,
      };
    }
    if (command === "stop") {
      this.stopManagedClientApiProcess();
      return {
        ...this.getFallbackRuntimeStatus(),
        state: "stopped",
        summary: "Local client-api process was stopped.",
        detail: "The next request can start it again on demand.",
      };
    }
    if (command === "restart") {
      this.stopManagedClientApiProcess();
    }
    if (command === "start" || command === "restart") {
      await this.ensureClientApiAvailable();
    }
    return this.fetchRuntimeStatus();
  }

  public async listSessions(agentId: string): Promise<{ sessions: SessionSummary[] }> {
    if (this.shouldUseMock()) {
      return mockListSessions(agentId);
    }
    const cached = this.readSessionsCache(agentId);
    if (cached) {
      clientDebugLog("sessions.cache.hit", {
        agentId,
        count: cached.length,
      });
      return { sessions: cached };
    }
    if (!(await this.ensureClientApiAvailable())) {
      return { sessions: [] };
    }
    const payload = await this.fetchClientApiJson(`/api/v1/agents/${agentId}/sessions`);
    const items = Array.isArray((payload.data as Record<string, unknown> | undefined)?.items)
      ? ((payload.data as Record<string, unknown>).items as unknown[])
      : [];
    const sessions = items
      .map((item) => normalizeClientApiSession(item))
      .filter((item): item is SessionSummary => item !== null);
    this.writeSessionsCache(agentId, sessions);
    return { sessions };
  }

  public async createSession(agentId: string, projectId?: string): Promise<{ session: SessionSummary }> {
    if (this.shouldUseMock()) {
      return mockCreateSession(agentId, projectId);
    }
    if (!(await this.ensureClientApiAvailable())) {
      throw new Error(`Remote gateway is unavailable for target ${this.target.name}.`);
    }
    const payload = await this.fetchClientApiJson(`/api/v1/agents/${agentId}/sessions`, {
      method: "POST",
      body: JSON.stringify({ project_id: projectId ?? "" }),
    });
    const session = normalizeClientApiSession((payload.data as Record<string, unknown> | undefined)?.session);
    if (!session) {
      throw new Error("Client API returned an invalid session payload.");
    }
    this.invalidateSessionCaches(agentId);
    return { session };
  }

  public async loadSession(sessionId: string): Promise<{ messages: ChatMessage[] }> {
    if (this.shouldUseMock()) {
      return mockLoadSession(sessionId);
    }
    const cached = this.readMessagesCache(sessionId);
    if (cached) {
      clientDebugLog("messages.cache.hit", {
        sessionId,
        count: cached.length,
      });
      return { messages: cached };
    }
    if (!(await this.ensureClientApiAvailable())) {
      return { messages: [] };
    }
    const payload = await this.fetchClientApiJson(`/api/v1/sessions/${sessionId}/messages`);
    const items = Array.isArray((payload.data as Record<string, unknown> | undefined)?.items)
      ? ((payload.data as Record<string, unknown>).items as unknown[])
      : [];
    const messages = items
      .map((item) => normalizeClientApiMessage(item))
      .filter((item): item is ChatMessage => item !== null);
    this.writeMessagesCache(sessionId, messages);
    return { messages };
  }

  public async sendMessage(input: SendMessageInput): Promise<{ runId: string }> {
    clientDebugLog("send.start", {
      agentId: input.agentId,
      sessionId: input.sessionId,
      textPreview: input.text.slice(0, 240),
      mode: this.shouldUseMock() ? "mock" : "local",
    });
    if (this.shouldUseMock()) {
      return mockSendMessage(input);
    }
    this.invalidateSessionCaches(input.agentId, input.sessionId);
    if (!(await this.ensureClientApiAvailable())) {
      throw new Error(`Remote gateway is unavailable for target ${this.target.name}.`);
    }
    return this.sendMessageViaClientApi(input);
  }

  private async sendMessageViaClientApi(input: SendMessageInput): Promise<{ runId: string }> {
    const payload = await this.fetchClientApiJson(buildClientApiRunPath(input), {
      method: "POST",
      body: JSON.stringify({ text: input.text, agent_id: input.agentId }),
    });
    const run = ((payload.data as Record<string, unknown> | undefined)?.run ?? {}) as Record<string, unknown>;
    const runId = String(run.id ?? `run-${crypto.randomUUID()}`);
    clientDebugLog("send.client-api.run-created", {
      runId,
      agentId: input.agentId,
      sessionId: input.sessionId,
    });
    const sessionPayload = await this.listSessions(input.agentId);
    const session = sessionPayload.sessions.find((item) => item.id === input.sessionId) ?? {
      id: input.sessionId,
      agentId: input.agentId,
      projectId: input.projectId,
      title: "Local session",
      updatedAt: now(),
      lastMessagePreview: input.text,
    };

    const response = await fetch(`${this.clientApiBaseUrl}/api/v1/runs/${runId}/events`);
    if (!response.ok || !response.body) {
      throw new Error(`Failed opening run event stream for ${runId}`);
    }
    clientDebugLog("send.client-api.stream-open", {
      runId,
      url: `${this.clientApiBaseUrl}/api/v1/runs/${runId}/events`,
    });

    await new Promise<void>(async (resolve, reject) => {
      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let assistantMessage: ChatMessage | null = null;
      let finalText = "";
      let stepParts: StepPart[] = [];
      let terminalEventReceived = false;

      const syncAssistant = (status: ChatMessage["status"]): void => {
        if (!assistantMessage) {
          return;
        }
        assistantMessage.status = status;
        assistantMessage.parts = mergeAssistantParts(stepParts, finalText);
          this.emit({
            type: "message.updated",
            runId,
            sessionId: assistantMessage.sessionId,
            messageId: assistantMessage.id,
            replaceParts: assistantMessage.parts,
            status,
          });
      };

      const handleClientApiEvent = (eventName: string, data: Record<string, unknown>): void => {
        clientDebugLog("send.client-api.event", {
          runId,
          eventName,
          keys: Object.keys(data),
        });
        if (eventName === "message.created") {
          const message = normalizeClientApiMessage(data.message);
          if (!message) {
            return;
          }
          assistantMessage = message;
          stepParts = message.parts.filter((part): part is StepPart => part.type === "step_ref");
          this.emit({ type: "message.created", runId, sessionId: message.sessionId, message });
          return;
        }
        if (eventName === "step.updated" && assistantMessage) {
          const stepPart = normalizeClientApiPart(data.step);
          if (stepPart?.type !== "step_ref") {
            return;
          }
          stepParts = [
            ...stepParts.filter((part) => part.stepId !== stepPart.stepId),
            stepPart,
          ];
          syncAssistant("streaming");
          return;
        }
        if (eventName === "message.delta" && assistantMessage) {
          const part = normalizeClientApiPart(data.part);
          if (part?.type === "markdown") {
            finalText = part.text;
            syncAssistant("streaming");
          }
          return;
        }
        if (eventName === "message.completed" && assistantMessage) {
          const message = normalizeClientApiMessage(data.message);
          finalText = message?.parts.find((part) => part.type === "markdown")?.text ?? finalText;
          stepParts = stepParts.map((part) => (part.status === "running" ? { ...part, status: "completed" } : part));
          syncAssistant("completed");
          return;
        }
        if (eventName === "message.failed" && assistantMessage) {
          const errorPart = normalizeClientApiPart(data.error);
          if (errorPart?.type === "error") {
            this.emit({
              type: "message.updated",
              runId,
              sessionId: assistantMessage.sessionId,
              messageId: assistantMessage.id,
              replaceParts: [errorPart],
              status: "failed",
            });
          }
          return;
        }
        if (eventName === "message.cancelled" && assistantMessage) {
          this.emit({
            type: "message.updated",
            runId,
            sessionId: assistantMessage.sessionId,
            messageId: assistantMessage.id,
            replaceParts: mergeAssistantParts(
              stepParts.map((part) => (part.status === "running" ? { ...part, status: "failed" } : part)),
              finalText,
            ),
            status: "cancelled",
          });
          return;
        }
        if (eventName === "run.finished") {
          session.updatedAt = now();
          session.lastMessagePreview = finalText || input.text;
          this.emit({ type: "session.updated", runId, session });
          this.emit({ type: "run.finished", runId, sessionId: input.sessionId });
          clientDebugLog("send.client-api.finished", {
            runId,
            status: "completed",
            finalTextLength: finalText.length,
          });
          terminalEventReceived = true;
          return;
        }
        if (eventName === "run.cancelled") {
          this.emit({ type: "run.finished", runId, sessionId: input.sessionId });
          terminalEventReceived = true;
        }
      };

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            clientDebugLog("send.client-api.stream-closed", { runId });
            break;
          }
          buffer += decoder.decode(value, { stream: true });
          const frames = buffer.split("\n\n");
          buffer = frames.pop() ?? "";
          for (const frame of frames) {
            const lines = frame.split("\n");
            let eventName = "message";
            let dataLine = "";
            for (const line of lines) {
              if (line.startsWith("event:")) {
                eventName = line.slice(6).trim();
              } else if (line.startsWith("data:")) {
                dataLine += line.slice(5).trim();
              }
            }
            if (!dataLine) {
              continue;
            }
            handleClientApiEvent(eventName, JSON.parse(dataLine) as Record<string, unknown>);
            if (terminalEventReceived) {
              clientDebugLog("send.client-api.stream-terminal", { runId, eventName });
              void reader.cancel().catch(() => undefined);
              resolve();
              return;
            }
          }
        }
        resolve();
      } catch (error) {
        clientDebugLog("send.client-api.stream-error", {
          runId,
          error: error instanceof Error ? error.message : String(error),
        });
        reject(error);
      }
    });

    return { runId };
  }

  public onRunEvent(listener: (event: RunEvent) => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  public dispose(): void {
    this.mockUnsubscribe();
    this.stopManagedClientApiProcess();
  }

  private stopManagedClientApiProcess(): void {
    const current = this.clientApiProcess;
    if (current && current.exitCode === null) {
      current.kill();
    }
    if (this.clientApiProcess === current) {
      this.clientApiProcess = null;
    }
    this.healthyUntil = 0;
  }
}
