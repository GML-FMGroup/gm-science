import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  BookOpen,
  Box,
  Brain,
  ChevronDown,
  Clock3,
  Cloud,
  Columns2,
  Cpu,
  Database,
  FileText,
  Folder,
  HardDrive,
  KeyRound,
  LayoutGrid,
  Library,
  Menu,
  MessageSquarePlus,
  Network,
  PanelLeftClose,
  PanelRightClose,
  Play,
  Plus,
  RefreshCw,
  Search,
  Send,
  Settings as SettingsIcon,
  ShieldCheck,
  SlidersHorizontal,
  UserRound,
  UsersRound,
  X,
  Zap,
} from "lucide-react";
import { CapabilitiesPanel } from "./components/CapabilitiesPanel";
import { ArtifactInspector } from "./components/ArtifactInspector";
import { DataPanel } from "./components/DataPanel";
import { MessageBubble } from "./components/MessageBubble";
import { MemorySettingsPanel } from "./components/MemorySettingsPanel";
import { SessionOptionsMenu } from "./components/SessionOptionsMenu";
import { CredentialsSettingsPanel, GeneralSettingsPanel } from "./components/SettingsPanels";
import type {
  AgentProfile,
  BootstrapPayload,
  ChatMessage,
  ClientDiagnostics,
  ConnectionSettings,
  GmScienceCapability,
  GmScienceCapabilityKind,
  GmScienceProject,
  GmScienceResource,
  GmScienceResourceDetail,
  GmScienceRun,
  GmScienceSessionPolicy,
  GmScienceSettings,
  RuntimeState,
  RuntimeStatus,
  SessionSummary,
  UpdateGmScienceSessionPolicyInput,
  UpdateGmScienceSettingsInput,
} from "./types";

type NavView = "projects" | "workspace";
type SettingsSection =
  | GmScienceCapabilityKind
  | "memory"
  | "compute"
  | "network"
  | "permissions"
  | "credentials"
  | "storage"
  | "usage"
  | "general";
type WorkspacePanel = "files" | "data" | "runs";

const SETTINGS_SECTION_TITLES: Record<SettingsSection, string> = {
  skill: "Skills",
  connector: "Connectors",
  specialist: "Specialists",
  memory: "Memory",
  compute: "Compute",
  network: "Network",
  permissions: "Permissions",
  credentials: "Credentials",
  storage: "Storage",
  usage: "Usage",
  general: "General",
};

interface ProjectFormState {
  name: string;
  description: string;
  agentContext: string;
}

interface PythonRunFormState {
  title: string;
  source: string;
  inputJson: string;
}

const EMPTY_PROJECT_FORM: ProjectFormState = {
  name: "",
  description: "",
  agentContext: "",
};

const DEFAULT_PYTHON_SOURCE = `import json
import os
from pathlib import Path

input_path = Path(os.environ["GM_SCIENCE_INPUT_PATH"])
output_dir = Path(os.environ["GM_SCIENCE_OUTPUT_DIR"])
payload = json.loads(input_path.read_text(encoding="utf-8"))

print("Run started", payload)
(output_dir / "result.txt").write_text(
    "gm-science local Python run completed.\\n",
    encoding="utf-8",
)
print("Run completed")
`;

const DEFAULT_PYTHON_RUN_FORM: PythonRunFormState = {
  title: "Python experiment",
  source: DEFAULT_PYTHON_SOURCE,
  inputJson: "{}",
};

const ACTIVE_RUN_STATUSES = new Set<GmScienceRun["status"]>([
  "queued",
  "running",
  "paused",
  "waiting_user",
  "waiting_approval",
  "interrupted",
  "stale",
]);

function mergeMessages(current: ChatMessage[], incoming: ChatMessage): ChatMessage[] {
  return current.some((item) => item.id === incoming.id) ? current : [...current, incoming];
}

function updateMessage(
  current: ChatMessage[],
  messageId: string,
  updater: (message: ChatMessage) => ChatMessage,
): ChatMessage[] {
  return current.map((message) => (message.id === messageId ? updater(message) : message));
}

function removeSendingSession(current: string[], sessionId: string): string[] {
  return current.filter((item) => item !== sessionId);
}

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

function mergeSessionSummary(existing: SessionSummary | undefined, incoming: SessionSummary): SessionSummary {
  if (!existing) {
    return incoming;
  }
  const merged = { ...incoming, projectId: incoming.projectId || existing.projectId };
  if (isGenericSessionTitle(incoming.title) && !isGenericSessionTitle(existing.title)) {
    return { ...merged, title: existing.title };
  }
  return merged;
}

function runtimeActionLabel(state: RuntimeState): string {
  if (state === "stopped") {
    return "启动";
  }
  if (state === "healthy") {
    return "重启";
  }
  return "重试";
}

function buildConnectionSettings(diagnostics: ClientDiagnostics | null): ConnectionSettings {
  return {
    targetType: diagnostics?.target.type ?? "local",
    targetId: diagnostics?.target.id ?? "local-default",
    targetName: diagnostics?.target.name ?? "This Mac",
    clientApiBaseUrl: diagnostics?.clientApiBaseUrl ?? "http://127.0.0.1:8876",
  };
}

function normalizeConnectionSettings(settings: ConnectionSettings): ConnectionSettings {
  const targetType = settings.targetType;
  const targetName = settings.targetName.trim() || (targetType === "remote" ? "Remote Gateway" : "This Mac");
  const normalizedName =
    targetName
      .toLowerCase()
      .replace(/[^a-z0-9_-]+/g, "-")
      .replace(/^-+|-+$/g, "") || "default";
  const existingId = settings.targetId.trim();
  const targetId =
    !existingId ||
    existingId === "local-default" ||
    existingId === "remote-default" ||
    !existingId.startsWith(`${targetType}-`)
      ? `${targetType}-${normalizedName}`
      : existingId;
  return {
    targetType,
    targetId,
    targetName,
    clientApiBaseUrl: settings.clientApiBaseUrl.trim() || "http://127.0.0.1:8876",
  };
}

function resizeComposer(textarea: HTMLTextAreaElement | null): void {
  if (!textarea) {
    return;
  }
  const computedStyle = window.getComputedStyle(textarea);
  const lineHeight = Number.parseFloat(computedStyle.lineHeight) || 24;
  const minHeight = lineHeight * 2;
  const maxHeight = lineHeight * 10;
  textarea.style.height = "auto";
  const nextHeight = Math.min(Math.max(textarea.scrollHeight, minHeight), maxHeight);
  textarea.style.height = `${nextHeight}px`;
  textarea.style.overflowY = textarea.scrollHeight > maxHeight ? "auto" : "hidden";
}

function formatResourceKind(kind: GmScienceResource["kind"]): string {
  return kind.replaceAll("_", " ");
}

function formatFileSize(value: number | null): string {
  if (value === null) {
    return "";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${Math.round(value / 1024)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function resourceSearchText(resource: GmScienceResource): string {
  return [
    resource.displayName,
    formatResourceKind(resource.kind),
    resource.artifactType,
    resource.mimeType,
    resource.relativePath,
  ]
    .join(" ")
    .toLowerCase();
}

function isActiveRun(run: GmScienceRun): boolean {
  return ACTIVE_RUN_STATUSES.has(run.status);
}

function formatRunStatus(status: GmScienceRun["status"]): string {
  return status.replaceAll("_", " ");
}

function formatRunTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function formatRelativeTime(value: string): string {
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) {
    return "";
  }
  const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
  if (seconds < 60) {
    return "now";
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h`;
  }
  const days = Math.floor(hours / 24);
  if (days < 7) {
    return `${days}d`;
  }
  return `${Math.floor(days / 7)}w`;
}

function isCapabilitySection(section: SettingsSection): section is GmScienceCapabilityKind {
  return section === "skill" || section === "connector" || section === "specialist";
}

function ResourceItem({
  resource,
  selected,
  onOpen,
  onToggle,
}: {
  resource: GmScienceResource;
  selected: boolean;
  onOpen: (resource: GmScienceResource) => void;
  onToggle: (resource: GmScienceResource) => void;
}) {
  const marker =
    resource.kind === "dataset" ? "D" : resource.kind === "run_output" ? "O" : resource.kind === "project_file" ? "F" : "A";
  const details = [
    resource.artifactType !== resource.kind ? resource.artifactType.replaceAll("_", " ") : "",
    resource.mimeType,
    formatFileSize(resource.sizeBytes),
    formatRunTime(resource.updatedAt),
  ]
    .filter(Boolean)
    .join(" · ");
  const location = resource.relativePath || resource.url;

  return (
    <article className={`resource-item resource-${resource.kind}${selected ? " selected" : ""}`}>
      <div className="resource-title-row">
        <button className="resource-open" aria-label={`Open ${resource.displayName}`} onClick={() => onOpen(resource)}>
          <span className="resource-marker" aria-hidden="true">
            {marker}
          </span>
          <span>
            <strong>{resource.displayName}</strong>
            <span className="resource-kind">{formatResourceKind(resource.kind)}</span>
          </span>
        </button>
        <input
          type="checkbox"
          checked={selected}
          aria-label={`Select ${resource.displayName}`}
          onChange={() => onToggle(resource)}
        />
      </div>
      {location ? <p className="resource-location">{location}</p> : null}
      {details ? <p className="resource-detail">{details}</p> : null}
    </article>
  );
}

function RunItem({
  run,
  actionPending,
  onCancel,
  onRetry,
}: {
  run: GmScienceRun;
  actionPending: boolean;
  onCancel: (run: GmScienceRun) => void;
  onRetry: (run: GmScienceRun) => void;
}) {
  const summary = run.lastError || run.terminalSummary || run.progressSummary;
  return (
    <article className="science-run-item">
      <div className="science-run-title-row">
        <div>
          <strong>{run.title}</strong>
          <time>{formatRunTime(run.createdAt)}</time>
        </div>
        <span className={`science-run-status ${run.status}`}>{formatRunStatus(run.status)}</span>
      </div>
      {summary ? <p className={run.lastError ? "science-run-summary error" : "science-run-summary"}>{summary}</p> : null}
      {run.logPreview ? (
        <details className="science-run-log">
          <summary>Log output</summary>
          <pre>{run.logPreview}</pre>
        </details>
      ) : null}
      {run.artifactIds.length ? <small>{run.artifactIds.length} artifacts</small> : null}
      {run.canCancel || run.canRetry ? (
        <div className="science-run-actions">
          {run.canCancel ? (
            <button className="secondary small" disabled={actionPending} onClick={() => onCancel(run)}>
              Cancel
            </button>
          ) : null}
          {run.canRetry ? (
            <button className="secondary small" disabled={actionPending} onClick={() => onRetry(run)}>
              Retry
            </button>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

export function App() {
  const [view, setView] = useState<NavView>("projects");
  const [ready, setReady] = useState(false);
  const [bootstrapError, setBootstrapError] = useState<string | null>(null);
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null);
  const [diagnostics, setDiagnostics] = useState<ClientDiagnostics | null>(null);
  const [agents, setAgents] = useState<AgentProfile[]>([]);
  const [projects, setProjects] = useState<GmScienceProject[]>([]);
  const [resources, setResources] = useState<GmScienceResource[]>([]);
  const [selectedResources, setSelectedResources] = useState<GmScienceResource[]>([]);
  const [openResourceIds, setOpenResourceIds] = useState<string[]>([]);
  const [activeResourceId, setActiveResourceId] = useState("");
  const [resourceDetails, setResourceDetails] = useState<Record<string, GmScienceResourceDetail>>({});
  const [resourceDetailLoading, setResourceDetailLoading] = useState(false);
  const [resourceDetailError, setResourceDetailError] = useState<string | null>(null);
  const [resourceActionError, setResourceActionError] = useState<string | null>(null);
  const [provenanceOpen, setProvenanceOpen] = useState(false);
  const [runs, setRuns] = useState<GmScienceRun[]>([]);
  const [resourceSearch, setResourceSearch] = useState("");
  const [workspacePanel, setWorkspacePanel] = useState<WorkspacePanel>("files");
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [composer, setComposer] = useState("");
  const [sendError, setSendError] = useState<string | null>(null);
  const [projectError, setProjectError] = useState<string | null>(null);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [settingsSection, setSettingsSection] = useState<SettingsSection>("skill");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [filesOpen, setFilesOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [capabilities, setCapabilities] = useState<GmScienceCapability[]>([]);
  const [capabilitiesLoading, setCapabilitiesLoading] = useState(false);
  const [capabilitiesSaving, setCapabilitiesSaving] = useState(false);
  const [capabilitiesError, setCapabilitiesError] = useState<string | null>(null);
  const [scienceSettings, setScienceSettings] = useState<GmScienceSettings | null>(null);
  const [scienceSettingsLoading, setScienceSettingsLoading] = useState(false);
  const [scienceSettingsSaving, setScienceSettingsSaving] = useState(false);
  const [sessionPolicy, setSessionPolicy] = useState<GmScienceSessionPolicy | null>(null);
  const [sessionPolicyLoading, setSessionPolicyLoading] = useState(false);
  const [sessionPolicySaving, setSessionPolicySaving] = useState(false);
  const [sessionPolicyError, setSessionPolicyError] = useState<string | null>(null);
  const [sessionOptionsOpen, setSessionOptionsOpen] = useState(false);
  const [sendingSessionIds, setSendingSessionIds] = useState<string[]>([]);
  const [connectionForm, setConnectionForm] = useState<ConnectionSettings>(buildConnectionSettings(null));
  const [savingConnection, setSavingConnection] = useState(false);
  const [projectModalOpen, setProjectModalOpen] = useState(false);
  const [projectForm, setProjectForm] = useState<ProjectFormState>(EMPTY_PROJECT_FORM);
  const [creatingProject, setCreatingProject] = useState(false);
  const [pythonRunModalOpen, setPythonRunModalOpen] = useState(false);
  const [pythonRunForm, setPythonRunForm] = useState<PythonRunFormState>(DEFAULT_PYTHON_RUN_FORM);
  const [runError, setRunError] = useState<string | null>(null);
  const [submittingRun, setSubmittingRun] = useState(false);
  const [runActionTaskId, setRunActionTaskId] = useState("");
  const switchRequestIdRef = useRef(0);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const messageStreamRef = useRef<HTMLElement | null>(null);
  const nextScrollBehaviorRef = useRef<ScrollBehavior>("auto");
  const selectedProjectIdRef = useRef("");
  const runsRef = useRef<GmScienceRun[]>([]);
  const capabilitySaveInFlightRef = useRef(false);
  const sessionPolicyRequestIdRef = useRef(0);
  const resourceDetailRequestIdRef = useRef(0);
  const sessionOptionsRef = useRef<HTMLDivElement | null>(null);

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId) ?? null,
    [projects, selectedProjectId],
  );
  const selectedAgent = useMemo(
    () => agents.find((agent) => agent.id === selectedAgentId) ?? agents[0] ?? null,
    [agents, selectedAgentId],
  );
  const projectSessions = useMemo(
    () => sessions.filter((session) => session.projectId === selectedProjectId),
    [sessions, selectedProjectId],
  );
  const recentSessions = useMemo(
    () => sessions.filter((session) => session.projectId && projects.some((project) => project.id === session.projectId)),
    [projects, sessions],
  );
  const selectedSession = useMemo(
    () => projectSessions.find((session) => session.id === selectedSessionId) ?? null,
    [projectSessions, selectedSessionId],
  );
  const selectedAgentBusy = useMemo(
    () =>
      Boolean(selectedAgentId) &&
      ((selectedSessionId && sendingSessionIds.includes(selectedSessionId)) ||
        projectSessions.some((session) => session.agentId === selectedAgentId && sendingSessionIds.includes(session.id))),
    [projectSessions, selectedAgentId, selectedSessionId, sendingSessionIds],
  );
  const visibleResources = useMemo(() => {
    const query = resourceSearch.trim().toLowerCase();
    return query ? resources.filter((resource) => resourceSearchText(resource).includes(query)) : resources;
  }, [resourceSearch, resources]);
  const selectedResourceIds = useMemo(
    () => new Set(selectedResources.map((resource) => resource.id)),
    [selectedResources],
  );
  const openResources = useMemo(
    () => openResourceIds
      .map((resourceId) => resources.find((resource) => resource.id === resourceId))
      .filter((resource): resource is GmScienceResource => Boolean(resource)),
    [openResourceIds, resources],
  );
  const activeResource = useMemo(
    () => resources.find((resource) => resource.id === activeResourceId) ?? null,
    [activeResourceId, resources],
  );
  const activeResourceDetail = activeResourceId ? resourceDetails[activeResourceId] ?? null : null;
  const canSend = Boolean(composer.trim()) && Boolean(selectedAgentId) && Boolean(selectedProjectId) && !selectedAgentBusy;
  const sessionPolicyActive = Boolean(
    sessionPolicy?.delegationEnabled
      || sessionPolicy?.autoReviewEnabled
      || sessionPolicy?.memoryEnabled
      || sessionPolicy?.specialistId,
  );

  useEffect(() => {
    if (!window.ppxClient) {
      setBootstrapError("Preload host API was not injected. Check Electron preload output and restart dev.");
      return;
    }

    let mounted = true;
    const off = window.ppxClient.onRunEvent((event) => {
      if (event.type === "message.created") {
        setMessages((current) => mergeMessages(current, event.message));
        return;
      }
      if (event.type === "message.updated") {
        setMessages((current) =>
          updateMessage(current, event.messageId, (message) => ({
            ...message,
            status: event.status ?? message.status,
            parts: event.replaceParts ?? [...message.parts, ...(event.appendParts ?? [])],
          })),
        );
        if (event.status === "completed" || event.status === "failed" || event.status === "cancelled") {
          setSendingSessionIds((current) => removeSendingSession(current, event.sessionId));
        }
        if (event.status === "failed") {
          void refreshResources(selectedProjectIdRef.current);
        }
        return;
      }
      if (event.type === "session.updated") {
        setSessions((current) =>
          [
            mergeSessionSummary(
              current.find((item) => item.id === event.session.id),
              event.session,
            ),
            ...current.filter((item) => item.id !== event.session.id),
          ].sort((left, right) => right.updatedAt.localeCompare(left.updatedAt)),
        );
        return;
      }
      if (event.type === "run.finished") {
        setSendingSessionIds((current) => removeSendingSession(current, event.sessionId));
        void refreshResources(selectedProjectIdRef.current);
      }
    });

    window.ppxClient
      .bootstrap()
      .then(async (payload: BootstrapPayload) => {
        if (!mounted) {
          return;
        }
        const projectPayload = await window.ppxClient.listGmScienceProjects().catch(() => ({ projects: [] }));
        const nextDiagnostics = await window.ppxClient.getDiagnostics().catch(() => null);
        if (!mounted) {
          return;
        }
        setRuntime(payload.runtime);
        setAgents(payload.agents);
        setSessions(payload.sessions);
        nextScrollBehaviorRef.current = "auto";
        setMessages([]);
        setSelectedAgentId(payload.selectedAgentId || payload.agents[0]?.id || "");
        setSelectedSessionId("");
        setProjects(projectPayload.projects);
        setDiagnostics(nextDiagnostics);
        setConnectionForm(buildConnectionSettings(nextDiagnostics));
        setReady(true);
        setBootstrapError(null);
      })
      .catch((error: unknown) => {
        if (!mounted) {
          return;
        }
        setBootstrapError(error instanceof Error ? error.message : String(error));
      });

    return () => {
      mounted = false;
      off();
    };
  }, []);

  useEffect(() => {
    resizeComposer(composerRef.current);
  }, [composer]);

  useEffect(() => {
    setSessionOptionsOpen(false);
    setSessionPolicySaving(false);
    if (!selectedSessionId) {
      sessionPolicyRequestIdRef.current += 1;
      setSessionPolicy(null);
      setSessionPolicyError(null);
      setSessionPolicyLoading(false);
      return;
    }
    void refreshSessionPolicy(selectedSessionId);
  }, [selectedSessionId]);

  useEffect(() => {
    if (!sessionOptionsOpen) {
      return;
    }
    const handlePointerDown = (event: PointerEvent) => {
      if (!sessionOptionsRef.current?.contains(event.target as Node)) {
        setSessionOptionsOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSessionOptionsOpen(false);
      }
    };
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [sessionOptionsOpen]);

  useEffect(() => {
    if (!settingsOpen) {
      return;
    }
    void Promise.all([refreshCapabilities(), refreshScienceSettings()]);
  }, [settingsOpen, selectedProjectId]);

  useEffect(() => {
    runsRef.current = runs;
  }, [runs]);

  useEffect(() => {
    if (view !== "workspace" || !selectedProjectId || !runs.some(isActiveRun)) {
      return;
    }
    const timer = window.setInterval(() => {
      void refreshRuns(selectedProjectId);
    }, 1200);
    return () => window.clearInterval(timer);
  }, [runs, selectedProjectId, view]);

  useEffect(() => {
    const stream = messageStreamRef.current;
    if (!stream) {
      return;
    }
    const behavior = nextScrollBehaviorRef.current;
    nextScrollBehaviorRef.current = "smooth";
    if (typeof stream.scrollTo === "function") {
      stream.scrollTo({ top: stream.scrollHeight, behavior });
      return;
    }
    stream.scrollTop = stream.scrollHeight;
  }, [messages]);

  async function refreshProjects(): Promise<void> {
    const listed = await window.ppxClient.listGmScienceProjects();
    setProjects(listed.projects);
  }

  async function refreshCapabilities(): Promise<void> {
    setCapabilitiesLoading(true);
    setCapabilitiesError(null);
    try {
      const catalog = await window.ppxClient.listGmScienceCapabilities(selectedProjectId || undefined);
      setCapabilities(catalog.items);
    } catch (error) {
      setCapabilitiesError(error instanceof Error ? error.message : String(error));
    } finally {
      setCapabilitiesLoading(false);
    }
  }

  async function refreshScienceSettings(): Promise<void> {
    setScienceSettingsLoading(true);
    setSettingsError(null);
    try {
      setScienceSettings(await window.ppxClient.getGmScienceSettings());
    } catch (error) {
      setSettingsError(error instanceof Error ? error.message : String(error));
    } finally {
      setScienceSettingsLoading(false);
    }
  }

  async function refreshSessionPolicy(sessionId: string): Promise<void> {
    const requestId = ++sessionPolicyRequestIdRef.current;
    setSessionPolicyLoading(true);
    setSessionPolicyError(null);
    try {
      const policy = await window.ppxClient.getGmScienceSessionPolicy(sessionId);
      if (requestId === sessionPolicyRequestIdRef.current) {
        setSessionPolicy(policy);
      }
    } catch (error) {
      if (requestId === sessionPolicyRequestIdRef.current) {
        setSessionPolicy(null);
        setSessionPolicyError(error instanceof Error ? error.message : String(error));
      }
    } finally {
      if (requestId === sessionPolicyRequestIdRef.current) {
        setSessionPolicyLoading(false);
      }
    }
  }

  async function updateSessionPolicy(input: UpdateGmScienceSessionPolicyInput): Promise<void> {
    if (!selectedSessionId || sessionPolicySaving) {
      return;
    }
    const sessionId = selectedSessionId;
    const requestId = ++sessionPolicyRequestIdRef.current;
    setSessionPolicySaving(true);
    setSessionPolicyError(null);
    try {
      const policy = await window.ppxClient.updateGmScienceSessionPolicy(sessionId, input);
      if (requestId === sessionPolicyRequestIdRef.current) {
        setSessionPolicy(policy);
      }
    } catch (error) {
      if (requestId === sessionPolicyRequestIdRef.current) {
        setSessionPolicyError(error instanceof Error ? error.message : String(error));
      }
    } finally {
      if (requestId === sessionPolicyRequestIdRef.current) {
        setSessionPolicySaving(false);
      }
    }
  }

  async function updateScienceSettings(input: UpdateGmScienceSettingsInput): Promise<void> {
    setScienceSettingsSaving(true);
    setSettingsError(null);
    try {
      const updated = await window.ppxClient.updateGmScienceSettings({
        ...input,
        projectId: selectedProjectId || undefined,
      });
      setScienceSettings(updated.settings);
      setAgents((current) => {
        const found = current.some((agent) => agent.id === updated.agent.id);
        return found
          ? current.map((agent) => agent.id === updated.agent.id ? updated.agent : agent)
          : [updated.agent, ...current];
      });
      if (updated.capabilities.length > 0) {
        setCapabilities(updated.capabilities);
      }
    } catch (error) {
      setSettingsError(error instanceof Error ? error.message : String(error));
      throw error;
    } finally {
      setScienceSettingsSaving(false);
    }
  }

  function openSettings(section: SettingsSection): void {
    setSettingsSection(section);
    setSettingsOpen(true);
  }

  async function toggleCapability(capabilityId: string): Promise<void> {
    if (!selectedProjectId || capabilitySaveInFlightRef.current) {
      return;
    }
    const previous = capabilities;
    const target = previous.find((item) => item.id === capabilityId);
    if (!target) {
      return;
    }
    const checked = target.projectEnabled ?? target.defaultEnabled;
    if (!target.available && !checked) {
      return;
    }
    const next = previous.map((item) =>
      item.id === capabilityId ? { ...item, projectEnabled: !checked } : item,
    );
    const projectId = selectedProjectId;
    capabilitySaveInFlightRef.current = true;
    setCapabilities(next);
    setCapabilitiesSaving(true);
    setCapabilitiesError(null);
    try {
      const response = await window.ppxClient.updateGmScienceProjectCapabilities(projectId, {
        enabledSkills: next.filter((item) => item.kind === "skill" && item.projectEnabled).map((item) => item.id),
        enabledConnectors: next
          .filter((item) => item.kind === "connector" && item.projectEnabled)
          .map((item) => item.id),
        enabledSpecialists: next
          .filter((item) => item.kind === "specialist" && item.projectEnabled)
          .map((item) => item.id),
      });
      setProjects((current) =>
        current.map((project) => (project.id === response.project.id ? response.project : project)),
      );
      if (selectedProjectIdRef.current === projectId) {
        setCapabilities(response.capabilities);
      }
    } catch (error) {
      if (selectedProjectIdRef.current === projectId) {
        setCapabilities(previous);
        setCapabilitiesError(error instanceof Error ? error.message : String(error));
      }
    } finally {
      capabilitySaveInFlightRef.current = false;
      setCapabilitiesSaving(false);
    }
  }

  async function refreshResources(projectId: string, clearOnError = false): Promise<void> {
    if (!projectId) {
      return;
    }
    try {
      const payload = await window.ppxClient.listGmScienceResources(projectId);
      if (selectedProjectIdRef.current === projectId) {
        setResources(payload.resources);
      }
    } catch {
      if (clearOnError && selectedProjectIdRef.current === projectId) {
        setResources([]);
      }
    }
  }

  async function openResource(resource: GmScienceResource, forceRefresh = false): Promise<void> {
    if (!selectedProjectId) {
      return;
    }
    const projectId = selectedProjectId;
    const requestId = ++resourceDetailRequestIdRef.current;
    setFilesOpen(true);
    setWorkspacePanel("files");
    setOpenResourceIds((current) => current.includes(resource.id) ? current : [...current, resource.id]);
    setActiveResourceId(resource.id);
    setResourceDetailError(null);
    setResourceActionError(null);
    setProvenanceOpen(false);
    const cached = resourceDetails[resource.id];
    if (!forceRefresh && cached?.resource.versionOrHash === resource.versionOrHash) {
      setResourceDetailLoading(false);
      return;
    }
    setResourceDetailLoading(true);
    try {
      const payload = await window.ppxClient.getGmScienceResourceDetail(projectId, resource.id);
      if (requestId !== resourceDetailRequestIdRef.current || selectedProjectIdRef.current !== projectId) {
        return;
      }
      setResourceDetails((current) => ({ ...current, [resource.id]: payload.detail }));
    } catch (error) {
      if (requestId === resourceDetailRequestIdRef.current && selectedProjectIdRef.current === projectId) {
        setResourceDetailError(error instanceof Error ? error.message : String(error));
      }
    } finally {
      if (requestId === resourceDetailRequestIdRef.current && selectedProjectIdRef.current === projectId) {
        setResourceDetailLoading(false);
      }
    }
  }

  function closeResourceTab(resourceId: string): void {
    const index = openResourceIds.indexOf(resourceId);
    const remaining = openResourceIds.filter((id) => id !== resourceId);
    setOpenResourceIds(remaining);
    if (activeResourceId !== resourceId) {
      return;
    }
    resourceDetailRequestIdRef.current += 1;
    const nextId = remaining[Math.min(Math.max(index, 0), remaining.length - 1)] ?? "";
    setActiveResourceId(nextId);
    setResourceDetailError(null);
    setResourceActionError(null);
    setProvenanceOpen(false);
    if (nextId) {
      const nextResource = resources.find((resource) => resource.id === nextId);
      if (nextResource && !resourceDetails[nextId]) {
        void openResource(nextResource);
      }
    }
  }

  function showArtifactCatalog(): void {
    resourceDetailRequestIdRef.current += 1;
    setActiveResourceId("");
    setResourceDetailLoading(false);
    setResourceDetailError(null);
    setResourceActionError(null);
    setProvenanceOpen(false);
  }

  async function viewActiveResourceInContext(): Promise<void> {
    if (!activeResourceDetail) {
      return;
    }
    const sessionId = activeResourceDetail.artifact?.sessionId || activeResourceDetail.resource.sessionId;
    if (!sessionId) {
      setResourceActionError("This Artifact is not attached to a source Session.");
      return;
    }
    const sourceSession = projectSessions.find((session) => session.id === sessionId);
    if (!sourceSession) {
      setResourceActionError("The source Session is no longer attached to this Project.");
      return;
    }
    setResourceActionError(null);
    setProvenanceOpen(false);
    await switchSession(sourceSession);
  }

  function openRelatedResource(resourceId: string): void {
    const related = resources.find((resource) => resource.id === resourceId);
    if (!related) {
      setResourceActionError("The related Artifact is no longer available in this Project.");
      return;
    }
    void openResource(related);
  }

  async function refreshRuns(projectId: string, clearOnError = false): Promise<void> {
    if (!projectId) {
      return;
    }
    try {
      const payload = await window.ppxClient.listGmScienceRuns(projectId);
      if (selectedProjectIdRef.current !== projectId) {
        return;
      }
      const previous = new Map(runsRef.current.map((run) => [run.taskId, run]));
      const becameTerminal = payload.runs.some((run) => {
        const prior = previous.get(run.taskId);
        return Boolean(prior && isActiveRun(prior) && !isActiveRun(run));
      });
      runsRef.current = payload.runs;
      setRuns(payload.runs);
      if (becameTerminal) {
        await Promise.all([refreshResources(projectId), refreshProjects()]);
      }
    } catch (error) {
      if (clearOnError && selectedProjectIdRef.current === projectId) {
        runsRef.current = [];
        setRuns([]);
      }
      if (workspacePanel === "runs" && selectedProjectIdRef.current === projectId) {
        setRunError(error instanceof Error ? error.message : String(error));
      }
    }
  }

  async function openProject(project: GmScienceProject): Promise<void> {
    const requestId = ++switchRequestIdRef.current;
    setProjectError(null);
    selectedProjectIdRef.current = project.id;
    setSelectedProjectId(project.id);
    setResourceSearch("");
    setSelectedResources([]);
    resourceDetailRequestIdRef.current += 1;
    setOpenResourceIds([]);
    setActiveResourceId("");
    setResourceDetails({});
    setResourceDetailLoading(false);
    setResourceDetailError(null);
    setResourceActionError(null);
    setProvenanceOpen(false);
    setRunError(null);
    runsRef.current = [];
    setRuns([]);
    setSelectedSessionId("");
    setMessages([]);
    setFilesOpen(false);
    setView("workspace");
    const agentId = selectedAgentId || agents[0]?.id || "";
    let nextSessions = sessions;
    if (agentId) {
      try {
        nextSessions = (await window.ppxClient.listSessions(agentId)).sessions;
        setSessions(nextSessions);
      } catch (error) {
        setProjectError(error instanceof Error ? error.message : String(error));
      }
    }
    const firstSession = nextSessions.find((session) => session.projectId === project.id);
    if (firstSession && requestId === switchRequestIdRef.current) {
      setSelectedAgentId(firstSession.agentId);
      setSelectedSessionId(firstSession.id);
      const loaded = await window.ppxClient.loadSession(firstSession.id);
      if (requestId === switchRequestIdRef.current) {
        nextScrollBehaviorRef.current = "auto";
        setMessages(loaded.messages);
      }
    }
    await Promise.all([refreshResources(project.id, true), refreshRuns(project.id, true)]);
  }

  function openPythonRunDialog(): void {
    setPythonRunForm(DEFAULT_PYTHON_RUN_FORM);
    setRunError(null);
    setPythonRunModalOpen(true);
  }

  async function createPythonRun(): Promise<void> {
    const title = pythonRunForm.title.trim();
    const source = pythonRunForm.source;
    if (!selectedProjectId || !title || !source.trim()) {
      setRunError("Run title and Python source are required.");
      return;
    }
    let input: Record<string, unknown>;
    try {
      const parsed: unknown = JSON.parse(pythonRunForm.inputJson || "{}");
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("Input must be a JSON object.");
      }
      input = parsed as Record<string, unknown>;
    } catch (error) {
      setRunError(error instanceof Error ? error.message : String(error));
      return;
    }
    setSubmittingRun(true);
    setRunError(null);
    try {
      const created = await window.ppxClient.createGmSciencePythonRun(selectedProjectId, {
        title,
        source,
        sessionId: selectedSessionId || undefined,
        input,
      });
      runsRef.current = [created.run, ...runsRef.current.filter((run) => run.taskId !== created.run.taskId)];
      setRuns(runsRef.current);
      setWorkspacePanel("runs");
      setPythonRunModalOpen(false);
      if (!isActiveRun(created.run)) {
        await Promise.all([refreshResources(selectedProjectId), refreshProjects()]);
      }
    } catch (error) {
      setRunError(error instanceof Error ? error.message : String(error));
    } finally {
      setSubmittingRun(false);
    }
  }

  async function cancelPythonRun(run: GmScienceRun): Promise<void> {
    setRunActionTaskId(run.taskId);
    setRunError(null);
    try {
      const cancelled = await window.ppxClient.cancelGmScienceRun(run.projectId, run.taskId);
      runsRef.current = runsRef.current.map((item) =>
        item.taskId === cancelled.run.taskId ? cancelled.run : item,
      );
      setRuns(runsRef.current);
      await Promise.all([refreshResources(run.projectId), refreshProjects()]);
    } catch (error) {
      setRunError(error instanceof Error ? error.message : String(error));
    } finally {
      setRunActionTaskId("");
    }
  }

  async function retryPythonRun(run: GmScienceRun): Promise<void> {
    setRunActionTaskId(run.taskId);
    setRunError(null);
    try {
      const retried = await window.ppxClient.retryGmScienceRun(run.projectId, run.taskId);
      runsRef.current = [retried.run, ...runsRef.current.filter((item) => item.taskId !== retried.run.taskId)];
      setRuns(runsRef.current);
      if (!isActiveRun(retried.run)) {
        await Promise.all([refreshResources(run.projectId), refreshProjects()]);
      }
    } catch (error) {
      setRunError(error instanceof Error ? error.message : String(error));
    } finally {
      setRunActionTaskId("");
    }
  }

  async function createProject(): Promise<void> {
    const name = projectForm.name.trim();
    if (!name) {
      setProjectError("Project name is required.");
      return;
    }
    setCreatingProject(true);
    setProjectError(null);
    try {
      const created = await window.ppxClient.createGmScienceProject({
        name,
        description: projectForm.description,
        agentContext: projectForm.agentContext,
      });
      setProjects((current) => [created.project, ...current.filter((project) => project.id !== created.project.id)]);
      setProjectForm(EMPTY_PROJECT_FORM);
      setProjectModalOpen(false);
      await openProject(created.project);
    } catch (error) {
      setProjectError(error instanceof Error ? error.message : String(error));
    } finally {
      setCreatingProject(false);
    }
  }

  async function switchSession(session: SessionSummary): Promise<void> {
    const requestId = ++switchRequestIdRef.current;
    setSendError(null);
    setSelectedAgentId(session.agentId);
    setSelectedSessionId(session.id);
    setMessages([]);
    const loaded = await window.ppxClient.loadSession(session.id);
    if (requestId !== switchRequestIdRef.current) {
      return;
    }
    nextScrollBehaviorRef.current = "auto";
    setMessages(loaded.messages);
  }

  async function handleNewSession(): Promise<void> {
    const agentId = selectedAgentId || selectedAgent?.id;
    if (!agentId || !selectedProjectId) {
      return;
    }
    setSendError(null);
    const created = await window.ppxClient.createSession(agentId, selectedProjectId);
    setSessions((current) => [created.session, ...current.filter((item) => item.id !== created.session.id)]);
    setSelectedAgentId(agentId);
    setSelectedSessionId(created.session.id);
    setMessages([]);
    void refreshProjects();
  }

  async function ensureActiveSession(
    agentId: string,
    projectId: string,
    preferredSessionId: string,
  ): Promise<SessionSummary> {
    const existing = sessions.find(
      (session) =>
        session.id === preferredSessionId && session.agentId === agentId && session.projectId === projectId,
    );
    if (existing) {
      return existing;
    }
    const listed = await window.ppxClient.listSessions(agentId);
    const firstSession = listed.sessions.find((session) => session.projectId === projectId);
    if (firstSession) {
      setSessions(listed.sessions);
      setSelectedSessionId(firstSession.id);
      if (firstSession.id !== preferredSessionId) {
        const loaded = await window.ppxClient.loadSession(firstSession.id);
        nextScrollBehaviorRef.current = "auto";
        setMessages(loaded.messages);
      }
      return firstSession;
    }
    const created = await window.ppxClient.createSession(agentId, projectId);
    setSessions((current) => [created.session, ...current.filter((item) => item.id !== created.session.id)]);
    setSelectedSessionId(created.session.id);
    setMessages([]);
    void refreshProjects();
    return created.session;
  }

  function applyFirstUserTitle(sessionId: string, text: string, timestamp: string): void {
    const title = compactSessionTitle(text);
    if (!title) {
      return;
    }
    setSessions((current) =>
      current.map((session) =>
        session.id === sessionId && isGenericSessionTitle(session.title)
          ? { ...session, title, updatedAt: timestamp }
          : session,
      ),
    );
  }

  async function handleSend(): Promise<void> {
    const text = composer.trim();
    const agentId = selectedAgentId || selectedAgent?.id || "";
    if (!text || !agentId || !selectedProjectId) {
      return;
    }
    setSendError(null);
    let session: SessionSummary;
    try {
      session = await ensureActiveSession(agentId, selectedProjectId, selectedSessionId);
    } catch (error) {
      setSendError(error instanceof Error ? error.message : String(error));
      return;
    }
    const sessionId = session.id;
    const resourceSnapshot = selectedResources;
    setSelectedAgentId(agentId);
    setSendingSessionIds((current) => (current.includes(sessionId) ? current : [...current, sessionId]));
    setComposer("");
    setSelectedResources([]);
    const optimisticParts: ChatMessage["parts"] = [
      { type: "markdown", text },
      ...resourceSnapshot.map((resource) => ({
        type: "resource_ref" as const,
        resourceId: resource.id,
        displayName: resource.displayName,
        kind: resource.kind,
        versionOrHash: resource.versionOrHash,
        mimeType: resource.mimeType,
        relativePath: resource.relativePath,
        url: resource.url,
        contentStatus: "selected",
        truncated: false,
      })),
    ];
    const optimisticMessage: ChatMessage = {
      id: `local-user-${crypto.randomUUID()}`,
      sessionId,
      role: "user",
      status: "completed",
      createdAt: new Date().toISOString(),
      parts: optimisticParts,
    };
    applyFirstUserTitle(sessionId, text, optimisticMessage.createdAt);
    setMessages((current) => [...current, optimisticMessage]);
    try {
      await window.ppxClient.sendMessage({
        agentId,
        sessionId,
        projectId: selectedProjectId,
        text,
        ...(resourceSnapshot.length
          ? {
              resourceRefs: resourceSnapshot.map((resource) => ({
                id: resource.id,
                versionOrHash: resource.versionOrHash,
              })),
            }
          : {}),
      });
    } catch (error) {
      console.error("Failed to send message", error);
      setSendError(error instanceof Error ? error.message : String(error));
      if (selectedProjectIdRef.current === selectedProjectId) {
        setSelectedResources((current) => {
          const restored = new Map(current.map((resource) => [resource.id, resource]));
          for (const resource of resourceSnapshot) {
            restored.set(resource.id, resource);
          }
          return [...restored.values()];
        });
      }
      await refreshResources(selectedProjectId);
    } finally {
      setSendingSessionIds((current) => current.filter((item) => item !== sessionId));
    }
  }

  function handleComposerKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>): void {
    if (event.key !== "Enter" || event.shiftKey) {
      return;
    }
    event.preventDefault();
    if (!canSend) {
      return;
    }
    void handleSend();
  }

  async function handleRuntimeAction(): Promise<void> {
    if (!runtime) {
      return;
    }
    setSettingsError(null);
    try {
      const command = runtime.state === "stopped" ? "start" : "restart";
      const next = await window.ppxClient.runRuntimeCommand(command);
      setRuntime(next);
      const nextDiagnostics = await window.ppxClient.getDiagnostics();
      setDiagnostics(nextDiagnostics);
      setConnectionForm(buildConnectionSettings(nextDiagnostics));
    } catch (error) {
      setSettingsError(error instanceof Error ? error.message : String(error));
    }
  }

  async function refreshDiagnostics(): Promise<void> {
    setSettingsError(null);
    try {
      const nextDiagnostics = await window.ppxClient.getDiagnostics();
      setDiagnostics(nextDiagnostics);
      setConnectionForm(buildConnectionSettings(nextDiagnostics));
    } catch (error) {
      setSettingsError(error instanceof Error ? error.message : String(error));
    }
  }

  async function handleConnectionSave(): Promise<void> {
    const nextSettings = normalizeConnectionSettings(connectionForm);
    setSavingConnection(true);
    setSettingsError(null);
    try {
      const nextDiagnostics = await window.ppxClient.saveConnectionSettings(nextSettings);
      setDiagnostics(nextDiagnostics);
      setConnectionForm(buildConnectionSettings(nextDiagnostics));
      const nextRuntime = await window.ppxClient.runRuntimeCommand("restart");
      setRuntime(nextRuntime);
      await refreshProjects();
    } catch (error) {
      setSettingsError(error instanceof Error ? error.message : String(error));
    } finally {
      setSavingConnection(false);
    }
  }

  if (bootstrapError) {
    return (
      <div className="loading-shell">
        <div>
          <strong>gm-science failed to initialize</strong>
          <p>{bootstrapError}</p>
        </div>
      </div>
    );
  }

  if (!ready || !runtime) {
    return <div className="loading-shell">Loading gm-science...</div>;
  }

  return (
    <div className="app-shell science-app">
      {view === "projects" ? (
        <main className="science-dashboard">
          <div className="dashboard-inner">
            <header className="dashboard-header">
              <div className="dashboard-brand">
                <h1>gm-science</h1>
                <span>Beta</span>
              </div>
              <div className="dashboard-actions">
                <button className="icon-control" aria-label="Search" title="Search">
                  <Search size={18} />
                </button>
                <button
                  className="icon-control"
                  aria-label="Settings"
                  title="Settings"
                  onClick={() => openSettings("general")}
                >
                  <UserRound size={18} />
                </button>
                <button className="command-button" onClick={() => setProjectModalOpen(true)}>
                  <Plus size={17} />
                  New project
                </button>
              </div>
            </header>

            <div className="dashboard-columns">
              <section className="dashboard-section" aria-labelledby="projects-heading">
                <div className="dashboard-section-title">
                  <Folder size={18} />
                  <h2 id="projects-heading">Projects</h2>
                </div>
                <div className="dashboard-list project-dashboard-list">
                  {projects.map((project) => (
                    <button key={project.id} className="dashboard-project-row" onClick={() => void openProject(project)}>
                      <strong>{project.name}</strong>
                      <span>{project.sessionsCount} {project.sessionsCount === 1 ? "session" : "sessions"}</span>
                      <span>{project.artifactsCount} {project.artifactsCount === 1 ? "artifact" : "artifacts"}</span>
                      <time>{formatRelativeTime(project.updatedAt)}</time>
                    </button>
                  ))}
                  {projects.length === 0 ? (
                    <div className="dashboard-empty">
                      <strong>No projects yet</strong>
                      <button className="command-button" onClick={() => setProjectModalOpen(true)}>
                        <Plus size={17} />
                        New project
                      </button>
                    </div>
                  ) : null}
                </div>
              </section>

              <section className="dashboard-section" aria-labelledby="recent-heading">
                <div className="dashboard-section-title">
                  <Clock3 size={18} />
                  <h2 id="recent-heading">Recent sessions</h2>
                </div>
                <div className="dashboard-list recent-dashboard-list">
                  {recentSessions.slice(0, 8).map((session) => (
                    <button
                      key={session.id}
                      className="dashboard-session-row"
                      onClick={() => {
                        const project = projects.find((item) => item.id === session.projectId);
                        if (project) {
                          void openProject(project).then(() => void switchSession(session));
                        }
                      }}
                    >
                      <span className="session-status-dot" aria-hidden="true" />
                      <span>
                        <strong>{session.title}</strong>
                        <small>{projects.find((item) => item.id === session.projectId)?.name}</small>
                      </span>
                      <time>{formatRelativeTime(session.updatedAt)}</time>
                    </button>
                  ))}
                  {recentSessions.length === 0 ? <div className="dashboard-empty quiet">No recent sessions</div> : null}
                </div>
              </section>
            </div>
          </div>
        </main>
      ) : null}

      {view === "workspace" && selectedProject ? (
        <main className={`science-project-shell${filesOpen ? " files-visible" : ""}${sidebarCollapsed ? " sidebar-collapsed" : ""}`}>
          <aside className="project-sidebar">
            <header className="project-sidebar-header">
              <button className="icon-control" onClick={() => setView("projects")} aria-label="Back to dashboard" title="Back to dashboard">
                <ArrowLeft size={18} />
              </button>
              {!sidebarCollapsed ? <strong>{selectedProject.name}</strong> : null}
              <button
                className="icon-control sidebar-collapse"
                onClick={() => setSidebarCollapsed((current) => !current)}
                aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
                title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
              >
                {sidebarCollapsed ? <Menu size={18} /> : <PanelLeftClose size={18} />}
              </button>
            </header>

            {!sidebarCollapsed ? (
              <>
                <nav className="project-primary-nav" aria-label="Sessions">
                  <button onClick={() => void handleNewSession()}>
                    <Plus size={18} />
                    New
                  </button>
                  <button onClick={() => openSettings("skill")}>
                    <Box size={18} />
                    Customize
                  </button>
                  <button
                    className={filesOpen ? "active" : ""}
                    onClick={() => {
                      setWorkspacePanel("files");
                      setFilesOpen((current) => !current);
                    }}
                  >
                    <FileText size={18} />
                    Files
                  </button>
                </nav>

                <div className="sidebar-divider" />
                <div className="session-groups">
                  <span className="session-group-label">Recent</span>
                  <div className="session-list">
                    {projectSessions.map((session) => (
                      <button
                        key={session.id}
                        className={session.id === selectedSessionId ? "session-row active" : "session-row"}
                        onClick={() => void switchSession(session)}
                      >
                        <strong>{session.title}</strong>
                        <time>{formatRelativeTime(session.updatedAt)}</time>
                      </button>
                    ))}
                    {projectSessions.length === 0 ? <span className="session-empty">No sessions yet</span> : null}
                  </div>
                </div>
                <button className="sidebar-settings" onClick={() => openSettings("general")}>
                  <SettingsIcon size={18} />
                  Settings
                  <span className={`runtime-dot ${runtime.state}`} aria-label={`Runtime ${runtime.state}`} />
                </button>
              </>
            ) : null}
          </aside>

          <section className="project-main">
            <header className="project-tabbar">
              <div className="open-tabs" role="tablist" aria-label="Open workspace tabs">
                <button className="open-tab active" role="tab" aria-selected="true">
                  {selectedSession?.title ?? "New session"}
                </button>
                <button
                  className={filesOpen ? "open-tab active" : "open-tab"}
                  role="tab"
                  aria-selected={filesOpen}
                  onClick={() => setFilesOpen((current) => !current)}
                >
                  <FileText size={16} />
                  Files
                </button>
              </div>
              <button
                className="icon-control"
                aria-label="Toggle Files pane"
                title="Toggle Files pane"
                onClick={() => setFilesOpen((current) => !current)}
              >
                {filesOpen ? <PanelRightClose size={18} /> : <Columns2 size={18} />}
              </button>
            </header>

            <div className="conversation-surface">
              <section className="message-stream" ref={messageStreamRef} aria-label="Conversation">
                {messages.length ? (
                  messages.map((message, index) => {
                    const previous = messages[index - 1];
                    const compactAgentHeader =
                      message.role === "assistant" &&
                      (previous?.role === "assistant" || previous?.role === "system" || previous?.role === "tool");
                    return <MessageBubble key={message.id} message={message} showIdentity={!compactAgentHeader} />;
                  })
                ) : (
                  <div className="conversation-empty">
                    <h3>{selectedProject.name} is ready</h3>
                    <p>{selectedProject.agentContext || "Start with a research question, paper, dataset, or protocol."}</p>
                  </div>
                )}
              </section>

              <div className="science-composer">
                {selectedResources.length ? (
                  <div className="composer-resources" aria-label="Selected Project files">
                    <span>{selectedResources.length === 1 ? "1 file selected" : `${selectedResources.length} files selected`}</span>
                    <div>
                      {selectedResources.map((resource) => (
                        <span className="composer-resource" key={resource.id}>
                          <span>{resource.displayName}</span>
                          <button
                            type="button"
                            aria-label={`Remove ${resource.displayName}`}
                            title={`Remove ${resource.displayName}`}
                            onClick={() => setSelectedResources((current) => current.filter((item) => item.id !== resource.id))}
                          >
                            <X size={13} />
                          </button>
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}
                <textarea
                  ref={composerRef}
                  value={composer}
                  placeholder="Ask anything..."
                  aria-label="Message"
                  onChange={(event) => setComposer(event.target.value)}
                  onKeyDown={handleComposerKeyDown}
                />
                <div className="science-composer-actions">
                  <div>
                    <button className="icon-control" aria-label="Add to message" title="Add to message" onClick={() => setFilesOpen(true)}>
                      <Plus size={18} />
                    </button>
                    <div className="session-options-anchor" ref={sessionOptionsRef}>
                      <button
                        className={sessionPolicyActive ? "icon-control policy-active" : "icon-control"}
                        aria-label="Session options"
                        aria-haspopup="menu"
                        aria-expanded={sessionOptionsOpen}
                        title="Session options"
                        disabled={!selectedSessionId}
                        onClick={() => {
                          const nextOpen = !sessionOptionsOpen;
                          setSessionOptionsOpen(nextOpen);
                          if (nextOpen && selectedSessionId) {
                            void refreshSessionPolicy(selectedSessionId);
                          }
                        }}
                      >
                        <SlidersHorizontal size={18} />
                        {sessionPolicyActive ? <span className="policy-active-dot" aria-hidden="true" /> : null}
                      </button>
                      {sessionOptionsOpen ? (
                        <SessionOptionsMenu
                          policy={sessionPolicy}
                          loading={sessionPolicyLoading}
                          saving={sessionPolicySaving}
                          error={sessionPolicyError}
                          onChange={(input) => void updateSessionPolicy(input)}
                        />
                      ) : null}
                    </div>
                  </div>
                  {sendError ? <span className="composer-error">{sendError}</span> : null}
                  <div>
                    <button className="model-button" onClick={() => openSettings("general")}>
                      {selectedAgent?.model || "Model unavailable"}
                      <ChevronDown size={14} />
                    </button>
                    <button
                      className={canSend ? "send-button ready" : "send-button"}
                      disabled={!canSend}
                      onClick={() => void handleSend()}
                      aria-label="Send"
                      title="Send"
                    >
                      {selectedAgentBusy ? <RefreshCw className="spin" size={18} /> : <Send size={18} />}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </section>

          {filesOpen ? (
            <aside className={activeResource ? "project-files-pane inspector-active" : "project-files-pane"} aria-label="Files">
              <header className="files-pane-header">
                <div className="workspace-panel-tabs" role="tablist" aria-label="Project workspace panel">
                  <button className={workspacePanel === "files" ? "active" : ""} role="tab" aria-selected={workspacePanel === "files"} onClick={() => setWorkspacePanel("files")}>Artifacts</button>
                  <button className={workspacePanel === "data" ? "active" : ""} role="tab" aria-selected={workspacePanel === "data"} onClick={() => setWorkspacePanel("data")}>Data</button>
                  <button className={workspacePanel === "runs" ? "active" : ""} role="tab" aria-selected={workspacePanel === "runs"} onClick={() => setWorkspacePanel("runs")}>Runs</button>
                </div>
                <button className="icon-control" onClick={() => setFilesOpen(false)} aria-label="Close Files" title="Close Files">
                  <X size={18} />
                </button>
              </header>

              {workspacePanel === "files" ? (
                activeResource ? (
                  <ArtifactInspector
                    tabs={openResources}
                    activeResourceId={activeResourceId}
                    detail={activeResourceDetail}
                    loading={resourceDetailLoading}
                    error={resourceDetailError}
                    actionError={resourceActionError}
                    provenanceOpen={provenanceOpen}
                    onBack={showArtifactCatalog}
                    onSelectTab={(resource) => void openResource(resource)}
                    onCloseTab={closeResourceTab}
                    onRetry={() => void openResource(activeResource, true)}
                    onViewInContext={() => void viewActiveResourceInContext()}
                    onOpenProvenance={() => {
                      setResourceActionError(null);
                      setProvenanceOpen(true);
                    }}
                    onCloseProvenance={() => setProvenanceOpen(false)}
                    onOpenRelation={openRelatedResource}
                  />
                ) : (
                  <>
                    <div className="files-source-row">
                      <button className="source-button"><Library size={17} />All artifacts<ChevronDown size={14} /></button>
                      <span>{resources.length} {resources.length === 1 ? "artifact" : "artifacts"}</span>
                      <button className="icon-control" aria-label="Grid view" title="Grid view"><LayoutGrid size={17} /></button>
                    </div>
                    <label className="files-search">
                      <Search size={17} />
                      <input value={resourceSearch} placeholder="Search artifacts..." aria-label="Search files" onChange={(event) => setResourceSearch(event.target.value)} />
                    </label>
                    <div className="artifact-list">
                      {visibleResources.map((resource) => (
                        <ResourceItem
                          key={resource.id}
                          resource={resource}
                          selected={selectedResourceIds.has(resource.id)}
                          onOpen={(next) => void openResource(next)}
                          onToggle={(next) => setSelectedResources((current) => current.some((item) => item.id === next.id) ? current.filter((item) => item.id !== next.id) : [...current, next])}
                        />
                      ))}
                      {resources.length === 0 ? <div className="artifact-empty">No artifacts yet</div> : null}
                      {resources.length > 0 && visibleResources.length === 0 ? <div className="artifact-empty">No matching artifacts</div> : null}
                    </div>
                  </>
                )
              ) : workspacePanel === "data" ? (
                <DataPanel
                  projectId={selectedProjectId}
                  sessionId={selectedSessionId || undefined}
                  onRunStarted={(run) => {
                    runsRef.current = [run, ...runsRef.current.filter((item) => item.taskId !== run.taskId)];
                    setRuns(runsRef.current);
                  }}
                  onWorkspaceChanged={async () => {
                    await Promise.all([refreshResources(selectedProjectId), refreshRuns(selectedProjectId), refreshProjects()]);
                  }}
                />
              ) : (
                <>
                  <div className="science-runs-toolbar">
                    <span>{runs.some(isActiveRun) ? "Execution in progress" : "Local Python"}</span>
                    <button className="secondary small" onClick={openPythonRunDialog} aria-label="New Python run"><Plus size={15} />New run</button>
                  </div>
                  <div className="science-run-list">
                    {runError ? <p className="science-runs-error">{runError}</p> : null}
                    {runs.map((run) => <RunItem key={run.taskId} run={run} actionPending={runActionTaskId === run.taskId} onCancel={(item) => void cancelPythonRun(item)} onRetry={(item) => void retryPythonRun(item)} />)}
                    {runs.length === 0 ? <div className="artifact-empty">No runs yet</div> : null}
                  </div>
                </>
              )}
            </aside>
          ) : null}
        </main>
      ) : null}

      {settingsOpen ? (
        <div className="settings-backdrop" role="presentation">
          <section className="science-settings-dialog" role="dialog" aria-modal="true" aria-labelledby="settings-title">
            <aside className="settings-sidebar">
              <span className="settings-nav-label">Capabilities</span>
              <button className={settingsSection === "skill" ? "active" : ""} onClick={() => setSettingsSection("skill")}><BookOpen size={18} />Skills</button>
              <button className={settingsSection === "connector" ? "active" : ""} onClick={() => setSettingsSection("connector")}><LayoutGrid size={18} />Connectors</button>
              <button className={settingsSection === "specialist" ? "active" : ""} onClick={() => setSettingsSection("specialist")}><UsersRound size={18} />Specialists</button>
              <button className={settingsSection === "memory" ? "active" : ""} onClick={() => setSettingsSection("memory")}><Brain size={18} />Memory</button>
              <button className={settingsSection === "compute" ? "active" : ""} onClick={() => setSettingsSection("compute")}><Cpu size={18} />Compute</button>
              <button className={settingsSection === "network" ? "active" : ""} onClick={() => setSettingsSection("network")}><Network size={18} />Network</button>
              <span className="settings-nav-label workspace-label">Workspace</span>
              <button className={settingsSection === "permissions" ? "active" : ""} onClick={() => setSettingsSection("permissions")}><ShieldCheck size={18} />Permissions</button>
              <button className={settingsSection === "credentials" ? "active" : ""} onClick={() => setSettingsSection("credentials")}><KeyRound size={18} />Credentials</button>
              <button className={settingsSection === "storage" ? "active" : ""} onClick={() => setSettingsSection("storage")}><Cloud size={18} />Storage</button>
              <button className={settingsSection === "usage" ? "active" : ""} onClick={() => setSettingsSection("usage")}><LayoutGrid size={18} />Usage</button>
              <button className={settingsSection === "general" ? "active" : ""} onClick={() => setSettingsSection("general")}><SettingsIcon size={18} />General</button>
            </aside>

            <div className="settings-main">
              <header className="settings-dialog-header">
                <h2 id="settings-title">{SETTINGS_SECTION_TITLES[settingsSection]}</h2>
                <button className="icon-control" onClick={() => setSettingsOpen(false)} aria-label="Close Settings" title="Close Settings"><X size={20} /></button>
              </header>

              <div className="settings-dialog-content">
                {isCapabilitySection(settingsSection) ? (
                  <CapabilitiesPanel
                    kind={settingsSection}
                    items={capabilities}
                    loading={capabilitiesLoading}
                    saving={capabilitiesSaving}
                    error={capabilitiesError}
                    onToggle={(capabilityId) => void toggleCapability(capabilityId)}
                    onRefresh={() => void refreshCapabilities()}
                  />
                ) : null}

                {settingsSection === "memory" ? (
                  <MemorySettingsPanel
                    projectId={selectedProjectId}
                    projectName={selectedProject?.name ?? ""}
                    settings={scienceSettings}
                    settingsLoading={scienceSettingsLoading}
                    settingsSaving={scienceSettingsSaving}
                    settingsError={settingsError}
                    onSetGlobalEnabled={(enabled) => updateScienceSettings({ memoryEnabled: enabled })}
                  />
                ) : null}

                {settingsSection === "compute" ? (
                  <div className="settings-page science-settings-page">
                    <div className="settings-page-title"><div><h3>Compute</h3><p>Choose where scientific workloads run.</p></div></div>
                    {settingsError ? <p className="composer-error">{settingsError}</p> : null}
                    <section className="settings-section-block settings-row-section">
                      <div><h4>Local computer</h4><p>{runtime.summary}</p><small>{runtime.detail}</small></div>
                      <span className={`status-chip ${runtime.state}`}>{runtime.state}</span>
                    </section>
                    <section className="settings-section-block settings-row-section">
                      <div><h4>SSH hosts</h4><p>Remote servers and clusters.</p></div>
                      <span className="muted-value">Not configured</span>
                    </section>
                    <section className="settings-section-block settings-row-section">
                      <div><h4>Cloud providers</h4><p>Modal and remote GPU providers.</p></div>
                      <span className="muted-value">Not configured</span>
                    </section>
                    <div className="settings-actions-row">
                      <button className="secondary" onClick={() => void handleRuntimeAction()}>{runtimeActionLabel(runtime.state)}</button>
                      <button className="secondary" onClick={() => void refreshDiagnostics()}><RefreshCw size={15} />Refresh</button>
                      {selectedProject ? <button className="secondary" onClick={() => { setSettingsOpen(false); setFilesOpen(true); setWorkspacePanel("runs"); }}><Play size={15} />Open runs</button> : null}
                    </div>
                  </div>
                ) : null}

                {settingsSection === "network" ? (
                  <div className="settings-page science-settings-page">
                    <div className="settings-page-title"><div><h3>Network</h3><p>Research services currently exposed through configured connectors.</p></div></div>
                    <section className="settings-section-block">
                      <h4>Research data sources</h4>
                      <div className="service-list">
                        {capabilities.filter((item) => item.kind === "connector").map((item) => (
                          <div className="service-row" key={item.id}><span><Database size={17} /><strong>{item.name}</strong></span><span className={`status-chip ${item.status}`}>{item.status.replaceAll("_", " ")}</span></div>
                        ))}
                        {capabilities.every((item) => item.kind !== "connector") ? <p>No connectors discovered.</p> : null}
                      </div>
                    </section>
                    <section className="settings-section-block settings-row-section"><div><h4>Package mirrors</h4><p>Conda and Python mirrors use the host environment.</p></div><span className="muted-value">System default</span></section>
                  </div>
                ) : null}

                {settingsSection === "permissions" ? (
                  <div className="settings-page science-settings-page">
                    <div className="settings-page-title"><div><h3>Permissions</h3><p>Control persistent agent and capability changes.</p></div></div>
                    <div className="settings-notice"><ShieldCheck size={19} /><div><strong>Trusted local mode</strong><p>gm-science currently runs on your computer without a sandbox or per-action grant registry.</p></div></div>
                    <section className="settings-section-block"><h4>Registry writes</h4><div className="permission-list">{["Update project capabilities", "Create project sessions", "Create local artifacts", "Run local analyses"].map((label) => <div key={label}><span>{label}</span><span className="status-chip">Local</span></div>)}</div></section>
                  </div>
                ) : null}

                {settingsSection === "credentials" ? (
                  <CredentialsSettingsPanel
                    settings={scienceSettings}
                    loading={scienceSettingsLoading}
                    saving={scienceSettingsSaving}
                    error={settingsError}
                    onUpdate={updateScienceSettings}
                  />
                ) : null}

                {settingsSection === "storage" ? (
                  <div className="settings-page science-settings-page">
                    <div className="settings-page-title"><div><h3>Storage</h3><p>Local locations used for projects, files, and history.</p></div></div>
                    <section className="settings-section-block settings-row-section"><div><h4>Data location</h4><p className="path-value">{diagnostics?.globalConfigPath || "Local gm-science configuration"}</p></div><HardDrive size={20} /></section>
                    <section className="settings-section-block"><h4>Workspace data</h4><div className="storage-grid"><span><Folder size={18} />Projects<strong>{projects.length}</strong></span><span><MessageSquarePlus size={18} />Sessions<strong>{sessions.length}</strong></span><span><FileText size={18} />Artifacts<strong>{resources.length}</strong></span><span><Play size={18} />Runs<strong>{runs.length}</strong></span></div></section>
                    <section className="settings-section-block settings-row-section"><div><h4>Cloud storage</h4><p>Browse and manage bucket connections.</p></div><span className="muted-value">Not configured</span></section>
                  </div>
                ) : null}

                {settingsSection === "usage" ? (
                  <div className="settings-page science-settings-page">
                    <div className="settings-page-title"><div><h3>Usage</h3><p>Runtime and model usage for this local workspace.</p></div></div>
                    <section className="settings-section-block"><h4>Where tokens go</h4><p>Detailed token accounting is not yet reported by the configured provider adapter.</p><div className="usage-placeholder"><Zap size={24} /><span>No usage data available</span></div></section>
                  </div>
                ) : null}

                {settingsSection === "general" ? (
                  <GeneralSettingsPanel
                    settings={scienceSettings}
                    loading={scienceSettingsLoading}
                    saving={scienceSettingsSaving}
                    error={settingsError}
                    runtime={runtime}
                    diagnostics={diagnostics}
                    connectionForm={connectionForm}
                    savingConnection={savingConnection}
                    onUpdateModel={(model) => updateScienceSettings({ model })}
                    onConnectionFormChange={setConnectionForm}
                    onSaveConnection={handleConnectionSave}
                  />
                ) : null}
              </div>
            </div>
          </section>
        </div>
      ) : null}

      {projectModalOpen ? (
        <div className="modal-backdrop" role="presentation">
          <section className="project-modal" role="dialog" aria-modal="true" aria-labelledby="new-project-title">
            <header>
              <h2 id="new-project-title">New Project</h2>
              <button className="icon-button" onClick={() => setProjectModalOpen(false)} aria-label="Close">
                ×
              </button>
            </header>
            <label className="settings-field">
              <span>Name</span>
              <input
                autoFocus
                value={projectForm.name}
                placeholder="Project name"
                onChange={(event) => setProjectForm((current) => ({ ...current, name: event.target.value }))}
              />
            </label>
            <label className="settings-field">
              <span>Description</span>
              <textarea
                value={projectForm.description}
                placeholder="Describe what this project is about..."
                onChange={(event) => setProjectForm((current) => ({ ...current, description: event.target.value }))}
              />
            </label>
            <label className="settings-field">
              <span>Agent Context</span>
              <textarea
                value={projectForm.agentContext}
                placeholder="e.g., Always use GRCh38 for genome references..."
                onChange={(event) => setProjectForm((current) => ({ ...current, agentContext: event.target.value }))}
              />
            </label>
            {projectError ? <p className="composer-error">{projectError}</p> : null}
            <footer>
              <button className="secondary" onClick={() => setProjectModalOpen(false)}>
                Cancel
              </button>
              <button className="primary" disabled={creatingProject || !projectForm.name.trim()} onClick={() => void createProject()}>
                {creatingProject ? "Creating..." : "Create"}
              </button>
            </footer>
          </section>
        </div>
      ) : null}

      {pythonRunModalOpen ? (
        <div className="modal-backdrop" role="presentation">
          <section className="project-modal python-run-modal" role="dialog" aria-modal="true" aria-labelledby="new-run-title">
            <header>
              <div>
                <h2 id="new-run-title">New Python Run</h2>
                <p>Runs locally in this Project workspace.</p>
              </div>
              <button className="icon-button" onClick={() => setPythonRunModalOpen(false)} aria-label="Close Python run dialog">
                ×
              </button>
            </header>
            <div className="python-run-form-body">
              <label className="settings-field">
                <span>Title</span>
                <input
                  autoFocus
                  value={pythonRunForm.title}
                  placeholder="Run title"
                  onChange={(event) => setPythonRunForm((current) => ({ ...current, title: event.target.value }))}
                />
              </label>
              <label className="settings-field">
                <span>Python source</span>
                <textarea
                  className="python-source-editor"
                  value={pythonRunForm.source}
                  spellCheck={false}
                  aria-label="Python source"
                  onChange={(event) => setPythonRunForm((current) => ({ ...current, source: event.target.value }))}
                />
              </label>
              <label className="settings-field">
                <span>Input JSON</span>
                <textarea
                  className="python-input-editor"
                  value={pythonRunForm.inputJson}
                  spellCheck={false}
                  aria-label="Input JSON"
                  onChange={(event) => setPythonRunForm((current) => ({ ...current, inputJson: event.target.value }))}
                />
                <small>Available from the GM_SCIENCE_INPUT_PATH environment variable. Use an argv array for command-line arguments.</small>
              </label>
              {runError ? <p className="composer-error">{runError}</p> : null}
            </div>
            <footer>
              <button className="secondary" onClick={() => setPythonRunModalOpen(false)}>
                Cancel
              </button>
              <button
                className="primary"
                disabled={submittingRun || !pythonRunForm.title.trim() || !pythonRunForm.source.trim()}
                onClick={() => void createPythonRun()}
              >
                {submittingRun ? "Starting..." : "Run"}
              </button>
            </footer>
          </section>
        </div>
      ) : null}
    </div>
  );
}
