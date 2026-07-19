import { app, BrowserWindow, dialog, ipcMain, shell } from "electron";
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
  CreateGmScienceConnectorInput,
  CreateGmScienceSkillInput,
  CreateGmScienceSpecialistInput,
  GmScienceCapabilityKind,
  GmScienceSkillSourcePickerMode,
  ImportGmScienceSkillInput,
  ImportGmScienceDatasetInput,
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
import { OpenPpxLocalAdapter } from "./openppx-local-adapter";
import { resolveGmScienceDataRoot } from "./gm-science-adapter-helpers";
import {
  assertSafeDataMigration,
  copyDataRootAtomically,
  readPersistedDataLocation,
  writePersistedDataLocation,
} from "./data-location";

let mainWindow: BrowserWindow | null = null;
let unsubscribeRunEvents: (() => void) | null = null;
let adapter: OpenPpxLocalAdapter | null = null;
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function connectionSettingsPath(): string {
  return path.join(app.getPath("userData"), "connection-settings.json");
}

function dataLocationSettingsPath(): string {
  return path.join(app.getPath("userData"), "data-location.json");
}

function applyPersistedDataLocation(): void {
  const persisted = readPersistedDataLocation(dataLocationSettingsPath());
  const launcherDefault = process.env.GM_SCIENCE_DATA_DIR_SOURCE === "launcher-default";
  const hasExplicitEnvironment = Boolean(
    process.env.GM_SCIENCE_DATA_DIR?.trim() || process.env.OPENPPX_DATA_DIR?.trim(),
  );
  if (!persisted || (hasExplicitEnvironment && !launcherDefault)) {
    return;
  }
  process.env.GM_SCIENCE_DATA_DIR = persisted;
  process.env.OPENPPX_DATA_DIR = persisted;
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

async function resolveProjectResourcePath(projectId: string, resourceId: string): Promise<{ filePath: string; fileName: string }> {
  const [{ project }, { detail }] = await Promise.all([
    adapter!.getGmScienceProject(projectId),
    adapter!.getGmScienceResourceDetail(projectId, resourceId),
  ]);
  if (!detail.resource.relativePath || detail.resource.accessMode !== "read") {
    throw new Error("This resource is not a readable local Project file.");
  }
  const workspace = fs.realpathSync(project.workspacePath);
  const candidate = fs.realpathSync(path.resolve(workspace, detail.resource.relativePath));
  const relative = path.relative(workspace, candidate);
  if (!relative || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    throw new Error("The resource path is outside the Project workspace.");
  }
  const stat = fs.statSync(candidate);
  if (!stat.isFile()) {
    throw new Error("The selected Project resource is not a regular file.");
  }
  return { filePath: candidate, fileName: detail.resource.displayName || path.basename(candidate) };
}

function disposeDesktopRuntime(): void {
  unsubscribeRunEvents?.();
  unsubscribeRunEvents = null;
  adapter?.dispose();
  adapter = null;
}

function startDesktopRuntime(): OpenPpxLocalAdapter {
  adapter = new OpenPpxLocalAdapter(readConnectionSettings() ?? undefined);
  unsubscribeRunEvents = adapter.onRunEvent((event) => {
    mainWindow?.webContents.send("ppx-client:run-event", event);
  });
  return adapter;
}

async function changeDataLocation(): Promise<{
  canceled: boolean;
  migrated: boolean;
  dataLocation: string;
}> {
  const currentLocation = path.resolve(resolveGmScienceDataRoot(process.env));
  const selected = await dialog.showOpenDialog(mainWindow!, {
    title: "Choose an empty folder for gm-science data",
    properties: ["openDirectory", "createDirectory"],
    buttonLabel: "Move data here",
  });
  if (selected.canceled || !selected.filePaths[0]) {
    return { canceled: true, migrated: false, dataLocation: currentLocation };
  }
  const destination = path.resolve(selected.filePaths[0]);
  assertSafeDataMigration(currentLocation, destination);
  const diagnostics = await adapter!.getDiagnostics();
  if (diagnostics.mode !== "local" || !diagnostics.clientApiProcessRunning) {
    throw new Error("Data migration requires the desktop-managed local gm-science runtime.");
  }

  const locationFile = dataLocationSettingsPath();
  const previousPersisted = readPersistedDataLocation(locationFile);
  const previousGmRoot = process.env.GM_SCIENCE_DATA_DIR;
  const previousOpenPpxRoot = process.env.OPENPPX_DATA_DIR;
  unsubscribeRunEvents?.();
  unsubscribeRunEvents = null;
  const previousAdapter = adapter!;
  adapter = null;
  await previousAdapter.shutdown();

  let copied = false;
  let migratedAdapter: OpenPpxLocalAdapter | null = null;
  try {
    await copyDataRootAtomically(currentLocation, destination);
    copied = true;
    process.env.GM_SCIENCE_DATA_DIR = destination;
    process.env.OPENPPX_DATA_DIR = destination;
    writePersistedDataLocation(locationFile, destination);
    migratedAdapter = startDesktopRuntime();
    await migratedAdapter.bootstrap();
    fs.rmSync(currentLocation, { recursive: true, force: true });
    return { canceled: false, migrated: true, dataLocation: destination };
  } catch (error) {
    if (migratedAdapter) {
      await migratedAdapter.shutdown();
      migratedAdapter = null;
      adapter = null;
    }
    if (copied) {
      fs.rmSync(destination, { recursive: true, force: true });
    }
    if (previousGmRoot === undefined) {
      delete process.env.GM_SCIENCE_DATA_DIR;
    } else {
      process.env.GM_SCIENCE_DATA_DIR = previousGmRoot;
    }
    if (previousOpenPpxRoot === undefined) {
      delete process.env.OPENPPX_DATA_DIR;
    } else {
      process.env.OPENPPX_DATA_DIR = previousOpenPpxRoot;
    }
    if (previousPersisted) {
      writePersistedDataLocation(locationFile, previousPersisted);
    } else {
      fs.rmSync(locationFile, { force: true });
    }
    const restoredAdapter = startDesktopRuntime();
    await restoredAdapter.bootstrap().catch(() => undefined);
    throw error;
  }
}

function quitFromSignal(): void {
  disposeDesktopRuntime();
  app.quit();
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

  startDesktopRuntime();

  if (process.env.VITE_DEV_SERVER_URL) {
    void mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL);
  } else {
    void mainWindow.loadFile(path.join(__dirname, "../../index.html"));
  }
}

app.whenReady().then(() => {
  applyPersistedDataLocation();
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
  ipcMain.handle("ppx-client:update-gm-science-session", async (_event, sessionId: string, input: { title: string }) =>
    adapter!.updateGmScienceSession(sessionId, input),
  );
  ipcMain.handle("ppx-client:delete-gm-science-session", async (_event, sessionId: string) =>
    adapter!.deleteGmScienceSession(sessionId),
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
  ipcMain.handle("ppx-client:create-gm-science-skill", async (_event, input: CreateGmScienceSkillInput) =>
    adapter!.createGmScienceSkill(input),
  );
  ipcMain.handle(
    "ppx-client:create-gm-science-connector",
    async (_event, input: CreateGmScienceConnectorInput) => adapter!.createGmScienceConnector(input),
  );
  ipcMain.handle(
    "ppx-client:create-gm-science-specialist",
    async (_event, input: CreateGmScienceSpecialistInput) => adapter!.createGmScienceSpecialist(input),
  );
  ipcMain.handle(
    "ppx-client:import-gm-science-skill",
    async (_event, input: ImportGmScienceSkillInput) => adapter!.importGmScienceSkill(input),
  );
  ipcMain.handle("ppx-client:list-gm-science-skill-drafts", async () =>
    adapter!.listGmScienceSkillDrafts(),
  );
  ipcMain.handle(
    "ppx-client:save-gm-science-skill-draft",
    async (_event, input: CreateGmScienceSkillInput) => adapter!.saveGmScienceSkillDraft(input),
  );
  ipcMain.handle(
    "ppx-client:publish-gm-science-skill-draft",
    async (_event, draftId: string) => adapter!.publishGmScienceSkillDraft(draftId),
  );
  ipcMain.handle(
    "ppx-client:delete-gm-science-skill-draft",
    async (_event, draftId: string) => adapter!.deleteGmScienceSkillDraft(draftId),
  );
  ipcMain.handle(
    "ppx-client:select-gm-science-skill-source",
    async (_event, mode: GmScienceSkillSourcePickerMode) => {
      const result = await dialog.showOpenDialog(mainWindow!, {
        title: mode === "directory" ? "Choose a Skill folder" : "Choose a SKILL.md or zip bundle",
        properties: mode === "directory" ? ["openDirectory"] : ["openFile"],
        filters: mode === "file"
          ? [{ name: "Skill bundle", extensions: ["md", "zip"] }]
          : undefined,
      });
      return { canceled: result.canceled, sourcePath: result.filePaths[0] ?? "" };
    },
  );
  ipcMain.handle(
    "ppx-client:get-gm-science-capability-definition",
    async (_event, kind: GmScienceCapabilityKind, capabilityId: string) =>
      adapter!.getGmScienceCapabilityDefinition(kind, capabilityId),
  );
  ipcMain.handle(
    "ppx-client:update-gm-science-capability",
    async (
      _event,
      kind: GmScienceCapabilityKind,
      capabilityId: string,
      input: CreateGmScienceSkillInput | CreateGmScienceConnectorInput | CreateGmScienceSpecialistInput,
    ) => adapter!.updateGmScienceCapability(kind, capabilityId, input),
  );
  ipcMain.handle(
    "ppx-client:delete-gm-science-capability",
    async (_event, kind: GmScienceCapabilityKind, capabilityId: string) =>
      adapter!.deleteGmScienceCapability(kind, capabilityId),
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
  ipcMain.handle("ppx-client:change-gm-science-data-location", async () => changeDataLocation());
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
  ipcMain.handle("ppx-client:get-gm-science-project-session-policy-defaults", async (_event, projectId: string) =>
    adapter!.getGmScienceProjectSessionPolicyDefaults(projectId),
  );
  ipcMain.handle(
    "ppx-client:update-gm-science-project-session-policy-defaults",
    async (_event, projectId: string, input: UpdateGmScienceSessionPolicyInput) =>
      adapter!.updateGmScienceProjectSessionPolicyDefaults(projectId, input),
  );
  ipcMain.handle("ppx-client:list-gm-science-artifacts", async (_event, projectId: string) =>
    adapter!.listGmScienceArtifacts(projectId),
  );
  ipcMain.handle(
    "ppx-client:list-gm-science-resources",
    async (_event, projectId: string, query?: string) => adapter!.listGmScienceResources(projectId, query),
  );
  ipcMain.handle(
    "ppx-client:list-gm-science-project-sources",
    async (_event, projectId: string) => adapter!.listGmScienceProjectSources(projectId),
  );
  ipcMain.handle(
    "ppx-client:select-gm-science-project-source",
    async (_event, kind: "file" | "folder") => {
      const result = await dialog.showOpenDialog(mainWindow!, {
        title: kind === "folder" ? "Add a folder to this Project" : "Add a file to this Project",
        properties: kind === "folder" ? ["openDirectory"] : ["openFile"],
      });
      return { canceled: result.canceled, sourcePath: result.filePaths[0] ?? "" };
    },
  );
  ipcMain.handle(
    "ppx-client:import-gm-science-project-source",
    async (_event, projectId: string, input: { sourcePath: string; kind: "file" | "folder" }) =>
      adapter!.importGmScienceProjectSource(projectId, input),
  );
  ipcMain.handle(
    "ppx-client:delete-gm-science-project-source",
    async (_event, projectId: string, sourceId: string) =>
      adapter!.deleteGmScienceProjectSource(projectId, sourceId),
  );
  ipcMain.handle(
    "ppx-client:download-gm-science-resource",
    async (_event, projectId: string, resourceId: string) => {
      const resource = await resolveProjectResourcePath(projectId, resourceId);
      const selected = await dialog.showSaveDialog(mainWindow!, {
        title: "Download Project file",
        defaultPath: resource.fileName,
      });
      if (selected.canceled || !selected.filePath) {
        return { canceled: true, destination: "" };
      }
      await fs.promises.copyFile(resource.filePath, selected.filePath);
      return { canceled: false, destination: selected.filePath };
    },
  );
  ipcMain.handle(
    "ppx-client:reveal-gm-science-resource",
    async (_event, projectId: string, resourceId: string) => {
      const resource = await resolveProjectResourcePath(projectId, resourceId);
      shell.showItemInFolder(resource.filePath);
    },
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
  ipcMain.handle(
    "ppx-client:update-gm-science-artifact",
    async (_event, projectId: string, artifactId: string, input: UpdateGmScienceArtifactInput) =>
      adapter!.updateGmScienceArtifact(projectId, artifactId, input),
  );
  ipcMain.handle(
    "ppx-client:delete-gm-science-artifact",
    async (_event, projectId: string, artifactId: string) =>
      adapter!.deleteGmScienceArtifact(projectId, artifactId),
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
  disposeDesktopRuntime();
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", disposeDesktopRuntime);
process.once("SIGINT", quitFromSignal);
process.once("SIGTERM", quitFromSignal);
