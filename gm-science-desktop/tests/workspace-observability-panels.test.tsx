import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import {
  StorageSettingsPanel,
  UsageSettingsPanel,
} from "../app/src/components/WorkspaceObservabilityPanels";
import type {
  GmScienceStorageSnapshot,
  GmScienceUsageSnapshot,
} from "../app/src/types";

const storage: GmScienceStorageSnapshot = {
  dataLocation: "/tmp/gm-science",
  exists: true,
  writable: true,
  scannedAt: "2026-07-19T00:00:00Z",
  scanComplete: false,
  partialReason: "Scan stopped after 100 filesystem entries.",
  entriesScanned: 100,
  elapsedMs: 17,
  totalBytes: 1_572_864,
  totalFiles: 9,
  categories: [
    { id: "workspaces", name: "Workspaces", bytes: 1_048_576, files: 5 },
    { id: "databases", name: "Databases", bytes: 524_288, files: 4 },
  ],
  issues: [],
  cloudStorage: { supported: false, configured: false, detail: "No cloud storage adapter is available in this build." },
};

const usage: GmScienceUsageSnapshot = {
  window: "7d",
  generatedAt: "2026-07-19T00:00:00Z",
  since: "2026-07-12T00:00:00Z",
  until: "2026-07-19T00:00:00Z",
  localEstimate: true,
  cost: { available: false, reason: "No provider price ledger." },
  tokens: {
    recordingStarted: true,
    requests: 3,
    inputTokens: 1200,
    outputTokens: 300,
    inputTextTokens: 1200,
    outputTextTokens: 300,
    inputImageTokens: 0,
    outputImageTokens: 0,
    totalTokens: 1500,
    byModel: [{ provider: "openai_codex", model: "openai-codex/gpt-5.5", requests: 3, inputTokens: 1200, outputTokens: 300, totalTokens: 1500 }],
  },
  runs: {
    recordingStarted: true,
    runs: 2,
    activeRuns: 1,
    terminalRuns: 1,
    runtimeMs: 65_000,
    byStatus: [{ status: "completed", runs: 1, runtimeMs: 60_000 }, { status: "running", runs: 1, runtimeMs: 5_000 }],
    byKind: [{ kind: "data_analysis", runs: 2, runtimeMs: 65_000 }],
  },
};

describe("workspace observability settings", () => {
  it("shows the actual data root, measured categories, and partial scan state", () => {
    const onChangeLocation = vi.fn(async () => undefined);
    render(
      <StorageSettingsPanel
        snapshot={storage}
        loading={false}
        error={null}
        onRefresh={vi.fn()}
        onChangeLocation={onChangeLocation}
      />,
    );

    expect(screen.getByText("/tmp/gm-science")).toBeInTheDocument();
    expect(screen.getByText("1.50 MB")).toBeInTheDocument();
    expect(screen.getByText("Workspaces")).toBeInTheDocument();
    expect(screen.getByText("Partial scan")).toBeInTheDocument();
    expect(screen.getByText("No cloud storage adapter is available in this build.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Change location" }));
    expect(onChangeLocation).toHaveBeenCalledOnce();
  });

  it("shows local token and TaskRun usage and changes the selected period", () => {
    const onWindowChange = vi.fn();
    render(
      <UsageSettingsPanel
        snapshot={usage}
        window="7d"
        loading={false}
        error={null}
        onWindowChange={onWindowChange}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByText("openai-codex/gpt-5.5")).toBeInTheDocument();
    expect(screen.getAllByText("1,500")).toHaveLength(2);
    expect(screen.getByText("1m 5s")).toBeInTheDocument();
    expect(screen.getByText("Cost unavailable")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "30 days" }));
    expect(onWindowChange).toHaveBeenCalledWith("30d");
  });
});
