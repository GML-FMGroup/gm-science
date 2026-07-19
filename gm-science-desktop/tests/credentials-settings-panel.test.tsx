import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { CredentialsSettingsPanel } from "../app/src/components/SettingsPanels";
import type { GmScienceSettings } from "../app/src/types";

function settings(): GmScienceSettings {
  return {
    providers: [{
      id: "openai_codex",
      name: "OpenAI Codex",
      defaultModel: "openai-codex/gpt-5.5",
      authType: "oauth",
      credentialRequired: true,
      credentialConfigured: true,
      credentialSource: "oauth_cache",
      active: true,
    }],
    credentials: { custom: [{ id: "lab-token", name: "Lab token", configured: true }] },
    literature: {
      arxiv: { status: "ready", statusDetail: "" },
      pubmed: { email: "researcher@example.org", apiKeyConfigured: false, status: "ready", statusDetail: "" },
      openalex: { apiKeyConfigured: false, status: "needs_configuration", statusDetail: "API key required." },
    },
  } as GmScienceSettings;
}

describe("CredentialsSettingsPanel", () => {
  it("uses write-only mutations for custom Connector credentials", async () => {
    const onUpdate = vi.fn(async () => undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(
      <CredentialsSettingsPanel
        settings={settings()}
        loading={false}
        saving={false}
        error={null}
        onUpdate={onUpdate}
      />,
    );

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Registry token" } });
    fireEvent.change(screen.getByLabelText("Credential ID"), { target: { value: "registry-token" } });
    fireEvent.change(screen.getByLabelText("Secret value"), { target: { value: "secret-value" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => expect(onUpdate).toHaveBeenCalledWith({
      customCredential: {
        operation: "upsert",
        id: "registry-token",
        name: "Registry token",
        value: "secret-value",
      },
    }));

    fireEvent.click(screen.getByRole("button", { name: "Remove Lab token" }));
    await waitFor(() => expect(onUpdate).toHaveBeenCalledWith({
      customCredential: { operation: "remove", id: "lab-token" },
    }));
    expect(screen.queryByDisplayValue("secret-value")).not.toBeInTheDocument();
  });
});
