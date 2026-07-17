import type {
  ChatMessage,
  GmScienceCapability,
  GmScienceArtifact,
  GmScienceProject,
  GmScienceRun,
  GmScienceRunStatus,
  MessagePart,
  MessageRole,
  MessageStatus,
  RuntimeState,
  RuntimeStatus,
  SessionSummary,
} from "../types";

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => String(item)).filter((item) => item.trim().length > 0);
}

function asLooseRecord(value: unknown): Record<string, unknown> {
  const record = asRecord(value);
  return record ? { ...record } : {};
}

function normalizeRole(value: unknown): MessageRole {
  const role = asString(value, "assistant");
  if (role === "user" || role === "assistant" || role === "system" || role === "tool") {
    return role;
  }
  return "assistant";
}

function normalizeStatus(value: unknown, fallback: MessageStatus): MessageStatus {
  const status = asString(value, fallback);
  if (status === "streaming" || status === "completed" || status === "failed" || status === "cancelled") {
    return status;
  }
  return fallback;
}

function normalizeRuntimeState(value: unknown): RuntimeState {
  const state = asString(value, "healthy");
  if (state === "stopped" || state === "starting" || state === "healthy" || state === "error") {
    return state;
  }
  return "healthy";
}

export function normalizeClientApiPart(payload: unknown): MessagePart | null {
  const part = asRecord(payload);
  if (!part) {
    return null;
  }
  const type = asString(part.type);
  if (type === "markdown") {
    return { type, text: asString(part.text) };
  }
  if (type === "code") {
    return { type, text: asString(part.text), language: asString(part.language) || undefined };
  }
  if (type === "file") {
    return {
      type,
      text: asString(part.text),
      fileName: asString(part.file_name ?? part.fileName, "file"),
      sizeBytes: typeof part.size_bytes === "number" ? part.size_bytes : undefined,
      mimeType: asString(part.mime_type) || undefined,
    };
  }
  if (type === "image") {
    return {
      type,
      text: asString(part.text),
      url: asString(part.url),
      mimeType: asString(part.mime_type) || undefined,
    };
  }
  if (type === "error") {
    return {
      type,
      text: asString(part.text),
      errorCode: asString(part.error_code) || undefined,
    };
  }
  if (type === "tool_result") {
    return {
      type,
      toolName: asString(part.tool_name ?? part.toolName, "tool"),
      summary: asString(part.summary, "Tool returned without a payload"),
      detail: asString(part.detail) || undefined,
      rawText: asString(part.raw_text ?? part.rawText) || undefined,
    };
  }
  if (type === "step_ref") {
    const status = asString(part.status, "running");
    return {
      type,
      stepId: asString(part.step_id ?? part.stepId, "step"),
      title: asString(part.title, "step"),
      status: status === "completed" || status === "failed" ? status : "running",
      detail: asString(part.detail),
    };
  }
  return null;
}

export function normalizeClientApiMessage(payload: unknown): ChatMessage | null {
  const message = asRecord(payload);
  if (!message) {
    return null;
  }
  const rawParts = Array.isArray(message.parts) ? message.parts : [];
  return {
    id: asString(message.id),
    sessionId: asString(message.session_id ?? message.sessionId),
    role: normalizeRole(message.role),
    status: normalizeStatus(message.status, "completed"),
    createdAt: asString(message.created_at ?? message.createdAt, new Date().toISOString()),
    parts: rawParts
      .map((part) => normalizeClientApiPart(part))
      .filter((part): part is MessagePart => part !== null),
  };
}

export function normalizeClientApiSession(payload: unknown): SessionSummary | null {
  const session = asRecord(payload);
  if (!session) {
    return null;
  }
  return {
    id: asString(session.id),
    agentId: asString(session.agent_id ?? session.agentId),
    projectId: asString(session.project_id ?? session.projectId) || undefined,
    title: asString(session.title, "Session"),
    updatedAt: asString(session.updated_at ?? session.updatedAt, new Date().toISOString()),
    lastMessagePreview: asString(session.last_message_preview ?? session.lastMessagePreview, ""),
  };
}

export function normalizeClientApiRuntime(payload: unknown): RuntimeStatus | null {
  const runtime = asRecord(payload);
  const target = asRecord(runtime?.target);
  if (!runtime || !target) {
    return null;
  }
  return {
    target: {
      id: asString(target.id, "local-default"),
      type: asString(target.type) === "remote" ? "remote" : "local",
      name: asString(target.name, "This Mac"),
    },
    state: normalizeRuntimeState(runtime.state),
    summary: asString(runtime.summary),
    detail: asString(runtime.detail) || undefined,
    lastError: asString(runtime.lastError ?? runtime.last_error) || undefined,
  };
}

export function normalizeGmScienceProject(payload: unknown): GmScienceProject | null {
  const project = asRecord(payload);
  if (!project) {
    return null;
  }
  return {
    id: asString(project.id),
    name: asString(project.name),
    description: asString(project.description),
    agentContext: asString(project.agent_context ?? project.agentContext),
    workspacePath: asString(project.workspace_path ?? project.workspacePath),
    sessionsCount: asNumber(project.sessions_count ?? project.sessionsCount),
    artifactsCount: asNumber(project.artifacts_count ?? project.artifactsCount),
    enabledSkills: asStringList(project.enabled_skills ?? project.enabledSkills),
    enabledConnectors: asStringList(project.enabled_connectors ?? project.enabledConnectors),
    enabledSpecialists: asStringList(project.enabled_specialists ?? project.enabledSpecialists),
    createdAt: asString(project.created_at ?? project.createdAt, new Date().toISOString()),
    updatedAt: asString(project.updated_at ?? project.updatedAt, new Date().toISOString()),
  };
}

export function normalizeGmScienceCapability(payload: unknown): GmScienceCapability | null {
  const capability = asRecord(payload);
  if (!capability) {
    return null;
  }
  const kind = asString(capability.kind);
  const status = asString(capability.status);
  if (kind !== "skill" && kind !== "connector" && kind !== "specialist") {
    return null;
  }
  if (status !== "ready" && status !== "needs_configuration" && status !== "disabled") {
    return null;
  }
  return {
    id: asString(capability.id),
    kind,
    name: asString(capability.name),
    description: asString(capability.description),
    available: capability.available === true,
    defaultEnabled: capability.default_enabled === true || capability.defaultEnabled === true,
    projectEnabled:
      typeof (capability.project_enabled ?? capability.projectEnabled) === "boolean"
        ? Boolean(capability.project_enabled ?? capability.projectEnabled)
        : null,
    status,
    statusDetail: asString(capability.status_detail ?? capability.statusDetail),
    metadata: asLooseRecord(capability.metadata),
  };
}

export function normalizeGmScienceArtifact(payload: unknown): GmScienceArtifact | null {
  const artifact = asRecord(payload);
  if (!artifact) {
    return null;
  }
  return {
    id: asString(artifact.id),
    projectId: asString(artifact.project_id ?? artifact.projectId),
    sessionId: asString(artifact.session_id ?? artifact.sessionId),
    type: asString(artifact.type),
    title: asString(artifact.title),
    pathOrUrl: asString(artifact.path_or_url ?? artifact.pathOrUrl),
    mimeType: asString(artifact.mime_type ?? artifact.mimeType),
    metadata: asLooseRecord(artifact.metadata),
    provenance: asLooseRecord(artifact.provenance),
    createdAt: asString(artifact.created_at ?? artifact.createdAt, new Date().toISOString()),
    updatedAt: asString(artifact.updated_at ?? artifact.updatedAt, new Date().toISOString()),
  };
}

const GM_SCIENCE_RUN_STATUSES = new Set<GmScienceRunStatus>([
  "queued",
  "running",
  "paused",
  "waiting_user",
  "waiting_approval",
  "interrupted",
  "stale",
  "completed",
  "failed",
  "cancelled",
  "lost",
]);

export function normalizeGmScienceRun(payload: unknown): GmScienceRun | null {
  const run = asRecord(payload);
  if (!run) {
    return null;
  }
  const status = asString(run.status) as GmScienceRunStatus;
  if (!GM_SCIENCE_RUN_STATUSES.has(status)) {
    return null;
  }
  const controls = asRecord(run.controls) ?? {};
  const endedAt = run.ended_at_ms ?? run.endedAtMs;
  return {
    taskId: asString(run.task_id ?? run.taskId),
    projectId: asString(run.project_id ?? run.projectId),
    sessionId: asString(run.session_id ?? run.sessionId),
    parentTaskId: asString(run.parent_task_id ?? run.parentTaskId),
    kind: asString(run.kind),
    title: asString(run.title),
    status,
    progressSummary: asString(run.progress_summary ?? run.progressSummary),
    terminalSummary: asString(run.terminal_summary ?? run.terminalSummary),
    lastError: asString(run.last_error ?? run.lastError),
    createdAt: asString(run.created_at ?? run.createdAt, new Date().toISOString()),
    updatedAt: asString(run.updated_at ?? run.updatedAt, new Date().toISOString()),
    createdAtMs: asNumber(run.created_at_ms ?? run.createdAtMs),
    updatedAtMs: asNumber(run.updated_at_ms ?? run.updatedAtMs),
    endedAtMs: typeof endedAt === "number" && Number.isFinite(endedAt) ? endedAt : null,
    canCancel: controls.can_cancel === true || controls.canCancel === true,
    canRetry: run.can_retry === true || run.canRetry === true,
    logPreview: asString(run.log_preview ?? run.logPreview),
    artifactIds: asStringList(run.artifact_ids ?? run.artifactIds),
  };
}
