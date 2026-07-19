import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { CapabilityCreatePanel } from "../app/src/components/CapabilityCreatePanel";
import type { GmScienceCapability } from "../app/src/types";

const capabilities: GmScienceCapability[] = [
  {
    id: "literature-review", kind: "skill", name: "Literature Review", description: "Review papers.",
    source: "built_in", version: "", license: "", files: [], available: true, defaultEnabled: true,
    projectEnabled: true, status: "ready", statusDetail: "", metadata: {},
  },
  {
    id: "boltz", kind: "skill", name: "Boltz", description: "Unavailable model.",
    source: "built_in", version: "", license: "", files: [], available: false, defaultEnabled: false,
    projectEnabled: false, status: "disabled", statusDetail: "Not installed.", metadata: {},
  },
  {
    id: "pubmed", kind: "connector", name: "PubMed", description: "Search biomedical papers.",
    source: "external", version: "", license: "", files: [], available: true, defaultEnabled: true,
    projectEnabled: true, status: "ready", statusDetail: "", metadata: {},
  },
];

const baseProps = {
  capabilities,
  credentials: [{ id: "workspace-token", name: "Workspace token", configured: true }],
  saving: false,
  error: null,
  onCancel: vi.fn(),
  onCreateSkill: vi.fn(async () => undefined),
  onCreateConnector: vi.fn(async () => undefined),
  onCreateSpecialist: vi.fn(async () => undefined),
  onImportSkill: vi.fn(async () => undefined),
  onSaveSkillDraft: vi.fn(async () => undefined),
  onPublishSkillDraft: vi.fn(async () => undefined),
  onSelectSkillSource: vi.fn(async () => null),
};

describe("CapabilityCreatePanel", () => {
  it("builds a local Skill request with an editable generated ID", async () => {
    const onCreateSkill = vi.fn(async () => undefined);
    render(<CapabilityCreatePanel {...baseProps} kind="skill" onCreateSkill={onCreateSkill} />);

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Assay Quality" } });
    expect(screen.getByLabelText("Skill ID")).toHaveValue("assay-quality");
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Review assay quality." } });
    fireEvent.change(screen.getByLabelText("Markdown content"), { target: { value: "# Workflow" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    expect(onCreateSkill).toHaveBeenCalledWith({
      id: "assay-quality",
      name: "Assay Quality",
      description: "Review assay quality.",
      content: "# Workflow",
    });
  });

  it("saves an incomplete Skill as a durable draft", () => {
    const onSaveSkillDraft = vi.fn(async () => undefined);
    render(<CapabilityCreatePanel {...baseProps} kind="skill" onSaveSkillDraft={onSaveSkillDraft} />);

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Assay Draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));

    expect(onSaveSkillDraft).toHaveBeenCalledWith({
      id: "assay-draft",
      name: "Assay Draft",
      description: "",
      content: "",
    });
  });

  it("saves and publishes a resumed complete Skill draft", async () => {
    const onSaveSkillDraft = vi.fn(async () => undefined);
    const onPublishSkillDraft = vi.fn(async () => undefined);
    render(
      <CapabilityCreatePanel
        {...baseProps}
        kind="skill"
        draft={{
          id: "assay-draft",
          name: "Assay Draft",
          description: "Review assay quality.",
          content: "# Workflow",
          version: "",
          license: "",
          updatedAt: "2026-07-19T00:00:00.000Z",
        }}
        onSaveSkillDraft={onSaveSkillDraft}
        onPublishSkillDraft={onPublishSkillDraft}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Publish" }));

    await waitFor(() => {
      expect(onSaveSkillDraft).toHaveBeenCalledWith({
        id: "assay-draft",
        name: "Assay Draft",
        description: "Review assay quality.",
        content: "# Workflow",
      });
      expect(onPublishSkillDraft).toHaveBeenCalledWith("assay-draft");
    });
  });

  it("maps Local command Connector fields without remote URL state", () => {
    const onCreateConnector = vi.fn(async () => undefined);
    render(<CapabilityCreatePanel {...baseProps} kind="connector" onCreateConnector={onCreateConnector} />);

    fireEvent.click(screen.getByRole("button", { name: "Local command" }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Local Files" } });
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Read local files." } });
    fireEvent.change(screen.getByLabelText("Command line"), {
      target: { value: "mcp-server-filesystem /tmp/research" },
    });
    fireEvent.change(screen.getByLabelText("Allowed tools (optional)"), {
      target: { value: "read_file\nlist_directory" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.change(screen.getByLabelText("Environment variables name"), {
      target: { value: "WORKSPACE_TOKEN" },
    });
    fireEvent.change(screen.getByLabelText("Environment variables value"), {
      target: { value: "workspace-token" },
    });
    fireEvent.click(screen.getByRole("checkbox", { name: /Confirm tool calls/ }));
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    expect(onCreateConnector).toHaveBeenCalledWith({
      id: "local-files",
      name: "Local Files",
      description: "Read local files.",
      connectionType: "local",
      url: undefined,
      commandLine: "mcp-server-filesystem /tmp/research",
      toolFilter: ["read_file", "list_directory"],
      requireConfirmation: true,
      headerCredentialRefs: undefined,
      environmentCredentialRefs: { WORKSPACE_TOKEN: "workspace-token" },
    });
  });

  it("starts Specialists with no assignments and submits only explicit selections", () => {
    const onCreateSpecialist = vi.fn(async () => undefined);
    render(<CapabilityCreatePanel {...baseProps} kind="specialist" onCreateSpecialist={onCreateSpecialist} />);

    expect(screen.getByRole("checkbox", { name: /Literature Review/ })).not.toBeChecked();
    expect(screen.queryByRole("checkbox", { name: /Boltz/ })).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /PubMed/ })).not.toBeChecked();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Evidence Reviewer" } });
    expect(screen.getByLabelText("Agent ID")).toHaveValue("evidence_reviewer");
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Review evidence." } });
    fireEvent.change(screen.getByLabelText("Instructions"), { target: { value: "Check every claim." } });
    fireEvent.click(screen.getByRole("checkbox", { name: /Literature Review/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /PubMed/ }));
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    expect(onCreateSpecialist).toHaveBeenCalledWith({
      id: "evidence_reviewer",
      name: "Evidence Reviewer",
      description: "Review evidence.",
      instructions: "Check every claim.",
      skills: ["literature-review"],
      connectors: ["pubmed"],
      connectorTools: {},
    });
  });

  it("submits a tool-level allowlist for an assigned MCP Connector", () => {
    const onCreateSpecialist = vi.fn(async () => undefined);
    const mcpConnector: GmScienceCapability = {
      id: "mcp:lab-tools", kind: "connector", name: "Lab Tools", description: "Laboratory MCP tools.",
      source: "local", version: "", license: "", files: [], available: true, defaultEnabled: false,
      projectEnabled: false, status: "ready", statusDetail: "", metadata: {},
    };
    render(
      <CapabilityCreatePanel
        {...baseProps}
        capabilities={[...capabilities, mcpConnector]}
        kind="specialist"
        onCreateSpecialist={onCreateSpecialist}
      />,
    );

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Lab Reviewer" } });
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Review lab evidence." } });
    fireEvent.change(screen.getByLabelText("Instructions"), { target: { value: "Use bounded lab tools." } });
    fireEvent.click(screen.getByRole("checkbox", { name: /Lab Tools/ }));
    fireEvent.change(screen.getByLabelText("Allowed tools for Lab Tools (optional)"), {
      target: { value: "search_samples\nread_sample" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    expect(onCreateSpecialist).toHaveBeenCalledWith({
      id: "lab_reviewer",
      name: "Lab Reviewer",
      description: "Review lab evidence.",
      instructions: "Use bounded lab tools.",
      skills: [],
      connectors: ["mcp:lab-tools"],
      connectorTools: { "mcp:lab-tools": ["search_samples", "read_sample"] },
    });
  });
});
