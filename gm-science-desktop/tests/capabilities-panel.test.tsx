import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { CapabilitiesPanel } from "../app/src/components/CapabilitiesPanel";

describe("CapabilitiesPanel", () => {
  it("lists durable Skill drafts and exposes resume and delete actions", () => {
    const draft = {
      id: "assay-draft",
      name: "Assay Draft",
      description: "Work in progress.",
      content: "",
      version: "",
      license: "",
      updatedAt: "2026-07-19T00:00:00.000Z",
    };
    const onEditDraft = vi.fn();
    const onDeleteDraft = vi.fn();
    render(
      <CapabilitiesPanel
        kind="skill"
        items={[]}
        drafts={[draft]}
        loading={false}
        saving={false}
        error={null}
        onToggle={vi.fn()}
        onRefresh={vi.fn()}
        onAdd={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onEditDraft={onEditDraft}
        onDeleteDraft={onDeleteDraft}
      />,
    );

    expect(screen.getByRole("heading", { name: /Drafts/ })).toBeInTheDocument();
    expect(screen.getByText("Assay Draft")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit draft Assay Draft" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete draft Assay Draft" }));
    expect(onEditDraft).toHaveBeenCalledWith(draft);
    expect(onDeleteDraft).toHaveBeenCalledWith(draft);
  });
});
