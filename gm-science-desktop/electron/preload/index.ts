import { contextBridge, ipcRenderer } from "electron";
import type {
  ConnectionSettings,
  CreateGmScienceArtifactInput,
  CreateGmSciencePythonRunInput,
  CreateGmScienceProjectInput,
  PpxClientApi,
  RunEvent,
  RuntimeCommand,
  SendMessageInput,
  UpdateGmScienceCapabilitiesInput,
} from "../../app/src/types";

const api: PpxClientApi = {
  bootstrap: () => ipcRenderer.invoke("ppx-client:bootstrap"),
  getDiagnostics: () => ipcRenderer.invoke("ppx-client:get-diagnostics"),
  saveConnectionSettings: (settings: ConnectionSettings) => ipcRenderer.invoke("ppx-client:save-connection-settings", settings),
  runRuntimeCommand: (command: RuntimeCommand) => ipcRenderer.invoke("ppx-client:runtime-command", command),
  listSessions: (agentId: string) => ipcRenderer.invoke("ppx-client:list-sessions", agentId),
  createSession: (agentId: string, projectId?: string) =>
    ipcRenderer.invoke("ppx-client:create-session", agentId, projectId),
  loadSession: (sessionId: string) => ipcRenderer.invoke("ppx-client:load-session", sessionId),
  sendMessage: (input: SendMessageInput) => ipcRenderer.invoke("ppx-client:send-message", input),
  listGmScienceProjects: () => ipcRenderer.invoke("ppx-client:list-gm-science-projects"),
  createGmScienceProject: (input: CreateGmScienceProjectInput) =>
    ipcRenderer.invoke("ppx-client:create-gm-science-project", input),
  getGmScienceProject: (projectId: string) => ipcRenderer.invoke("ppx-client:get-gm-science-project", projectId),
  listGmScienceCapabilities: (projectId?: string) =>
    ipcRenderer.invoke("ppx-client:list-gm-science-capabilities", projectId),
  updateGmScienceProjectCapabilities: (projectId: string, input: UpdateGmScienceCapabilitiesInput) =>
    ipcRenderer.invoke("ppx-client:update-gm-science-project-capabilities", projectId, input),
  listGmScienceArtifacts: (projectId: string) => ipcRenderer.invoke("ppx-client:list-gm-science-artifacts", projectId),
  createGmScienceArtifact: (projectId: string, input: CreateGmScienceArtifactInput) =>
    ipcRenderer.invoke("ppx-client:create-gm-science-artifact", projectId, input),
  listGmScienceRuns: (projectId: string) => ipcRenderer.invoke("ppx-client:list-gm-science-runs", projectId),
  getGmScienceRun: (projectId: string, taskId: string) =>
    ipcRenderer.invoke("ppx-client:get-gm-science-run", projectId, taskId),
  createGmSciencePythonRun: (projectId: string, input: CreateGmSciencePythonRunInput) =>
    ipcRenderer.invoke("ppx-client:create-gm-science-python-run", projectId, input),
  cancelGmScienceRun: (projectId: string, taskId: string) =>
    ipcRenderer.invoke("ppx-client:cancel-gm-science-run", projectId, taskId),
  retryGmScienceRun: (projectId: string, taskId: string) =>
    ipcRenderer.invoke("ppx-client:retry-gm-science-run", projectId, taskId),
  onRunEvent: (listener: (event: RunEvent) => void) => {
    const wrapped = (_event: unknown, payload: RunEvent) => listener(payload);
    ipcRenderer.on("ppx-client:run-event", wrapped);
    return () => {
      ipcRenderer.removeListener("ppx-client:run-event", wrapped);
    };
  },
};

contextBridge.exposeInMainWorld("ppxClient", api);
