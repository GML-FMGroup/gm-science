const { contextBridge, ipcRenderer } = require("electron");

const api = {
  bootstrap: () => ipcRenderer.invoke("ppx-client:bootstrap"),
  getDiagnostics: () => ipcRenderer.invoke("ppx-client:get-diagnostics"),
  saveConnectionSettings: (settings) => ipcRenderer.invoke("ppx-client:save-connection-settings", settings),
  runRuntimeCommand: (command) => ipcRenderer.invoke("ppx-client:runtime-command", command),
  listSessions: (agentId) => ipcRenderer.invoke("ppx-client:list-sessions", agentId),
  createSession: (agentId, projectId) => ipcRenderer.invoke("ppx-client:create-session", agentId, projectId),
  loadSession: (sessionId) => ipcRenderer.invoke("ppx-client:load-session", sessionId),
  sendMessage: (input) => ipcRenderer.invoke("ppx-client:send-message", input),
  listGmScienceProjects: () => ipcRenderer.invoke("ppx-client:list-gm-science-projects"),
  createGmScienceProject: (input) => ipcRenderer.invoke("ppx-client:create-gm-science-project", input),
  getGmScienceProject: (projectId) => ipcRenderer.invoke("ppx-client:get-gm-science-project", projectId),
  listGmScienceCapabilities: (projectId) =>
    ipcRenderer.invoke("ppx-client:list-gm-science-capabilities", projectId),
  updateGmScienceProjectCapabilities: (projectId, input) =>
    ipcRenderer.invoke("ppx-client:update-gm-science-project-capabilities", projectId, input),
  listGmScienceArtifacts: (projectId) => ipcRenderer.invoke("ppx-client:list-gm-science-artifacts", projectId),
  createGmScienceArtifact: (projectId, input) =>
    ipcRenderer.invoke("ppx-client:create-gm-science-artifact", projectId, input),
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
