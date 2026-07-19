import { fireEvent, render, screen } from "@testing-library/react";
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
  saving: false,
  error: null,
  onCancel: vi.fn(),
  onCreateSkill: vi.fn(async () => undefined),
  onCreateConnector: vi.fn(async () => undefined),
  onCreateSpecialist: vi.fn(async () => undefined),
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

  it("maps Local command Connector fields without remote URL state", () => {
    const onCreateConnector = vi.fn(async () => undefined);
    render(<CapabilityCreatePanel {...baseProps} kind="connector" onCreateConnector={onCreateConnector} />);

    fireEvent.click(screen.getByRole("button", { name: "Local command" }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Local Files" } });
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Read local files." } });
    fireEvent.change(screen.getByLabelText("Command line"), {
      target: { value: "mcp-server-filesystem /tmp/research" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    expect(onCreateConnector).toHaveBeenCalledWith({
      id: "local-files",
      name: "Local Files",
      description: "Read local files.",
      connectionType: "local",
      url: undefined,
      commandLine: "mcp-server-filesystem /tmp/research",
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
    });
  });
});
