import { useEffect, useMemo, useRef, useState } from "react";
import { CapabilitiesPanel } from "./components/CapabilitiesPanel";
import { MessageBubble } from "./components/MessageBubble";
import type {
  AgentProfile,
  BootstrapPayload,
  ChatMessage,
  ClientDiagnostics,
  ConnectionSettings,
  GmScienceArtifact,
  GmScienceCapability,
  GmScienceCapabilityKind,
  GmScienceProject,
  RuntimeState,
  RuntimeStatus,
  SessionSummary,
} from "./types";

type NavView = "projects" | "workspace" | "settings";
type SettingsSection = GmScienceCapabilityKind | "runtime";

interface ProjectFormState {
  name: string;
  description: string;
  agentContext: string;
}

const EMPTY_PROJECT_FORM: ProjectFormState = {
  name: "",
  description: "",
  agentContext: "",
};

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
    normalized === "New local session" ||
    normalized === "New chat" ||
    normalized === "新对话" ||
    normalized.startsWith("Session ")
  );
}

function mergeSessionSummary(existing: SessionSummary | undefined, incoming: SessionSummary): SessionSummary {
  if (!existing) {
    return incoming;
  }
  if (isGenericSessionTitle(incoming.title) && !isGenericSessionTitle(existing.title)) {
    return { ...incoming, title: existing.title };
  }
  return incoming;
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

function formatArtifactType(type: string): string {
  if (!type) {
    return "artifact";
  }
  return type.replace(/[_-]+/g, " ");
}

function metadataText(metadata: Record<string, unknown>, key: string): string {
  const value = metadata[key];
  return typeof value === "string" || typeof value === "number" ? String(value) : "";
}

function metadataList(metadata: Record<string, unknown>, key: string): string[] {
  const value = metadata[key];
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && Boolean(item)) : [];
}

function metadataObjectList(metadata: Record<string, unknown>, key: string): Record<string, unknown>[] {
  const value = metadata[key];
  return Array.isArray(value)
    ? value.filter(
        (item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item),
      )
    : [];
}

function formatEvidenceScope(scope: string): string {
  if (scope === "metadata_abstract") {
    return "abstract metadata";
  }
  if (scope === "local_text") {
    return "local text";
  }
  return scope.replaceAll("_", " ");
}

function artifactSearchText(artifact: GmScienceArtifact): string {
  return `${artifact.title} ${artifact.type} ${JSON.stringify(artifact.metadata)}`.toLowerCase();
}

function isWebUrl(value: string): boolean {
  return /^https?:\/\//i.test(value.trim());
}

function ArtifactItem({ artifact }: { artifact: GmScienceArtifact }) {
  const type = artifact.type.trim().toLowerCase() || "artifact";
  const metadata = artifact.metadata ?? {};
  const authors = metadataList(metadata, "authors");
  const sources = metadataList(metadata, "source_names");
  const year = metadataText(metadata, "year");
  const citationCount = metadataText(metadata, "citation_count");
  const identifier =
    (metadataText(metadata, "doi") && `DOI ${metadataText(metadata, "doi")}`) ||
    (metadataText(metadata, "pmid") && `PMID ${metadataText(metadata, "pmid")}`) ||
    (metadataText(metadata, "arxiv_id") && `arXiv ${metadataText(metadata, "arxiv_id")}`) ||
    (metadataText(metadata, "openalex_id") && `OpenAlex ${metadataText(metadata, "openalex_id")}`) ||
    "";
  const paperDetails = [
    year,
    sources.join(" + "),
    citationCount && `${citationCount} citation${citationCount === "1" ? "" : "s"}`,
  ]
    .filter(Boolean)
    .join(" · ");
  const citedPapers = metadataList(metadata, "paper_artifact_ids").length;
  const reportFileName = artifact.pathOrUrl.split(/[\\/]/).pop() ?? "";
  const reportDate = artifact.createdAt ? new Date(artifact.createdAt).toLocaleDateString("zh-CN") : "";
  const reportDetails = [
    reportFileName,
    `${citedPapers} cited ${citedPapers === 1 ? "paper" : "papers"}`,
    reportDate,
  ]
    .filter(Boolean)
    .join(" · ");
  const readingSources = metadataList(metadata, "source_artifact_ids");
  const evidenceScopes = metadataList(metadata, "evidence_scopes").map(formatEvidenceScope);
  const readingDetails = [
    `${readingSources.length} ${readingSources.length === 1 ? "source" : "sources"}`,
    evidenceScopes.length > 0 && `Evidence: ${evidenceScopes.join(" + ")}`,
  ]
    .filter(Boolean)
    .join(" · ");
  const confidenceNote = metadataText(metadata, "confidence_note");
  const readingFocus = metadataText(metadata, "focus");
  const verdict = metadataText(metadata, "verdict").toLowerCase();
  const targetArtifactId = metadataText(metadata, "target_artifact_id");
  const findings = metadataObjectList(metadata, "findings");
  const severityOrder = ["blocking", "major", "minor"];
  const severityDetails = severityOrder
    .map((severity) => {
      const count = findings.filter((finding) => metadataText(finding, "severity").toLowerCase() === severity).length;
      return count > 0 ? `${count} ${severity}` : "";
    })
    .filter(Boolean)
    .join(" · ");
  const marker =
    type === "paper"
      ? "P"
      : type === "report"
        ? "R"
        : type === "citation"
          ? "C"
          : type === "reading_note"
            ? "N"
            : type === "critique_report"
              ? "Q"
              : "A";

  return (
    <article className={`artifact-item artifact-${type}`}>
      <div className="artifact-title-row">
        <span className="artifact-marker" aria-hidden="true">
          {marker}
        </span>
        <div>
          <strong>{artifact.title}</strong>
          <span className="artifact-kind">{formatArtifactType(type)}</span>
        </div>
      </div>
      {type === "paper" && authors.length > 0 ? <p className="artifact-byline">{authors.slice(0, 3).join(", ")}</p> : null}
      {type === "paper" && paperDetails ? <p className="artifact-detail">{paperDetails}</p> : null}
      {type === "paper" && identifier ? <p className="artifact-identifier">{identifier}</p> : null}
      {type === "report" ? <p className="artifact-detail">{reportDetails}</p> : null}
      {type === "citation" ? <p className="artifact-detail">Linked to report</p> : null}
      {type === "reading_note" ? <p className="artifact-detail">{readingDetails}</p> : null}
      {type === "reading_note" && readingFocus ? <p className="artifact-note">Focus: {readingFocus}</p> : null}
      {type === "reading_note" && confidenceNote ? <p className="artifact-note">{confidenceNote}</p> : null}
      {type === "critique_report" ? (
        <div className="artifact-critique-summary">
          <div>
            {verdict ? <span className={`artifact-verdict ${verdict}`}>{verdict}</span> : null}
            {severityDetails ? <span className="artifact-severity-summary">{severityDetails}</span> : null}
          </div>
          {targetArtifactId ? <p className="artifact-target">Target: {targetArtifactId}</p> : null}
          {findings.length > 0 ? (
            <ul className="artifact-findings">
              {findings.slice(0, 3).map((finding, index) => (
                <li key={`${metadataText(finding, "severity")}-${index}`}>
                  <span className={`finding-severity ${metadataText(finding, "severity").toLowerCase()}`}>
                    {metadataText(finding, "severity") || "finding"}
                  </span>
                  <span>{metadataText(finding, "claim") || metadataText(finding, "category")}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
      {isWebUrl(artifact.pathOrUrl) ? (
        <a className="artifact-link" href={artifact.pathOrUrl} target="_blank" rel="noreferrer">
          Open
        </a>
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
  const [artifacts, setArtifacts] = useState<GmScienceArtifact[]>([]);
  const [artifactSearch, setArtifactSearch] = useState("");
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
  const [capabilities, setCapabilities] = useState<GmScienceCapability[]>([]);
  const [capabilitiesLoading, setCapabilitiesLoading] = useState(false);
  const [capabilitiesSaving, setCapabilitiesSaving] = useState(false);
  const [capabilitiesDirty, setCapabilitiesDirty] = useState(false);
  const [capabilitiesError, setCapabilitiesError] = useState<string | null>(null);
  const [sendingSessionIds, setSendingSessionIds] = useState<string[]>([]);
  const [connectionForm, setConnectionForm] = useState<ConnectionSettings>(buildConnectionSettings(null));
  const [savingConnection, setSavingConnection] = useState(false);
  const [projectModalOpen, setProjectModalOpen] = useState(false);
  const [projectForm, setProjectForm] = useState<ProjectFormState>(EMPTY_PROJECT_FORM);
  const [creatingProject, setCreatingProject] = useState(false);
  const switchRequestIdRef = useRef(0);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const messageStreamRef = useRef<HTMLElement | null>(null);
  const nextScrollBehaviorRef = useRef<ScrollBehavior>("auto");
  const selectedProjectIdRef = useRef("");

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId) ?? null,
    [projects, selectedProjectId],
  );
  const selectedAgent = useMemo(
    () => agents.find((agent) => agent.id === selectedAgentId) ?? agents[0] ?? null,
    [agents, selectedAgentId],
  );
  const selectedSession = useMemo(
    () => sessions.find((session) => session.id === selectedSessionId) ?? null,
    [sessions, selectedSessionId],
  );
  const selectedAgentBusy = useMemo(
    () =>
      Boolean(selectedAgentId) &&
      ((selectedSessionId && sendingSessionIds.includes(selectedSessionId)) ||
        sessions.some((session) => session.agentId === selectedAgentId && sendingSessionIds.includes(session.id))),
    [selectedAgentId, selectedSessionId, sendingSessionIds, sessions],
  );
  const visibleArtifacts = useMemo(() => {
    const query = artifactSearch.trim().toLowerCase();
    return query ? artifacts.filter((artifact) => artifactSearchText(artifact).includes(query)) : artifacts;
  }, [artifactSearch, artifacts]);
  const canSend = Boolean(composer.trim()) && Boolean(selectedAgentId) && Boolean(selectedProjectId) && !selectedAgentBusy;

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
          void refreshArtifacts(selectedProjectIdRef.current);
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
        void refreshArtifacts(selectedProjectIdRef.current);
      }
    });

    window.ppxClient
      .bootstrap()
      .then(async (payload: BootstrapPayload) => {
        if (!mounted) {
          return;
        }
        let nextSessions = payload.sessions;
        let nextSelectedSessionId = payload.selectedSessionId;
        let nextMessages = payload.messages;
        if (payload.selectedAgentId && !nextSelectedSessionId) {
          const created = await window.ppxClient.createSession(payload.selectedAgentId);
          nextSessions = [created.session, ...nextSessions.filter((session) => session.id !== created.session.id)];
          nextSelectedSessionId = created.session.id;
          nextMessages = [];
        }
        const projectPayload = await window.ppxClient.listGmScienceProjects().catch(() => ({ projects: [] }));
        const nextDiagnostics = await window.ppxClient.getDiagnostics().catch(() => null);
        if (!mounted) {
          return;
        }
        setRuntime(payload.runtime);
        setAgents(payload.agents);
        setSessions(nextSessions);
        nextScrollBehaviorRef.current = "auto";
        setMessages(nextMessages);
        setSelectedAgentId(payload.selectedAgentId || payload.agents[0]?.id || "");
        setSelectedSessionId(nextSelectedSessionId);
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
    if (view !== "settings") {
      return;
    }
    void refreshCapabilities();
  }, [view, selectedProjectId]);

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
      setCapabilitiesDirty(false);
    } catch (error) {
      setCapabilitiesError(error instanceof Error ? error.message : String(error));
    } finally {
      setCapabilitiesLoading(false);
    }
  }

  function openSettings(section: SettingsSection): void {
    setSettingsSection(section);
    setView("settings");
  }

  function toggleCapability(capabilityId: string): void {
    setCapabilities((current) =>
      current.map((item) =>
        item.id === capabilityId
          ? { ...item, projectEnabled: !(item.projectEnabled ?? item.defaultEnabled) }
          : item,
      ),
    );
    setCapabilitiesDirty(true);
    setCapabilitiesError(null);
  }

  async function saveCapabilities(): Promise<void> {
    if (!selectedProjectId) {
      return;
    }
    setCapabilitiesSaving(true);
    setCapabilitiesError(null);
    try {
      const response = await window.ppxClient.updateGmScienceProjectCapabilities(selectedProjectId, {
        enabledSkills: capabilities.filter((item) => item.kind === "skill" && item.projectEnabled).map((item) => item.id),
        enabledConnectors: capabilities
          .filter((item) => item.kind === "connector" && item.projectEnabled)
          .map((item) => item.id),
        enabledSpecialists: capabilities
          .filter((item) => item.kind === "specialist" && item.projectEnabled)
          .map((item) => item.id),
      });
      setProjects((current) =>
        current.map((project) => (project.id === response.project.id ? response.project : project)),
      );
      setCapabilities(response.capabilities);
      setCapabilitiesDirty(false);
    } catch (error) {
      setCapabilitiesError(error instanceof Error ? error.message : String(error));
    } finally {
      setCapabilitiesSaving(false);
    }
  }

  async function refreshArtifacts(projectId: string, clearOnError = false): Promise<void> {
    if (!projectId) {
      return;
    }
    try {
      const payload = await window.ppxClient.listGmScienceArtifacts(projectId);
      if (selectedProjectIdRef.current === projectId) {
        setArtifacts(payload.artifacts);
      }
    } catch {
      if (clearOnError && selectedProjectIdRef.current === projectId) {
        setArtifacts([]);
      }
    }
  }

  async function openProject(project: GmScienceProject): Promise<void> {
    setProjectError(null);
    selectedProjectIdRef.current = project.id;
    setSelectedProjectId(project.id);
    setArtifactSearch("");
    setView("workspace");
    await refreshArtifacts(project.id, true);
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
    if (!agentId) {
      return;
    }
    setSendError(null);
    const created = await window.ppxClient.createSession(agentId);
    setSessions((current) => [created.session, ...current.filter((item) => item.id !== created.session.id)]);
    setSelectedAgentId(agentId);
    setSelectedSessionId(created.session.id);
    setMessages([]);
  }

  async function ensureActiveSession(agentId: string, preferredSessionId: string): Promise<SessionSummary> {
    const existing = sessions.find((session) => session.id === preferredSessionId && session.agentId === agentId);
    if (existing) {
      return existing;
    }
    const listed = await window.ppxClient.listSessions(agentId);
    const firstSession = listed.sessions[0];
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
    const created = await window.ppxClient.createSession(agentId);
    setSessions((current) => [created.session, ...current.filter((item) => item.id !== created.session.id)]);
    setSelectedSessionId(created.session.id);
    setMessages([]);
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
      session = await ensureActiveSession(agentId, selectedSessionId);
    } catch (error) {
      setSendError(error instanceof Error ? error.message : String(error));
      return;
    }
    const sessionId = session.id;
    setSelectedAgentId(agentId);
    setSendingSessionIds((current) => (current.includes(sessionId) ? current : [...current, sessionId]));
    setComposer("");
    const optimisticMessage: ChatMessage = {
      id: `local-user-${crypto.randomUUID()}`,
      sessionId,
      role: "user",
      status: "completed",
      createdAt: new Date().toISOString(),
      parts: [{ type: "markdown", text }],
    };
    applyFirstUserTitle(sessionId, text, optimisticMessage.createdAt);
    setMessages((current) => [...current, optimisticMessage]);
    try {
      await window.ppxClient.sendMessage({
        agentId,
        sessionId,
        projectId: selectedProjectId,
        text,
      });
    } catch (error) {
      console.error("Failed to send message", error);
      setSendError(error instanceof Error ? error.message : String(error));
      await refreshArtifacts(selectedProjectId);
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
      <aside className="nav-shell">
        <nav className="nav-rail" aria-label="Primary">
          <button
            className={view === "projects" ? "nav-item active" : "nav-item"}
            onClick={() => setView("projects")}
            aria-label="Projects"
            title="Projects"
          >
            <span className="nav-symbol">P</span>
          </button>
          <button
            className={view === "workspace" ? "nav-item active" : "nav-item"}
            onClick={() => selectedProject && setView("workspace")}
            disabled={!selectedProject}
            aria-label="Workspace"
            title="Workspace"
          >
            <span className="nav-symbol">W</span>
          </button>
          <button
            className={view === "settings" ? "nav-item active" : "nav-item"}
            onClick={() => openSettings("skill")}
            aria-label="设置"
            title="设置"
          >
            <span className="nav-symbol">S</span>
          </button>
        </nav>
      </aside>

      {view === "projects" ? (
        <main className="projects-home">
          <header className="projects-header">
            <div>
              <h1>gm-science</h1>
              <p>Local personal research agent</p>
            </div>
            <div className="projects-actions">
              <button className="secondary" onClick={() => void refreshProjects()}>
                Refresh
              </button>
              <button className="primary" onClick={() => setProjectModalOpen(true)}>
                + New project
              </button>
            </div>
          </header>

          <section className="projects-grid">
            <div className="projects-list-panel">
              <div className="section-title-row">
                <h2>Projects</h2>
                <span>{projects.length}</span>
              </div>
              <div className="project-list">
                {projects.map((project) => (
                  <button key={project.id} className="project-row" onClick={() => void openProject(project)}>
                    <span className="project-name">{project.name}</span>
                    <span className="project-meta">{project.sessionsCount} sessions</span>
                    <span className="project-meta">{project.artifactsCount} artifacts</span>
                    <time>{new Date(project.updatedAt).toLocaleDateString("zh-CN")}</time>
                  </button>
                ))}
                {projects.length === 0 ? (
                  <div className="project-empty">
                    <strong>No projects yet</strong>
                    <button className="primary" onClick={() => setProjectModalOpen(true)}>
                      + New project
                    </button>
                  </div>
                ) : null}
              </div>
            </div>

            <div className="recent-panel">
              <div className="section-title-row">
                <h2>Recent sessions</h2>
                <span>{sessions.length}</span>
              </div>
              <div className="recent-list">
                {sessions.slice(0, 5).map((session) => (
                  <button
                    key={session.id}
                    className="recent-row"
                    onClick={() => {
                      if (projects[0]) {
                        void openProject(projects[0]).then(() => void switchSession(session));
                      }
                    }}
                  >
                    <strong>{session.title}</strong>
                    <time>{new Date(session.updatedAt).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}</time>
                  </button>
                ))}
              </div>
            </div>
          </section>
        </main>
      ) : null}

      {view === "workspace" && selectedProject ? (
        <>
          <section className="sidebar-shell">
            <aside className="sidebar science-sidebar">
              <button className="project-back" onClick={() => setView("projects")}>
                ← Projects
              </button>
              <div className="active-project-block">
                <strong>{selectedProject.name}</strong>
                <p>{selectedProject.description || "Personal research workspace"}</p>
                <button className="project-customize" onClick={() => openSettings("skill")}>
                  Customize
                </button>
              </div>
              <div className="sidebar-section">
                <div className="sidebar-section-header">
                  <span>Sessions</span>
                  <button className="secondary small" onClick={() => void handleNewSession()}>
                    New
                  </button>
                </div>
                <div className="list-stack">
                  {sessions.map((session) => (
                    <button
                      key={session.id}
                      className={session.id === selectedSessionId ? "list-item active" : "list-item"}
                      onClick={() => void switchSession(session)}
                    >
                      <div>
                        <strong>{session.title}</strong>
                      </div>
                      <time>{new Date(session.updatedAt).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}</time>
                    </button>
                  ))}
                </div>
              </div>
            </aside>
          </section>

          <section className="workspace-shell">
            <header className="column-topbar workspace-topbar">
              <div className="topbar-copy">
                <strong>{selectedSession?.title ?? selectedProject.name}</strong>
                <span>{selectedAgent?.name ?? "science-research"}</span>
              </div>
              <button className="topbar-pill" onClick={() => openSettings("runtime")}>
                <span className={`runtime-dot ${runtime.state}`} />
                {runtime.state}
              </button>
            </header>
            <main className="workspace-frame chat-workspace">
              <section className="message-stream" ref={messageStreamRef}>
                {messages.length ? (
                  messages.map((message, index) => {
                    const previous = messages[index - 1];
                    const compactAgentHeader =
                      message.role === "assistant" &&
                      (previous?.role === "assistant" || previous?.role === "system" || previous?.role === "tool");
                    return <MessageBubble key={message.id} message={message} showIdentity={!compactAgentHeader} />;
                  })
                ) : (
                  <div className="empty-state">
                    <h3>{selectedProject.name} is ready</h3>
                    <p>{selectedProject.agentContext || "Start with a research question, paper, dataset, or protocol."}</p>
                  </div>
                )}
              </section>
              <div className="composer-shell">
                <textarea
                  ref={composerRef}
                  value={composer}
                  placeholder="向本地 agent 发送任务..."
                  onChange={(event) => setComposer(event.target.value)}
                  onKeyDown={handleComposerKeyDown}
                />
                <div className="composer-actions">
                  {sendError ? <span className="composer-error">{sendError}</span> : <span />}
                  <button className={canSend ? "send-button ready" : "send-button"} disabled={!canSend} onClick={() => void handleSend()}>
                    {selectedAgentBusy ? "运行中" : "发送"}
                  </button>
                </div>
              </div>
            </main>
          </section>

          <aside className="artifacts-shell">
            <header className="artifacts-header">
              <strong>Artifacts</strong>
              <span>{artifacts.length}</span>
            </header>
            <input
              className="artifact-search"
              value={artifactSearch}
              placeholder="Search artifacts..."
              aria-label="Search artifacts"
              onChange={(event) => setArtifactSearch(event.target.value)}
            />
            <div className="artifact-list">
              {visibleArtifacts.map((artifact) => (
                <ArtifactItem key={artifact.id} artifact={artifact} />
              ))}
              {artifacts.length === 0 ? <div className="artifact-empty">No artifacts yet</div> : null}
              {artifacts.length > 0 && visibleArtifacts.length === 0 ? (
                <div className="artifact-empty">No matching artifacts</div>
              ) : null}
            </div>
          </aside>
        </>
      ) : null}

      {view === "settings" ? (
        <main className="settings-shell">
          <header className="column-topbar workspace-topbar">
            <div className="topbar-copy">
              <strong>Settings</strong>
              <span>{selectedProject?.name ?? "gm-science local runtime"}</span>
            </div>
          </header>
          <section className="workspace-frame settings-frame">
            <div className="settings-layout">
              <aside className="settings-menu" aria-label="Settings sections">
                <span className="settings-menu-label">Capabilities</span>
                <button className={settingsSection === "skill" ? "active" : ""} onClick={() => setSettingsSection("skill")}>
                  Skills
                </button>
                <button
                  className={settingsSection === "connector" ? "active" : ""}
                  onClick={() => setSettingsSection("connector")}
                >
                  Connectors
                </button>
                <button
                  className={settingsSection === "specialist" ? "active" : ""}
                  onClick={() => setSettingsSection("specialist")}
                >
                  Specialists
                </button>
                <span className="settings-menu-label workspace-label">Workspace</span>
                <button className={settingsSection === "runtime" ? "active" : ""} onClick={() => setSettingsSection("runtime")}>
                  Runtime
                </button>
              </aside>

              <div className="settings-content">
                {settingsSection !== "runtime" ? (
                  <CapabilitiesPanel
                    kind={settingsSection}
                    projectName={selectedProject?.name ?? ""}
                    items={capabilities}
                    loading={capabilitiesLoading}
                    saving={capabilitiesSaving}
                    dirty={capabilitiesDirty}
                    error={capabilitiesError}
                    onToggle={toggleCapability}
                    onSave={() => void saveCapabilities()}
                    onRefresh={() => void refreshCapabilities()}
                  />
                ) : (
                  <div className="settings-page runtime-settings-page">
                    {settingsError ? <p className="composer-error">{settingsError}</p> : null}
                    <section className="settings-card runtime-panel">
                      <h2>Runtime</h2>
                      <p>{runtime.summary}</p>
                      <small>{runtime.detail}</small>
                      <div className="runtime-actions">
                        <button className="secondary" onClick={() => void handleRuntimeAction()}>
                          {runtimeActionLabel(runtime.state)}
                        </button>
                        <button className="secondary" onClick={() => void refreshDiagnostics()}>
                          Refresh
                        </button>
                      </div>
                    </section>

                    <section className="settings-card">
                      <h2>Connection</h2>
                      <label className="settings-field">
                        <span>Target type</span>
                        <select
                          value={connectionForm.targetType}
                          onChange={(event) =>
                            setConnectionForm((current) => ({
                              ...current,
                              targetType: event.target.value === "remote" ? "remote" : "local",
                            }))
                          }
                        >
                          <option value="local">local</option>
                          <option value="remote">remote</option>
                        </select>
                      </label>
                      <label className="settings-field">
                        <span>Target name</span>
                        <input
                          value={connectionForm.targetName}
                          onChange={(event) =>
                            setConnectionForm((current) => ({ ...current, targetName: event.target.value }))
                          }
                        />
                      </label>
                      <label className="settings-field">
                        <span>Client API URL</span>
                        <input
                          value={connectionForm.clientApiBaseUrl}
                          onChange={(event) =>
                            setConnectionForm((current) => ({ ...current, clientApiBaseUrl: event.target.value }))
                          }
                        />
                      </label>
                      <button className="primary" disabled={savingConnection} onClick={() => void handleConnectionSave()}>
                        {savingConnection ? "Saving..." : "Save connection"}
                      </button>
                    </section>

                    {diagnostics ? (
                      <section className="settings-card">
                        <h2>Diagnostics</h2>
                        <dl className="diagnostics-list">
                          <div><dt>Mode</dt><dd>{diagnostics.mode}</dd></div>
                          <div><dt>Target</dt><dd>{diagnostics.target.name} ({diagnostics.target.type})</dd></div>
                          <div><dt>Client API</dt><dd>{diagnostics.clientApiBaseUrl}</dd></div>
                          <div><dt>Data config</dt><dd>{diagnostics.globalConfigPath}</dd></div>
                        </dl>
                      </section>
                    ) : null}
                  </div>
                )}
              </div>
            </div>
          </section>
        </main>
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
    </div>
  );
}
