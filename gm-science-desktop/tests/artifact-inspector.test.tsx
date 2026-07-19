import { render, screen, within } from "@testing-library/react";
import { vi } from "vitest";
import { ArtifactInspector } from "../app/src/components/ArtifactInspector";
import type { GmScienceResource, GmScienceResourceDetail } from "../app/src/types";

const resource: GmScienceResource = {
  id: "project_file:measurements",
  kind: "project_file",
  projectId: "proj-1",
  sessionId: "",
  displayName: "measurements.csv",
  artifactType: "project_file",
  mimeType: "text/csv",
  versionOrHash: "sha-1",
  accessMode: "read",
  source: "workspace",
  artifactId: "",
  relativePath: "references/measurements.csv",
  url: "",
  sizeBytes: 32,
  createdAt: "2026-07-19T00:00:00.000Z",
  updatedAt: "2026-07-19T00:00:00.000Z",
  metadata: {},
};

const detail: GmScienceResourceDetail = {
  resource,
  preview: {
    content: "sample,value\nA,1\n",
    contentStatus: "included",
    contentIncluded: true,
    contentChars: 17,
    truncated: false,
    displayMode: "table",
    table: { columns: ["sample", "value"], rows: [["A", "1"]], truncated: false },
  },
  artifact: null,
  relations: [],
};

describe("ArtifactInspector", () => {
  it("renders a structured table preview", () => {
    render(
      <ArtifactInspector
        tabs={[resource]}
        activeResourceId={resource.id}
        detail={detail}
        loading={false}
        error={null}
        actionError={null}
        provenanceOpen={false}
        onBack={vi.fn()}
        onSelectTab={vi.fn()}
        onCloseTab={vi.fn()}
        onRetry={vi.fn()}
        onViewInContext={vi.fn()}
        onOpenProvenance={vi.fn()}
        onCloseProvenance={vi.fn()}
        onOpenRelation={vi.fn()}
        onRename={vi.fn()}
        onToggleStar={vi.fn()}
        onHide={vi.fn()}
        onDelete={vi.fn()}
        onCopyLink={vi.fn()}
        onDownload={vi.fn()}
        onReveal={vi.fn()}
        onExport={vi.fn()}
      />,
    );

    const tableRegion = screen.getByRole("region", { name: "Table preview" });
    expect(within(tableRegion).getByRole("columnheader", { name: "sample" })).toBeInTheDocument();
    expect(within(tableRegion).getByRole("cell", { name: "A" })).toBeInTheDocument();
    expect(within(tableRegion).getByRole("cell", { name: "1" })).toBeInTheDocument();
  });
});
