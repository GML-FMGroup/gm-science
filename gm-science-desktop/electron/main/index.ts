import { app, BrowserWindow, dialog, ipcMain } from "electron";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type {
  ConnectionSettings,
  CreateGmScienceAnalysisInput,
  CreateGmScienceArtifactInput,
  CreateGmSciencePythonRunInput,
  CreateGmScienceProjectInput,
  CreateGmScienceMemoryNoteInput,
  ImportGmScienceDatasetInput,
  RuntimeCommand,
  SendMessageInput,
  UpdateGmScienceCapabilitiesInput,
  UpdateGmScienceSessionPolicyInput,
  UpdateGmScienceSettingsInput,
  UpdateGmScienceMemoryNoteInput,
  GmScienceMemoryScope,
  GmScienceUsageWindow,
} from "../../app/src/types";
import { OpenPpxLocalAdapter } from "./openppx-local-adapter";

let mainWindow: BrowserWindow | null = null;
let unsubscribeRunEvents: (() => void) | null = null;
let adapter: OpenPpxLocalAdapter | null = null;
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function connectionSettingsPath(): string {
  return path.join(app.getPath("userData"), "connection-settings.json");
}

function readConnectionSettings(): ConnectionSettings | null {
  try {
    const filePath = connectionSettingsPath();
    if (!fs.existsSync(filePath)) {
      return null;
    }
    return JSON.parse(fs.readFileSync(filePath, "utf-8")) as ConnectionSettings;
  } catch {
    return null;
  }
}

function writeConnectionSettings(settings: ConnectionSettings): void {
  const filePath = connectionSettingsPath();
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(settings, null, 2), "utf-8");
}

function createWindow(): void {
  const preloadPath = process.env.VITE_DEV_SERVER_URL
    ? path.resolve(process.cwd(), "electron/preload/index.cjs")
    : path.join(__dirname, "../preload/index.cjs");
  const isMac = process.platform === "darwin";

  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1100,
    minHeight: 760,
    backgroundColor: "#f4efe5",
    title: "gm-science",
    titleBarStyle: isMac ? "hiddenInset" : "default",
    trafficLightPosition: isMac ? { x: 22, y: 22 } : undefined,
    webPreferences: {
      preload: preloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  adapter = new OpenPpxLocalAdapter(readConnectionSettings() ?? undefined);
  unsubscribeRunEvents = adapter.onRunEvent((event) => {
    mainWindow?.webContents.send("ppx-client:run-event", event);
  });

  if (process.env.VITE_DEV_SERVER_URL) {
    void mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL);
  } else {
    void mainWindow.loadFile(path.join(__dirname, "../../index.html"));
  }
}

app.whenReady().then(() => {
  ipcMain.handle("ppx-client:bootstrap", async () => adapter!.bootstrap());
  ipcMain.handle("ppx-client:get-diagnostics", async () => adapter!.getDiagnostics());
  ipcMain.handle("ppx-client:save-connection-settings", async (_event, settings: ConnectionSettings) => {
    writeConnectionSettings(settings);
    adapter!.applyConnectionSettings(settings);
    return adapter!.getDiagnostics();
  });
  ipcMain.handle("ppx-client:runtime-command", async (_event, command: RuntimeCommand) =>
    adapter!.runRuntimeCommand(command),
  );
  ipcMain.handle("ppx-client:list-sessions", async (_event, agentId: string) => adapter!.listSessions(agentId));
  ipcMain.handle("ppx-client:create-session", async (_event, agentId: string, projectId?: string) =>
    adapter!.createSession(agentId, projectId),
  );
  ipcMain.handle("ppx-client:load-session", async (_event, sessionId: string) => adapter!.loadSession(sessionId));
  ipcMain.handle("ppx-client:send-message", async (_event, input: SendMessageInput) => adapter!.sendMessage(input));
  ipcMain.handle("ppx-client:list-gm-science-projects", async () => adapter!.listGmScienceProjects());
  ipcMain.handle("ppx-client:create-gm-science-project", async (_event, input: CreateGmScienceProjectInput) =>
    adapter!.createGmScienceProject(input),
  );
  ipcMain.handle("ppx-client:get-gm-science-project", async (_event, projectId: string) =>
    adapter!.getGmScienceProject(projectId),
  );
  ipcMain.handle("ppx-client:list-gm-science-capabilities", async (_event, projectId?: string) =>
    adapter!.listGmScienceCapabilities(projectId),
  );
  ipcMain.handle(
    "ppx-client:update-gm-science-project-capabilities",
    async (_event, projectId: string, input: UpdateGmScienceCapabilitiesInput) =>
      adapter!.updateGmScienceProjectCapabilities(projectId, input),
  );
  ipcMain.handle("ppx-client:get-gm-science-settings", async () => adapter!.getGmScienceSettings());
  ipcMain.handle(
    "ppx-client:update-gm-science-settings",
    async (_event, input: UpdateGmScienceSettingsInput) => adapter!.updateGmScienceSettings(input),
  );
  ipcMain.handle(
    "ppx-client:check-gm-science-compute-target",
    async (_event, targetId: string) => adapter!.checkGmScienceComputeTarget(targetId),
  );
  ipcMain.handle("ppx-client:get-gm-science-storage", async () => adapter!.getGmScienceStorage());
  ipcMain.handle(
    "ppx-client:get-gm-science-usage",
    async (_event, window: GmScienceUsageWindow) => adapter!.getGmScienceUsage(window),
  );
  ipcMain.handle("ppx-client:get-gm-science-memory", async (_event, projectId: string) =>
    adapter!.getGmScienceMemory(projectId),
  );
  ipcMain.handle(
    "ppx-client:create-gm-science-memory-note",
    async (_event, projectId: string, input: CreateGmScienceMemoryNoteInput) =>
      adapter!.createGmScienceMemoryNote(projectId, input),
  );
  ipcMain.handle(
    "ppx-client:update-gm-science-memory-note",
    async (_event, projectId: string, noteId: string, input: UpdateGmScienceMemoryNoteInput) =>
      adapter!.updateGmScienceMemoryNote(projectId, noteId, input),
  );
  ipcMain.handle(
    "ppx-client:delete-gm-science-memory-note",
    async (_event, projectId: string, noteId: string) =>
      adapter!.deleteGmScienceMemoryNote(projectId, noteId),
  );
  ipcMain.handle(
    "ppx-client:clear-gm-science-memory",
    async (_event, projectId: string, scope: GmScienceMemoryScope) =>
      adapter!.clearGmScienceMemory(projectId, scope),
  );
  ipcMain.handle(
    "ppx-client:review-gm-science-memory-candidate",
    async (_event, projectId: string, candidateId: string, decision: "approve" | "reject") =>
      adapter!.reviewGmScienceMemoryCandidate(projectId, candidateId, decision),
  );
  ipcMain.handle("ppx-client:get-gm-science-session-policy", async (_event, sessionId: string) =>
    adapter!.getGmScienceSessionPolicy(sessionId),
  );
  ipcMain.handle(
    "ppx-client:update-gm-science-session-policy",
    async (_event, sessionId: string, input: UpdateGmScienceSessionPolicyInput) =>
      adapter!.updateGmScienceSessionPolicy(sessionId, input),
  );
  ipcMain.handle("ppx-client:list-gm-science-artifacts", async (_event, projectId: string) =>
    adapter!.listGmScienceArtifacts(projectId),
  );
  ipcMain.handle(
    "ppx-client:list-gm-science-resources",
    async (_event, projectId: string, query?: string) => adapter!.listGmScienceResources(projectId, query),
  );
  ipcMain.handle(
    "ppx-client:get-gm-science-resource-detail",
    async (_event, projectId: string, resourceId: string) =>
      adapter!.getGmScienceResourceDetail(projectId, resourceId),
  );
  ipcMain.handle(
    "ppx-client:create-gm-science-artifact",
    async (_event, projectId: string, input: CreateGmScienceArtifactInput) =>
      adapter!.createGmScienceArtifact(projectId, input),
  );
  ipcMain.handle("ppx-client:list-gm-science-runs", async (_event, projectId: string) =>
    adapter!.listGmScienceRuns(projectId),
  );
  ipcMain.handle("ppx-client:get-gm-science-run", async (_event, projectId: string, taskId: string) =>
    adapter!.getGmScienceRun(projectId, taskId),
  );
  ipcMain.handle(
    "ppx-client:create-gm-science-python-run",
    async (_event, projectId: string, input: CreateGmSciencePythonRunInput) =>
      adapter!.createGmSciencePythonRun(projectId, input),
  );
  ipcMain.handle("ppx-client:cancel-gm-science-run", async (_event, projectId: string, taskId: string) =>
    adapter!.cancelGmScienceRun(projectId, taskId),
  );
  ipcMain.handle("ppx-client:retry-gm-science-run", async (_event, projectId: string, taskId: string) =>
    adapter!.retryGmScienceRun(projectId, taskId),
  );
  ipcMain.handle("ppx-client:select-gm-science-dataset-file", async () => {
    const result = await dialog.showOpenDialog(mainWindow!, {
      title: "Import dataset",
      properties: ["openFile"],
      filters: [
        { name: "Tabular datasets", extensions: ["csv", "tsv", "json", "jsonl", "ndjson"] },
        { name: "All files", extensions: ["*"] },
      ],
    });
    if (result.canceled || !result.filePaths[0]) {
      return null;
    }
    return { path: result.filePaths[0], name: path.basename(result.filePaths[0]) };
  });
  ipcMain.handle("ppx-client:list-gm-science-datasets", async (_event, projectId: string) =>
    adapter!.listGmScienceDatasets(projectId),
  );
  ipcMain.handle(
    "ppx-client:get-gm-science-dataset",
    async (_event, projectId: string, artifactId: string) => adapter!.getGmScienceDataset(projectId, artifactId),
  );
  ipcMain.handle(
    "ppx-client:import-gm-science-dataset",
    async (_event, projectId: string, input: ImportGmScienceDatasetInput) =>
      adapter!.importGmScienceDataset(projectId, input),
  );
  ipcMain.handle("ppx-client:list-gm-science-analyses", async (_event, projectId: string) =>
    adapter!.listGmScienceAnalyses(projectId),
  );
  ipcMain.handle(
    "ppx-client:get-gm-science-analysis",
    async (_event, projectId: string, analysisId: string) => adapter!.getGmScienceAnalysis(projectId, analysisId),
  );
  ipcMain.handle(
    "ppx-client:create-gm-science-analysis",
    async (_event, projectId: string, input: CreateGmScienceAnalysisInput) =>
      adapter!.createGmScienceAnalysis(projectId, input),
  );
  ipcMain.handle(
    "ppx-client:run-gm-science-analysis",
    async (_event, projectId: string, analysisId: string) => adapter!.runGmScienceAnalysis(projectId, analysisId),
  );

  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  unsubscribeRunEvents?.();
  unsubscribeRunEvents = null;
  adapter?.dispose();
  adapter = null;
  if (process.platform !== "darwin") {
    app.quit();
  }
});
