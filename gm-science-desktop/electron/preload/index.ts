import { contextBridge, ipcRenderer } from "electron";
import type {
  ConnectionSettings,
  CreateGmScienceAnalysisInput,
  CreateGmScienceArtifactInput,
  CreateGmSciencePythonRunInput,
  CreateGmScienceProjectInput,
  CreateGmScienceMemoryNoteInput,
  CreateGmScienceConnectorInput,
  CreateGmScienceSkillInput,
  CreateGmScienceSpecialistInput,
  GmScienceCapabilityKind,
  GmScienceSkillSourcePickerMode,
  ImportGmScienceSkillInput,
  ImportGmScienceDatasetInput,
  PpxClientApi,
  RunEvent,
  RuntimeCommand,
  SendMessageInput,
  UpdateGmScienceCapabilitiesInput,
  UpdateGmScienceArtifactInput,
  UpdateGmScienceSessionPolicyInput,
  UpdateGmScienceSettingsInput,
  UpdateGmScienceMemoryNoteInput,
  GmScienceMemoryScope,
  GmScienceUsageWindow,
} from "../../app/src/types";

const api: PpxClientApi = {
  bootstrap: () => ipcRenderer.invoke("ppx-client:bootstrap"),
  getDiagnostics: () => ipcRenderer.invoke("ppx-client:get-diagnostics"),
  saveConnectionSettings: (settings: ConnectionSettings) => ipcRenderer.invoke("ppx-client:save-connection-settings", settings),
  runRuntimeCommand: (command: RuntimeCommand) => ipcRenderer.invoke("ppx-client:runtime-command", command),
  listSessions: (agentId: string) => ipcRenderer.invoke("ppx-client:list-sessions", agentId),
  createSession: (agentId: string, projectId?: string) =>
    ipcRenderer.invoke("ppx-client:create-session", agentId, projectId),
  updateGmScienceSession: (sessionId: string, input: { title: string }) =>
    ipcRenderer.invoke("ppx-client:update-gm-science-session", sessionId, input),
  deleteGmScienceSession: (sessionId: string) =>
    ipcRenderer.invoke("ppx-client:delete-gm-science-session", sessionId),
  loadSession: (sessionId: string) => ipcRenderer.invoke("ppx-client:load-session", sessionId),
  sendMessage: (input: SendMessageInput) => ipcRenderer.invoke("ppx-client:send-message", input),
  listGmScienceProjects: () => ipcRenderer.invoke("ppx-client:list-gm-science-projects"),
  createGmScienceProject: (input: CreateGmScienceProjectInput) =>
    ipcRenderer.invoke("ppx-client:create-gm-science-project", input),
  getGmScienceProject: (projectId: string) => ipcRenderer.invoke("ppx-client:get-gm-science-project", projectId),
  listGmScienceCapabilities: (projectId?: string) =>
    ipcRenderer.invoke("ppx-client:list-gm-science-capabilities", projectId),
  createGmScienceSkill: (input: CreateGmScienceSkillInput) =>
    ipcRenderer.invoke("ppx-client:create-gm-science-skill", input),
  createGmScienceConnector: (input: CreateGmScienceConnectorInput) =>
    ipcRenderer.invoke("ppx-client:create-gm-science-connector", input),
  createGmScienceSpecialist: (input: CreateGmScienceSpecialistInput) =>
    ipcRenderer.invoke("ppx-client:create-gm-science-specialist", input),
  importGmScienceSkill: (input: ImportGmScienceSkillInput) =>
    ipcRenderer.invoke("ppx-client:import-gm-science-skill", input),
  listGmScienceSkillDrafts: () => ipcRenderer.invoke("ppx-client:list-gm-science-skill-drafts"),
  saveGmScienceSkillDraft: (input: CreateGmScienceSkillInput) =>
    ipcRenderer.invoke("ppx-client:save-gm-science-skill-draft", input),
  publishGmScienceSkillDraft: (draftId: string) =>
    ipcRenderer.invoke("ppx-client:publish-gm-science-skill-draft", draftId),
  deleteGmScienceSkillDraft: (draftId: string) =>
    ipcRenderer.invoke("ppx-client:delete-gm-science-skill-draft", draftId),
  selectGmScienceSkillSource: (mode: GmScienceSkillSourcePickerMode) =>
    ipcRenderer.invoke("ppx-client:select-gm-science-skill-source", mode),
  getGmScienceCapabilityDefinition: (kind: GmScienceCapabilityKind, capabilityId: string) =>
    ipcRenderer.invoke("ppx-client:get-gm-science-capability-definition", kind, capabilityId),
  updateGmScienceCapability: (
    kind: GmScienceCapabilityKind,
    capabilityId: string,
    input: CreateGmScienceSkillInput | CreateGmScienceConnectorInput | CreateGmScienceSpecialistInput,
  ) => ipcRenderer.invoke("ppx-client:update-gm-science-capability", kind, capabilityId, input),
  deleteGmScienceCapability: (kind: GmScienceCapabilityKind, capabilityId: string) =>
    ipcRenderer.invoke("ppx-client:delete-gm-science-capability", kind, capabilityId),
  updateGmScienceProjectCapabilities: (projectId: string, input: UpdateGmScienceCapabilitiesInput) =>
    ipcRenderer.invoke("ppx-client:update-gm-science-project-capabilities", projectId, input),
  getGmScienceSettings: () => ipcRenderer.invoke("ppx-client:get-gm-science-settings"),
  updateGmScienceSettings: (input: UpdateGmScienceSettingsInput) =>
    ipcRenderer.invoke("ppx-client:update-gm-science-settings", input),
  checkGmScienceComputeTarget: (targetId: string) =>
    ipcRenderer.invoke("ppx-client:check-gm-science-compute-target", targetId),
  getGmScienceStorage: () => ipcRenderer.invoke("ppx-client:get-gm-science-storage"),
  changeGmScienceDataLocation: () => ipcRenderer.invoke("ppx-client:change-gm-science-data-location"),
  getGmScienceUsage: (window: GmScienceUsageWindow) =>
    ipcRenderer.invoke("ppx-client:get-gm-science-usage", window),
  getGmScienceMemory: (projectId: string) =>
    ipcRenderer.invoke("ppx-client:get-gm-science-memory", projectId),
  createGmScienceMemoryNote: (projectId: string, input: CreateGmScienceMemoryNoteInput) =>
    ipcRenderer.invoke("ppx-client:create-gm-science-memory-note", projectId, input),
  updateGmScienceMemoryNote: (projectId: string, noteId: string, input: UpdateGmScienceMemoryNoteInput) =>
    ipcRenderer.invoke("ppx-client:update-gm-science-memory-note", projectId, noteId, input),
  deleteGmScienceMemoryNote: (projectId: string, noteId: string) =>
    ipcRenderer.invoke("ppx-client:delete-gm-science-memory-note", projectId, noteId),
  clearGmScienceMemory: (projectId: string, scope: GmScienceMemoryScope) =>
    ipcRenderer.invoke("ppx-client:clear-gm-science-memory", projectId, scope),
  reviewGmScienceMemoryCandidate: (
    projectId: string,
    candidateId: string,
    decision: "approve" | "reject",
  ) => ipcRenderer.invoke(
    "ppx-client:review-gm-science-memory-candidate",
    projectId,
    candidateId,
    decision,
  ),
  getGmScienceSessionPolicy: (sessionId: string) =>
    ipcRenderer.invoke("ppx-client:get-gm-science-session-policy", sessionId),
  updateGmScienceSessionPolicy: (sessionId: string, input: UpdateGmScienceSessionPolicyInput) =>
    ipcRenderer.invoke("ppx-client:update-gm-science-session-policy", sessionId, input),
  getGmScienceProjectSessionPolicyDefaults: (projectId: string) =>
    ipcRenderer.invoke("ppx-client:get-gm-science-project-session-policy-defaults", projectId),
  updateGmScienceProjectSessionPolicyDefaults: (projectId: string, input: UpdateGmScienceSessionPolicyInput) =>
    ipcRenderer.invoke("ppx-client:update-gm-science-project-session-policy-defaults", projectId, input),
  listGmScienceArtifacts: (projectId: string) => ipcRenderer.invoke("ppx-client:list-gm-science-artifacts", projectId),
  listGmScienceResources: (projectId: string, query?: string) =>
    ipcRenderer.invoke("ppx-client:list-gm-science-resources", projectId, query),
  listGmScienceProjectSources: (projectId: string) =>
    ipcRenderer.invoke("ppx-client:list-gm-science-project-sources", projectId),
  selectGmScienceProjectSource: (kind: "file" | "folder") =>
    ipcRenderer.invoke("ppx-client:select-gm-science-project-source", kind),
  importGmScienceProjectSource: (
    projectId: string,
    input: { sourcePath: string; kind: "file" | "folder" },
  ) => ipcRenderer.invoke("ppx-client:import-gm-science-project-source", projectId, input),
  deleteGmScienceProjectSource: (projectId: string, sourceId: string) =>
    ipcRenderer.invoke("ppx-client:delete-gm-science-project-source", projectId, sourceId),
  downloadGmScienceResource: (projectId: string, resourceId: string) =>
    ipcRenderer.invoke("ppx-client:download-gm-science-resource", projectId, resourceId),
  revealGmScienceResource: (projectId: string, resourceId: string) =>
    ipcRenderer.invoke("ppx-client:reveal-gm-science-resource", projectId, resourceId),
  getGmScienceResourceDetail: (projectId: string, resourceId: string) =>
    ipcRenderer.invoke("ppx-client:get-gm-science-resource-detail", projectId, resourceId),
  createGmScienceArtifact: (projectId: string, input: CreateGmScienceArtifactInput) =>
    ipcRenderer.invoke("ppx-client:create-gm-science-artifact", projectId, input),
  updateGmScienceArtifact: (projectId: string, artifactId: string, input: UpdateGmScienceArtifactInput) =>
    ipcRenderer.invoke("ppx-client:update-gm-science-artifact", projectId, artifactId, input),
  deleteGmScienceArtifact: (projectId: string, artifactId: string) =>
    ipcRenderer.invoke("ppx-client:delete-gm-science-artifact", projectId, artifactId),
  listGmScienceRuns: (projectId: string) => ipcRenderer.invoke("ppx-client:list-gm-science-runs", projectId),
  getGmScienceRun: (projectId: string, taskId: string) =>
    ipcRenderer.invoke("ppx-client:get-gm-science-run", projectId, taskId),
  createGmSciencePythonRun: (projectId: string, input: CreateGmSciencePythonRunInput) =>
    ipcRenderer.invoke("ppx-client:create-gm-science-python-run", projectId, input),
  cancelGmScienceRun: (projectId: string, taskId: string) =>
    ipcRenderer.invoke("ppx-client:cancel-gm-science-run", projectId, taskId),
  retryGmScienceRun: (projectId: string, taskId: string) =>
    ipcRenderer.invoke("ppx-client:retry-gm-science-run", projectId, taskId),
  selectGmScienceDatasetFile: () => ipcRenderer.invoke("ppx-client:select-gm-science-dataset-file"),
  listGmScienceDatasets: (projectId: string) => ipcRenderer.invoke("ppx-client:list-gm-science-datasets", projectId),
  getGmScienceDataset: (projectId: string, artifactId: string) =>
    ipcRenderer.invoke("ppx-client:get-gm-science-dataset", projectId, artifactId),
  importGmScienceDataset: (projectId: string, input: ImportGmScienceDatasetInput) =>
    ipcRenderer.invoke("ppx-client:import-gm-science-dataset", projectId, input),
  listGmScienceAnalyses: (projectId: string) => ipcRenderer.invoke("ppx-client:list-gm-science-analyses", projectId),
  getGmScienceAnalysis: (projectId: string, analysisId: string) =>
    ipcRenderer.invoke("ppx-client:get-gm-science-analysis", projectId, analysisId),
  createGmScienceAnalysis: (projectId: string, input: CreateGmScienceAnalysisInput) =>
    ipcRenderer.invoke("ppx-client:create-gm-science-analysis", projectId, input),
  runGmScienceAnalysis: (projectId: string, analysisId: string) =>
    ipcRenderer.invoke("ppx-client:run-gm-science-analysis", projectId, analysisId),
  onRunEvent: (listener: (event: RunEvent) => void) => {
    const wrapped = (_event: unknown, payload: RunEvent) => listener(payload);
    ipcRenderer.on("ppx-client:run-event", wrapped);
    return () => {
      ipcRenderer.removeListener("ppx-client:run-event", wrapped);
    };
  },
};

contextBridge.exposeInMainWorld("ppxClient", api);
