import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { MemorySettingsPanel } from "../app/src/components/MemorySettingsPanel";
import type {
  GmScienceMemoryWorkspace,
  GmScienceSettings,
  PpxClientApi,
} from "../app/src/types";

function settings(enabled = true): GmScienceSettings {
  return {
    model: { provider: "openai_codex", model: "openai-codex/gpt-5.5" },
    memory: { enabled },
    providers: [],
    permissions: { items: [] },
    network: {
      enabled: true,
      enforceAllowlist: true,
      allowPrivateNetworks: false,
      packageMirrors: { condaChannelMirror: "", pythonPackageIndex: "", caBundlePath: "" },
      categories: [],
      customDomains: [],
      enforcementBoundary: "Managed gm-science network clients.",
    },
    compute: { targets: [] },
    literature: {
      arxiv: { status: "ready", statusDetail: "" },
      pubmed: { email: "", apiKeyConfigured: false, status: "ready", statusDetail: "" },
      openalex: { apiKeyConfigured: false, status: "ready", statusDetail: "" },
    },
  };
}

function workspace(): GmScienceMemoryWorkspace {
  return {
    projectId: "proj-1",
    notes: [],
    candidates: [
      {
        id: "candidate-1",
        scope: "project",
        category: "Project context",
        text: "Use GRCh38 for genome references.",
        rationale: "A durable Project convention.",
        status: "pending",
        projectId: "proj-1",
        sourceSessionId: "session-1",
        model: "openai-codex/gpt-5.5",
        approvedNoteId: "",
        createdAt: "2026-07-19T01:00:00Z",
        reviewedAt: "",
      },
    ],
    categories: ["Project context"],
  };
}

function installClient(memory: GmScienceMemoryWorkspace) {
  const getGmScienceMemory = vi.fn(async () => structuredClone(memory));
  const createGmScienceMemoryNote = vi.fn(async (_projectId, input) => {
    const note = {
      id: "note-manual",
      ...input,
      createdAt: "2026-07-19T01:00:00Z",
      updatedAt: "2026-07-19T01:00:00Z",
      provenance: { source: "manual", projectId: "", sessionId: "", model: "", candidateId: "", rationale: "" },
      usage: { count: 0, sessionIds: [], lastUsedAtMs: 0 },
    };
    memory.notes.unshift(note);
    return structuredClone(note);
  });
  const reviewGmScienceMemoryCandidate = vi.fn(async (_projectId, candidateId, decision) => {
    const candidate = memory.candidates.find((item) => item.id === candidateId)!;
    candidate.status = decision === "approve" ? "approved" : "rejected";
    return structuredClone(candidate);
  });
  const api = {
    getGmScienceMemory,
    createGmScienceMemoryNote,
    updateGmScienceMemoryNote: vi.fn(),
    deleteGmScienceMemoryNote: vi.fn(),
    clearGmScienceMemory: vi.fn(async () => 0),
    reviewGmScienceMemoryCandidate,
  } as unknown as PpxClientApi;
  Object.defineProperty(window, "ppxClient", { configurable: true, value: api });
  return { api, getGmScienceMemory, createGmScienceMemoryNote, reviewGmScienceMemoryCandidate };
}

describe("MemorySettingsPanel", () => {
  it("reviews Project candidates and updates the global switch", async () => {
    const memory = workspace();
    const client = installClient(memory);
    const onSetGlobalEnabled = vi.fn(async () => undefined);

    render(
      <MemorySettingsPanel
        projectId="proj-1"
        projectName="Genome study"
        settings={settings(true)}
        settingsLoading={false}
        settingsSaving={false}
        settingsError={null}
        onSetGlobalEnabled={onSetGlobalEnabled}
      />,
    );

    await waitFor(() => expect(client.getGmScienceMemory).toHaveBeenCalledWith("proj-1"));
    fireEvent.click(screen.getByRole("tab", { name: "Genome study" }));
    expect(await screen.findByText("Use GRCh38 for genome references.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(client.reviewGmScienceMemoryCandidate).toHaveBeenCalledWith(
      "proj-1",
      "candidate-1",
      "approve",
    ));
    await waitFor(() => expect(screen.queryByText("Use GRCh38 for genome references.")).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole("checkbox", { name: "Enable Memory" }));
    expect(onSetGlobalEnabled).toHaveBeenCalledWith(false);
  });

  it("creates an explicit User note and refreshes the approved list", async () => {
    const memory = workspace();
    const client = installClient(memory);

    render(
      <MemorySettingsPanel
        projectId="proj-1"
        projectName="Genome study"
        settings={settings()}
        settingsLoading={false}
        settingsSaving={false}
        settingsError={null}
        onSetGlobalEnabled={async () => undefined}
      />,
    );

    await waitFor(() => expect(client.getGmScienceMemory).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.change(screen.getByLabelText("Category"), { target: { value: "Preferences" } });
    fireEvent.change(screen.getByLabelText("Note"), { target: { value: "Prefer concise summaries." } });
    fireEvent.click(screen.getByRole("button", { name: "Add note" }));

    await waitFor(() => expect(client.createGmScienceMemoryNote).toHaveBeenCalledWith("proj-1", {
      scope: "user",
      category: "Preferences",
      text: "Prefer concise summaries.",
    }));
    expect(await screen.findByText("Prefer concise summaries.")).toBeInTheDocument();
  });
});
