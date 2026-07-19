import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import {
  ComputeSettingsPanel,
  NetworkSettingsPanel,
  PermissionsSettingsPanel,
} from "../app/src/components/InfrastructureSettingsPanels";
import type { GmScienceSettings } from "../app/src/types";

function settings(): GmScienceSettings {
  return {
    model: { provider: "openai_codex", model: "openai-codex/gpt-5.5" },
    memory: { enabled: true },
    general: { reasoningEffort: "medium", reasoningEffortSupported: true, subagentModel: "", licenseUseIntent: "commercial" },
    providers: [],
    credentials: { custom: [] },
    permissions: {
      items: [{
        id: "attach_skill",
        name: "Attach skill",
        description: "Attach a Skill to a Project.",
        category: "registry_writes",
        granted: true,
        scope: "global",
        source: "default",
        updatedAt: "",
      }],
    },
    network: {
      enabled: true,
      enforceAllowlist: true,
      allowPrivateNetworks: false,
      packageMirrors: {
        condaChannelMirror: "",
        pythonPackageIndex: "",
        caBundlePath: "",
      },
      categories: [{
        id: "research_data",
        name: "Research data",
        description: "Literature and research data services.",
        enabled: true,
        domains: ["pubmed.ncbi.nlm.nih.gov"],
      }],
      customDomains: [],
      enforcementBoundary: "Managed gm-science HTTP clients and TaskRun environments.",
    },
    compute: {
      targets: [{
        id: "local",
        type: "local",
        name: "This computer",
        enabled: true,
        configured: true,
        executable: true,
        status: "ready",
        statusDetail: "Local TaskRun execution is available.",
        metadata: { runtime: "managed_python" },
      }],
    },
    literature: {
      arxiv: { status: "ready", statusDetail: "" },
      pubmed: { email: "", apiKeyConfigured: false, status: "ready", statusDetail: "" },
      openalex: { apiKeyConfigured: false, status: "ready", statusDetail: "" },
    },
  };
}

const commonProps = {
  loading: false,
  saving: false,
  error: null,
};

describe("infrastructure settings panels", () => {
  it("persists an explicit registry permission revoke", async () => {
    const onUpdate = vi.fn(async () => undefined);
    render(<PermissionsSettingsPanel {...commonProps} settings={settings()} onUpdate={onUpdate} />);

    fireEvent.click(screen.getByRole("switch", { name: "Grant Attach skill" }));

    await waitFor(() => expect(onUpdate).toHaveBeenCalledWith({
      permissionGrants: { attach_skill: false },
    }));
  });

  it("saves package, category, and custom-domain Network settings together", async () => {
    const onUpdate = vi.fn(async () => undefined);
    render(<NetworkSettingsPanel {...commonProps} settings={settings()} onUpdate={onUpdate} />);

    fireEvent.change(screen.getByLabelText("Python package index"), {
      target: { value: "https://packages.example.test/simple" },
    });
    fireEvent.click(screen.getByRole("switch", { name: "Enable Research data" }));
    fireEvent.change(screen.getByLabelText("Custom Network domains"), {
      target: { value: "data.example.test\n*.lab.example.test" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(onUpdate).toHaveBeenCalledWith({
      network: {
        enabled: true,
        enforceAllowlist: true,
        allowPrivateNetworks: false,
        condaChannelMirror: "",
        pythonPackageIndex: "https://packages.example.test/simple",
        caBundlePath: "",
        categoryEnabled: { research_data: false },
        customDomains: ["data.example.test", "*.lab.example.test"],
      },
    }));
  });

  it("keeps remote target reachability separate from executability", async () => {
    const remoteSettings = settings();
    remoteSettings.compute.targets = [{
      id: "lab_cluster",
      type: "ssh",
      name: "Lab cluster",
      enabled: true,
      configured: true,
      executable: false,
      status: "unavailable",
      statusDetail: "Remote execution is not implemented.",
      metadata: { host: "cluster.example.test", username: "researcher", port: 22 },
    }];
    const onCheck = vi.fn(async (targetId: string) => ({
      targetId,
      status: "reachable" as const,
      reachable: true,
      executable: false,
      detail: "SSH port is reachable; remote execution is not implemented.",
      checkedAt: "2026-07-19T02:00:00Z",
    }));
    render(
      <ComputeSettingsPanel
        {...commonProps}
        settings={remoteSettings}
        onUpdate={vi.fn(async () => undefined)}
        onCheck={onCheck}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Check" }));

    await screen.findByText("SSH port is reachable; remote execution is not implemented.");
    expect(onCheck).toHaveBeenCalledWith("lab_cluster");
    expect(screen.getByText("reachable")).toBeInTheDocument();
  });

  it("registers an SSH target without claiming it is executable", async () => {
    const onUpdate = vi.fn(async () => undefined);
    render(
      <ComputeSettingsPanel
        {...commonProps}
        settings={settings()}
        onUpdate={onUpdate}
        onCheck={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Add target" }));
    fireEvent.change(screen.getByLabelText("Compute Target ID"), { target: { value: "lab_cluster" } });
    fireEvent.change(screen.getByLabelText("Compute Target name"), { target: { value: "Lab cluster" } });
    fireEvent.change(screen.getByLabelText("SSH host"), { target: { value: "cluster.example.test" } });
    fireEvent.change(screen.getByLabelText("SSH username"), { target: { value: "researcher" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => expect(onUpdate).toHaveBeenCalledWith({
      computeTarget: {
        operation: "upsert",
        target: expect.objectContaining({
          id: "lab_cluster",
          type: "ssh",
          name: "Lab cluster",
          enabled: true,
          host: "cluster.example.test",
          port: 22,
          username: "researcher",
        }),
      },
    }));
  });

  it("confirms before removing a configured Compute Target", async () => {
    const configured = settings();
    configured.compute.targets = [{
      id: "lab_cluster",
      type: "ssh",
      name: "Lab cluster",
      enabled: true,
      configured: true,
      executable: false,
      status: "unavailable",
      statusDetail: "Remote execution is not implemented.",
      metadata: { host: "cluster.example.test" },
    }];
    const onUpdate = vi.fn(async () => undefined);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(
      <ComputeSettingsPanel
        {...commonProps}
        settings={configured}
        onUpdate={onUpdate}
        onCheck={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Remove Lab cluster" }));
    expect(onUpdate).not.toHaveBeenCalled();

    confirm.mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: "Remove Lab cluster" }));

    await waitFor(() => expect(onUpdate).toHaveBeenCalledWith({
      computeTarget: { operation: "remove", id: "lab_cluster" },
    }));
    confirm.mockRestore();
  });
});
