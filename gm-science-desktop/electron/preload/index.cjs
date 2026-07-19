const { contextBridge, ipcRenderer } = require("electron");

const api = {
  bootstrap: () => ipcRenderer.invoke("ppx-client:bootstrap"),
  getDiagnostics: () => ipcRenderer.invoke("ppx-client:get-diagnostics"),
  saveConnectionSettings: (settings) => ipcRenderer.invoke("ppx-client:save-connection-settings", settings),
  runRuntimeCommand: (command) => ipcRenderer.invoke("ppx-client:runtime-command", command),
  listSessions: (agentId) => ipcRenderer.invoke("ppx-client:list-sessions", agentId),
  createSession: (agentId, projectId) => ipcRenderer.invoke("ppx-client:create-session", agentId, projectId),
  updateGmScienceSession: (sessionId, input) =>
    ipcRenderer.invoke("ppx-client:update-gm-science-session", sessionId, input),
  deleteGmScienceSession: (sessionId) =>
    ipcRenderer.invoke("ppx-client:delete-gm-science-session", sessionId),
  loadSession: (sessionId) => ipcRenderer.invoke("ppx-client:load-session", sessionId),
  sendMessage: (input) => ipcRenderer.invoke("ppx-client:send-message", input),
  listGmScienceProjects: () => ipcRenderer.invoke("ppx-client:list-gm-science-projects"),
  createGmScienceProject: (input) => ipcRenderer.invoke("ppx-client:create-gm-science-project", input),
  getGmScienceProject: (projectId) => ipcRenderer.invoke("ppx-client:get-gm-science-project", projectId),
  listGmScienceCapabilities: (projectId) =>
    ipcRenderer.invoke("ppx-client:list-gm-science-capabilities", projectId),
  createGmScienceSkill: (input) => ipcRenderer.invoke("ppx-client:create-gm-science-skill", input),
  createGmScienceConnector: (input) => ipcRenderer.invoke("ppx-client:create-gm-science-connector", input),
  createGmScienceSpecialist: (input) => ipcRenderer.invoke("ppx-client:create-gm-science-specialist", input),
  importGmScienceSkill: (input) => ipcRenderer.invoke("ppx-client:import-gm-science-skill", input),
  listGmScienceSkillDrafts: () => ipcRenderer.invoke("ppx-client:list-gm-science-skill-drafts"),
  saveGmScienceSkillDraft: (input) => ipcRenderer.invoke("ppx-client:save-gm-science-skill-draft", input),
  publishGmScienceSkillDraft: (draftId) =>
    ipcRenderer.invoke("ppx-client:publish-gm-science-skill-draft", draftId),
  deleteGmScienceSkillDraft: (draftId) =>
    ipcRenderer.invoke("ppx-client:delete-gm-science-skill-draft", draftId),
  selectGmScienceSkillSource: (mode) => ipcRenderer.invoke("ppx-client:select-gm-science-skill-source", mode),
  getGmScienceCapabilityDefinition: (kind, capabilityId) =>
    ipcRenderer.invoke("ppx-client:get-gm-science-capability-definition", kind, capabilityId),
  updateGmScienceCapability: (kind, capabilityId, input) =>
    ipcRenderer.invoke("ppx-client:update-gm-science-capability", kind, capabilityId, input),
  deleteGmScienceCapability: (kind, capabilityId) =>
    ipcRenderer.invoke("ppx-client:delete-gm-science-capability", kind, capabilityId),
  updateGmScienceProjectCapabilities: (projectId, input) =>
    ipcRenderer.invoke("ppx-client:update-gm-science-project-capabilities", projectId, input),
  getGmScienceSettings: () => ipcRenderer.invoke("ppx-client:get-gm-science-settings"),
  updateGmScienceSettings: (input) => ipcRenderer.invoke("ppx-client:update-gm-science-settings", input),
  checkGmScienceComputeTarget: (targetId) => ipcRenderer.invoke("ppx-client:check-gm-science-compute-target", targetId),
  getGmScienceStorage: () => ipcRenderer.invoke("ppx-client:get-gm-science-storage"),
  changeGmScienceDataLocation: () => ipcRenderer.invoke("ppx-client:change-gm-science-data-location"),
  getGmScienceUsage: (window) => ipcRenderer.invoke("ppx-client:get-gm-science-usage", window),
  getGmScienceMemory: (projectId) => ipcRenderer.invoke("ppx-client:get-gm-science-memory", projectId),
  createGmScienceMemoryNote: (projectId, input) =>
    ipcRenderer.invoke("ppx-client:create-gm-science-memory-note", projectId, input),
  updateGmScienceMemoryNote: (projectId, noteId, input) =>
    ipcRenderer.invoke("ppx-client:update-gm-science-memory-note", projectId, noteId, input),
  deleteGmScienceMemoryNote: (projectId, noteId) =>
    ipcRenderer.invoke("ppx-client:delete-gm-science-memory-note", projectId, noteId),
  clearGmScienceMemory: (projectId, scope) =>
    ipcRenderer.invoke("ppx-client:clear-gm-science-memory", projectId, scope),
  reviewGmScienceMemoryCandidate: (projectId, candidateId, decision) =>
    ipcRenderer.invoke(
      "ppx-client:review-gm-science-memory-candidate",
      projectId,
      candidateId,
      decision,
    ),
  getGmScienceSessionPolicy: (sessionId) =>
    ipcRenderer.invoke("ppx-client:get-gm-science-session-policy", sessionId),
  updateGmScienceSessionPolicy: (sessionId, input) =>
    ipcRenderer.invoke("ppx-client:update-gm-science-session-policy", sessionId, input),
  getGmScienceProjectSessionPolicyDefaults: (projectId) =>
    ipcRenderer.invoke("ppx-client:get-gm-science-project-session-policy-defaults", projectId),
  updateGmScienceProjectSessionPolicyDefaults: (projectId, input) =>
    ipcRenderer.invoke("ppx-client:update-gm-science-project-session-policy-defaults", projectId, input),
  listGmScienceArtifacts: (projectId) => ipcRenderer.invoke("ppx-client:list-gm-science-artifacts", projectId),
  listGmScienceResources: (projectId, query) =>
    ipcRenderer.invoke("ppx-client:list-gm-science-resources", projectId, query),
  listGmScienceProjectSources: (projectId) =>
    ipcRenderer.invoke("ppx-client:list-gm-science-project-sources", projectId),
  selectGmScienceProjectSource: (kind) =>
    ipcRenderer.invoke("ppx-client:select-gm-science-project-source", kind),
  importGmScienceProjectSource: (projectId, input) =>
    ipcRenderer.invoke("ppx-client:import-gm-science-project-source", projectId, input),
  deleteGmScienceProjectSource: (projectId, sourceId) =>
    ipcRenderer.invoke("ppx-client:delete-gm-science-project-source", projectId, sourceId),
  downloadGmScienceResource: (projectId, resourceId) =>
    ipcRenderer.invoke("ppx-client:download-gm-science-resource", projectId, resourceId),
  revealGmScienceResource: (projectId, resourceId) =>
    ipcRenderer.invoke("ppx-client:reveal-gm-science-resource", projectId, resourceId),
  getGmScienceResourceDetail: (projectId, resourceId) =>
    ipcRenderer.invoke("ppx-client:get-gm-science-resource-detail", projectId, resourceId),
  createGmScienceArtifact: (projectId, input) =>
    ipcRenderer.invoke("ppx-client:create-gm-science-artifact", projectId, input),
  updateGmScienceArtifact: (projectId, artifactId, input) =>
    ipcRenderer.invoke("ppx-client:update-gm-science-artifact", projectId, artifactId, input),
  deleteGmScienceArtifact: (projectId, artifactId) =>
    ipcRenderer.invoke("ppx-client:delete-gm-science-artifact", projectId, artifactId),
  listGmScienceRuns: (projectId) => ipcRenderer.invoke("ppx-client:list-gm-science-runs", projectId),
  getGmScienceRun: (projectId, taskId) =>
    ipcRenderer.invoke("ppx-client:get-gm-science-run", projectId, taskId),
  createGmSciencePythonRun: (projectId, input) =>
    ipcRenderer.invoke("ppx-client:create-gm-science-python-run", projectId, input),
  cancelGmScienceRun: (projectId, taskId) =>
    ipcRenderer.invoke("ppx-client:cancel-gm-science-run", projectId, taskId),
  retryGmScienceRun: (projectId, taskId) =>
    ipcRenderer.invoke("ppx-client:retry-gm-science-run", projectId, taskId),
  selectGmScienceDatasetFile: () => ipcRenderer.invoke("ppx-client:select-gm-science-dataset-file"),
  listGmScienceDatasets: (projectId) => ipcRenderer.invoke("ppx-client:list-gm-science-datasets", projectId),
  getGmScienceDataset: (projectId, artifactId) =>
    ipcRenderer.invoke("ppx-client:get-gm-science-dataset", projectId, artifactId),
  importGmScienceDataset: (projectId, input) =>
    ipcRenderer.invoke("ppx-client:import-gm-science-dataset", projectId, input),
  listGmScienceAnalyses: (projectId) => ipcRenderer.invoke("ppx-client:list-gm-science-analyses", projectId),
  getGmScienceAnalysis: (projectId, analysisId) =>
    ipcRenderer.invoke("ppx-client:get-gm-science-analysis", projectId, analysisId),
  createGmScienceAnalysis: (projectId, input) =>
    ipcRenderer.invoke("ppx-client:create-gm-science-analysis", projectId, input),
  runGmScienceAnalysis: (projectId, analysisId) =>
    ipcRenderer.invoke("ppx-client:run-gm-science-analysis", projectId, analysisId),
  onRunEvent: (listener) => {
    const wrapped = (_event, payload) => listener(payload);
    ipcRenderer.on("ppx-client:run-event", wrapped);
    return () => {
      ipcRenderer.removeListener("ppx-client:run-event", wrapped);
    };
  },
};

contextBridge.exposeInMainWorld("ppxClient", api);
