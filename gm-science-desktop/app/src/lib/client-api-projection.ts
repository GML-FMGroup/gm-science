import type {
  ChatMessage,
  GmScienceCapability,
  GmScienceAnalysis,
  GmScienceArtifact,
  GmScienceDataset,
  GmScienceDatasetColumnProfile,
  GmScienceDatasetProfile,
  GmScienceProject,
  GmScienceResource,
  GmScienceResourceAccessMode,
  GmScienceResourceKind,
  GmScienceResourceSource,
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

function asNullableNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
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
  const source = asString(capability.source);
  if (kind !== "skill" && kind !== "connector" && kind !== "specialist") {
    return null;
  }
  if (status !== "ready" && status !== "needs_configuration" && status !== "disabled") {
    return null;
  }
  if (source !== "built_in" && source !== "local" && source !== "external") {
    return null;
  }
  return {
    id: asString(capability.id),
    kind,
    name: asString(capability.name),
    description: asString(capability.description),
    source,
    version: asString(capability.version),
    license: asString(capability.license),
    files: asStringList(capability.files),
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

const GM_SCIENCE_RESOURCE_KINDS = new Set<GmScienceResourceKind>([
  "artifact",
  "dataset",
  "run_output",
  "project_file",
]);
const GM_SCIENCE_RESOURCE_ACCESS_MODES = new Set<GmScienceResourceAccessMode>([
  "read",
  "external",
  "metadata_only",
]);
const GM_SCIENCE_RESOURCE_SOURCES = new Set<GmScienceResourceSource>(["artifact", "workspace"]);

export function normalizeGmScienceResource(payload: unknown): GmScienceResource | null {
  const resource = asRecord(payload);
  if (!resource) {
    return null;
  }
  const kind = asString(resource.kind) as GmScienceResourceKind;
  const accessMode = asString(resource.access_mode ?? resource.accessMode) as GmScienceResourceAccessMode;
  const source = asString(resource.source) as GmScienceResourceSource;
  if (
    !GM_SCIENCE_RESOURCE_KINDS.has(kind) ||
    !GM_SCIENCE_RESOURCE_ACCESS_MODES.has(accessMode) ||
    !GM_SCIENCE_RESOURCE_SOURCES.has(source)
  ) {
    return null;
  }
  return {
    id: asString(resource.id),
    kind,
    projectId: asString(resource.project_id ?? resource.projectId),
    sessionId: asString(resource.session_id ?? resource.sessionId),
    displayName: asString(resource.display_name ?? resource.displayName),
    artifactType: asString(resource.artifact_type ?? resource.artifactType),
    mimeType: asString(resource.mime_type ?? resource.mimeType),
    versionOrHash: asString(resource.version_or_hash ?? resource.versionOrHash),
    accessMode,
    source,
    artifactId: asString(resource.artifact_id ?? resource.artifactId),
    relativePath: asString(resource.relative_path ?? resource.relativePath),
    url: asString(resource.url),
    sizeBytes: asNullableNumber(resource.size_bytes ?? resource.sizeBytes),
    createdAt: asString(resource.created_at ?? resource.createdAt),
    updatedAt: asString(resource.updated_at ?? resource.updatedAt),
    metadata: asLooseRecord(resource.metadata),
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

function normalizeDatasetColumn(payload: unknown): GmScienceDatasetColumnProfile | null {
  const column = asRecord(payload);
  if (!column) {
    return null;
  }
  const numeric = asRecord(column.numeric);
  const topValues = Array.isArray(column.top_values ?? column.topValues)
    ? (column.top_values ?? column.topValues) as unknown[]
    : [];
  const typeCountsRaw = asRecord(column.type_counts ?? column.typeCounts) ?? {};
  return {
    name: asString(column.name),
    inferredType: asString(column.inferred_type ?? column.inferredType),
    nonNullCount: asNumber(column.non_null_count ?? column.nonNullCount),
    missingCount: asNumber(column.missing_count ?? column.missingCount),
    missingFraction: asNumber(column.missing_fraction ?? column.missingFraction),
    uniqueCount: asNumber(column.unique_count ?? column.uniqueCount),
    uniqueCountCapped: column.unique_count_capped === true || column.uniqueCountCapped === true,
    typeCounts: Object.fromEntries(
      Object.entries(typeCountsRaw).map(([key, value]) => [key, asNumber(value)]),
    ),
    topValues: topValues
      .map((item) => asRecord(item))
      .filter((item): item is Record<string, unknown> => item !== null)
      .map((item) => ({ value: asString(item.value), count: asNumber(item.count) })),
    numeric: numeric
      ? {
          count: asNumber(numeric.count),
          min: asNullableNumber(numeric.min),
          max: asNullableNumber(numeric.max),
          mean: asNullableNumber(numeric.mean),
          standardDeviation: asNullableNumber(numeric.standard_deviation ?? numeric.standardDeviation),
        }
      : undefined,
  };
}

function normalizeDatasetProfile(payload: unknown): GmScienceDatasetProfile | undefined {
  const profile = asRecord(payload);
  if (!profile) {
    return undefined;
  }
  const columns = Array.isArray(profile.columns) ? profile.columns : [];
  const preview = Array.isArray(profile.preview) ? profile.preview : [];
  return {
    version: asNumber(profile.version, 1),
    format: asString(profile.format),
    rowCount: asNumber(profile.row_count ?? profile.rowCount),
    profiledRowCount: asNumber(profile.profiled_row_count ?? profile.profiledRowCount),
    columnCount: asNumber(profile.column_count ?? profile.columnCount),
    columns: columns
      .map(normalizeDatasetColumn)
      .filter((item): item is GmScienceDatasetColumnProfile => item !== null),
    preview: preview.map(asLooseRecord),
    warnings: asStringList(profile.warnings),
  };
}

export function normalizeGmScienceDataset(payload: unknown): GmScienceDataset | null {
  const dataset = asRecord(payload);
  if (!dataset) {
    return null;
  }
  return {
    artifactId: asString(dataset.artifact_id ?? dataset.artifactId),
    projectId: asString(dataset.project_id ?? dataset.projectId),
    sessionId: asString(dataset.session_id ?? dataset.sessionId),
    title: asString(dataset.title),
    path: asString(dataset.path),
    mimeType: asString(dataset.mime_type ?? dataset.mimeType),
    format: asString(dataset.format),
    sourceName: asString(dataset.source_name ?? dataset.sourceName),
    sizeBytes: asNumber(dataset.size_bytes ?? dataset.sizeBytes),
    rowCount: asNumber(dataset.row_count ?? dataset.rowCount),
    profiledRowCount: asNumber(dataset.profiled_row_count ?? dataset.profiledRowCount),
    columnCount: asNumber(dataset.column_count ?? dataset.columnCount),
    columnNames: asStringList(dataset.column_names ?? dataset.columnNames),
    profileArtifactId: asString(dataset.profile_artifact_id ?? dataset.profileArtifactId),
    profile: normalizeDatasetProfile(dataset.profile),
    createdAt: asString(dataset.created_at ?? dataset.createdAt, new Date().toISOString()),
    updatedAt: asString(dataset.updated_at ?? dataset.updatedAt, new Date().toISOString()),
  };
}

export function normalizeGmScienceAnalysis(payload: unknown): GmScienceAnalysis | null {
  const analysis = asRecord(payload);
  const plan = asRecord(analysis?.plan);
  if (!analysis || !plan) {
    return null;
  }
  const status = asString(analysis.status, "draft");
  if (status !== "draft" && !GM_SCIENCE_RUN_STATUSES.has(status as GmScienceRunStatus)) {
    return null;
  }
  const steps = Array.isArray(plan.steps) ? plan.steps : [];
  const datasets = Array.isArray(plan.datasets) ? plan.datasets : [];
  const source = typeof analysis.source === "string" ? analysis.source : undefined;
  return {
    id: asString(analysis.id),
    projectId: asString(analysis.project_id ?? analysis.projectId),
    sessionId: asString(analysis.session_id ?? analysis.sessionId),
    title: asString(analysis.title),
    objective: asString(analysis.objective),
    datasetArtifactIds: asStringList(analysis.dataset_artifact_ids ?? analysis.datasetArtifactIds),
    plan: {
      version: asNumber(plan.version, 1),
      objective: asString(plan.objective),
      operations: asStringList(plan.operations),
      steps: steps
        .map(asRecord)
        .filter((item): item is Record<string, unknown> => item !== null)
        .map((item) => ({
          id: asString(item.id),
          title: asString(item.title),
          description: asString(item.description),
        })),
      datasets: datasets.map(asLooseRecord),
      assumptions: asStringList(plan.assumptions),
      warnings: asStringList(plan.warnings),
    },
    source,
    taskId: asString(analysis.task_id ?? analysis.taskId),
    status: status as GmScienceAnalysis["status"],
    run: normalizeGmScienceRun(analysis.run),
    reportArtifactId: asString(analysis.report_artifact_id ?? analysis.reportArtifactId),
    figureArtifactIds: asStringList(analysis.figure_artifact_ids ?? analysis.figureArtifactIds),
    artifactIds: asStringList(analysis.artifact_ids ?? analysis.artifactIds),
    createdAt: asString(analysis.created_at ?? analysis.createdAt, new Date().toISOString()),
    updatedAt: asString(analysis.updated_at ?? analysis.updatedAt, new Date().toISOString()),
  };
}
