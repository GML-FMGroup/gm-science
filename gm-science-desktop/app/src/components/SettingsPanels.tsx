import { useEffect, useMemo, useState } from "react";
import { KeyRound, Plus, Trash2 } from "lucide-react";
import type {
  ClientDiagnostics,
  ConnectionSettings,
  GmScienceProviderOption,
  GmScienceSettings,
  RuntimeStatus,
  UpdateGmScienceSettingsInput,
} from "../types";

interface GeneralSettingsPanelProps {
  settings: GmScienceSettings | null;
  loading: boolean;
  saving: boolean;
  error: string | null;
  runtime: RuntimeStatus;
  diagnostics: ClientDiagnostics | null;
  connectionForm: ConnectionSettings;
  savingConnection: boolean;
  onUpdateModel: (model: { provider: string; model: string }) => Promise<void>;
  onUpdateGeneral: (general: NonNullable<UpdateGmScienceSettingsInput["general"]>) => Promise<void>;
  onConnectionFormChange: (settings: ConnectionSettings) => void;
  onSaveConnection: () => Promise<void>;
}

interface CredentialsSettingsPanelProps {
  settings: GmScienceSettings | null;
  loading: boolean;
  saving: boolean;
  error: string | null;
  onUpdate: (input: UpdateGmScienceSettingsInput) => Promise<void>;
}

function providerStatus(provider: GmScienceProviderOption | undefined): string {
  if (!provider) {
    return "Not configured";
  }
  if (provider.credentialConfigured) {
    return provider.credentialSource === "environment" ? "Environment" : "Configured";
  }
  return provider.credentialRequired ? "Not configured" : "Optional";
}

export function GeneralSettingsPanel({
  settings,
  loading,
  saving,
  error,
  runtime,
  diagnostics,
  connectionForm,
  savingConnection,
  onUpdateModel,
  onUpdateGeneral,
  onConnectionFormChange,
  onSaveConnection,
}: GeneralSettingsPanelProps) {
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [reasoningEffort, setReasoningEffort] = useState<"low" | "medium" | "high">("medium");
  const [subagentModel, setSubagentModel] = useState("");
  const [licenseUseIntent, setLicenseUseIntent] = useState<"commercial" | "non_commercial">("commercial");

  useEffect(() => {
    if (!settings) {
      return;
    }
    setProvider(settings.model.provider);
    setModel(settings.model.model);
    setReasoningEffort(settings.general.reasoningEffort);
    setSubagentModel(settings.general.subagentModel);
    setLicenseUseIntent(settings.general.licenseUseIntent);
  }, [settings]);

  const selectedProvider = settings?.providers.find((item) => item.id === provider);
  const modelChanged = Boolean(
    settings && (provider !== settings.model.provider || model.trim() !== settings.model.model),
  );
  const policyChanged = Boolean(settings && (
    reasoningEffort !== settings.general.reasoningEffort
    || subagentModel.trim() !== settings.general.subagentModel
    || licenseUseIntent !== settings.general.licenseUseIntent
  ));

  return (
    <div className="settings-page science-settings-page">
      <div className="settings-page-title">
        <div><h3>General</h3><p>Model routing, local runtime, and connection settings.</p></div>
        <span className={`status-chip ${runtime.state}`}>{runtime.state}</span>
      </div>
      {error ? <p className="composer-error">{error}</p> : null}
      <section className="settings-section-block">
        <h4>Model</h4>
        {loading && !settings ? <p>Loading model settings...</p> : (
          <>
            <div className="connection-fields model-settings-fields">
              <label className="settings-field">
                <span>Provider</span>
                <select
                  aria-label="Model provider"
                  value={provider}
                  disabled={!settings || saving}
                  onChange={(event) => {
                    const nextProvider = event.target.value;
                    const option = settings?.providers.find((item) => item.id === nextProvider);
                    setProvider(nextProvider);
                    setModel(option?.defaultModel ?? "");
                  }}
                >
                  {(settings?.providers ?? []).map((option) => (
                    <option key={option.id} value={option.id}>{option.name}</option>
                  ))}
                </select>
              </label>
              <label className="settings-field">
                <span>Model</span>
                <input
                  aria-label="Default model"
                  value={model}
                  disabled={!settings || saving}
                  onChange={(event) => setModel(event.target.value)}
                />
              </label>
            </div>
            <div className="settings-inline-status">
              <span className={`status-chip ${selectedProvider?.credentialConfigured ? "ready" : "needs_configuration"}`}>
                {providerStatus(selectedProvider)}
              </span>
              <button
                className="primary"
                disabled={!modelChanged || !provider || !model.trim() || saving}
                onClick={() => void onUpdateModel({ provider, model: model.trim() }).catch(() => undefined)}
              >
                {saving ? "Saving..." : "Save model"}
              </button>
            </div>
            <p className="settings-footnote">New sessions and subsequent agent runs use the saved provider and model.</p>
          </>
        )}
      </section>
      <section className="settings-section-block">
        <h4>Agent policy</h4>
        <div className="connection-fields model-settings-fields">
          <label className="settings-field">
            <span>Reasoning effort</span>
            <select aria-label="Reasoning effort" value={reasoningEffort} disabled={!settings?.general.reasoningEffortSupported || saving} onChange={(event) => setReasoningEffort(event.target.value as "low" | "medium" | "high")}>
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
            </select>
          </label>
          <label className="settings-field">
            <span>Subagent model</span>
            <input aria-label="Subagent model" value={subagentModel} placeholder="Same as main model" disabled={!settings || saving} onChange={(event) => setSubagentModel(event.target.value)} />
          </label>
        </div>
        {!settings?.general.reasoningEffortSupported ? <p className="settings-footnote">The active provider does not expose a supported reasoning-effort control.</p> : null}
        <fieldset className="license-intent-field">
          <legend>Skill license use intent</legend>
          <label><input type="radio" name="license-intent" checked={licenseUseIntent === "commercial"} onChange={() => setLicenseUseIntent("commercial")} />Commercial use</label>
          <label><input type="radio" name="license-intent" checked={licenseUseIntent === "non_commercial"} onChange={() => setLicenseUseIntent("non_commercial")} />Non-commercial use</label>
        </fieldset>
        <div className="settings-inline-status">
          <span />
          <button className="primary" disabled={!policyChanged || saving} onClick={() => void onUpdateGeneral({ reasoningEffort, subagentModel: subagentModel.trim(), licenseUseIntent }).catch(() => undefined)}>{saving ? "Saving..." : "Save agent policy"}</button>
        </div>
      </section>
      <section className="settings-section-block">
        <h4>Connection</h4>
        <div className="connection-fields">
          <label className="settings-field">
            <span>Target type</span>
            <select
              value={connectionForm.targetType}
              onChange={(event) => onConnectionFormChange({
                ...connectionForm,
                targetType: event.target.value === "remote" ? "remote" : "local",
              })}
            >
              <option value="local">Local</option>
              <option value="remote">Remote</option>
            </select>
          </label>
          <label className="settings-field">
            <span>Target name</span>
            <input value={connectionForm.targetName} onChange={(event) => onConnectionFormChange({ ...connectionForm, targetName: event.target.value })} />
          </label>
          <label className="settings-field full">
            <span>Client API URL</span>
            <input value={connectionForm.clientApiBaseUrl} onChange={(event) => onConnectionFormChange({ ...connectionForm, clientApiBaseUrl: event.target.value })} />
          </label>
        </div>
        <button className="primary" disabled={savingConnection} onClick={() => void onSaveConnection()}>
          {savingConnection ? "Saving..." : "Save connection"}
        </button>
      </section>
      {diagnostics ? (
        <section className="settings-section-block">
          <h4>Diagnostics</h4>
          <dl className="diagnostics-list">
            <div><dt>Mode</dt><dd>{diagnostics.mode}</dd></div>
            <div><dt>Target</dt><dd>{diagnostics.target.name} ({diagnostics.target.type})</dd></div>
            <div><dt>Client API</dt><dd>{diagnostics.clientApiBaseUrl}</dd></div>
            <div><dt>Configuration</dt><dd className="path-value">{diagnostics.globalConfigPath}</dd></div>
          </dl>
        </section>
      ) : null}
    </div>
  );
}

export function CredentialsSettingsPanel({
  settings,
  loading,
  saving,
  error,
  onUpdate,
}: CredentialsSettingsPanelProps) {
  const [providerApiKey, setProviderApiKey] = useState("");
  const [pubmedEmail, setPubmedEmail] = useState("");
  const [pubmedApiKey, setPubmedApiKey] = useState("");
  const [openalexApiKey, setOpenalexApiKey] = useState("");
  const [customCredentialName, setCustomCredentialName] = useState("");
  const [customCredentialId, setCustomCredentialId] = useState("");
  const [customCredentialValue, setCustomCredentialValue] = useState("");

  useEffect(() => {
    setPubmedEmail(settings?.literature.pubmed.email ?? "");
  }, [settings?.literature.pubmed.email]);

  const activeProvider = useMemo(
    () => settings?.providers.find((provider) => provider.active),
    [settings],
  );

  async function saveProviderCredential(): Promise<void> {
    if (!providerApiKey.trim()) {
      return;
    }
    try {
      await onUpdate({ providerApiKey: { operation: "replace", value: providerApiKey.trim() } });
      setProviderApiKey("");
    } catch {
      // The parent owns the rendered error state.
    }
  }

  async function savePubMed(): Promise<void> {
    try {
      await onUpdate({
        pubmedEmail,
        pubmedApiKey: pubmedApiKey.trim()
          ? { operation: "replace", value: pubmedApiKey.trim() }
          : undefined,
      });
      setPubmedApiKey("");
    } catch {
      // The parent owns the rendered error state.
    }
  }

  async function saveOpenAlex(): Promise<void> {
    if (!openalexApiKey.trim()) {
      return;
    }
    try {
      await onUpdate({ openalexApiKey: { operation: "replace", value: openalexApiKey.trim() } });
      setOpenalexApiKey("");
    } catch {
      // The parent owns the rendered error state.
    }
  }

  async function saveCustomCredential(): Promise<void> {
    if (!customCredentialId.trim() || !customCredentialName.trim() || !customCredentialValue) {
      return;
    }
    try {
      await onUpdate({
        customCredential: {
          operation: "upsert",
          id: customCredentialId.trim(),
          name: customCredentialName.trim(),
          value: customCredentialValue,
        },
      });
      setCustomCredentialId("");
      setCustomCredentialName("");
      setCustomCredentialValue("");
    } catch {
      // The parent owns the rendered error state.
    }
  }

  return (
    <div className="settings-page science-settings-page">
      <div className="settings-page-title"><div><h3>Credentials</h3><p>Manage local credentials used by gm-science.</p></div></div>
      {error ? <p className="composer-error">{error}</p> : null}
      {loading && !settings ? <p>Loading credentials...</p> : null}
      {settings ? (
        <>
          <section className="settings-section-block">
            <h4>Model providers</h4>
            <div className="service-list credential-provider-list">
              {settings.providers.map((provider) => (
                <div className="service-row" key={provider.id}>
                  <span><KeyRound size={17} /><strong>{provider.name}</strong>{provider.active ? <small>Active</small> : null}</span>
                  <span className={`status-chip ${provider.credentialConfigured ? "ready" : provider.credentialRequired ? "needs_configuration" : ""}`}>
                    {providerStatus(provider)}
                  </span>
                </div>
              ))}
            </div>
          </section>
          <section className="settings-section-block credential-editor">
            <div className="credential-heading">
              <div><h4>{activeProvider?.name ?? "Active provider"}</h4><p>Credentials for the selected model provider.</p></div>
              <span className={`status-chip ${activeProvider?.credentialConfigured ? "ready" : "needs_configuration"}`}>{providerStatus(activeProvider)}</span>
            </div>
            {activeProvider?.authType === "oauth" ? (
              <p>Sign in through the gm-science launcher or OpenAI Codex login flow. OAuth tokens are not shown or copied into this page.</p>
            ) : (
              <div className="credential-control-row">
                <label className="settings-field"><span>API key</span><input type="password" autoComplete="off" value={providerApiKey} placeholder="Leave blank to keep existing" onChange={(event) => setProviderApiKey(event.target.value)} /></label>
                <button className="primary" disabled={!providerApiKey.trim() || saving} onClick={() => void saveProviderCredential()}>{saving ? "Saving..." : "Save"}</button>
                {activeProvider?.credentialConfigured ? <button className="secondary danger" disabled={saving} onClick={() => void onUpdate({ providerApiKey: { operation: "remove" } }).catch(() => undefined)}>Remove</button> : null}
              </div>
            )}
          </section>
          <section className="settings-section-block credential-editor">
            <div className="credential-heading">
              <div><h4>PubMed</h4><p>A contact email is required by gm-science; an NCBI API key is optional.</p></div>
              <span className={`status-chip ${settings.literature.pubmed.status}`}>{settings.literature.pubmed.status.replaceAll("_", " ")}</span>
            </div>
            <div className="credential-control-row literature-credential-row">
              <label className="settings-field"><span>Contact email</span><input type="email" value={pubmedEmail} onChange={(event) => setPubmedEmail(event.target.value)} /></label>
              <label className="settings-field"><span>NCBI API key</span><input type="password" autoComplete="off" value={pubmedApiKey} placeholder="Optional; blank keeps existing" onChange={(event) => setPubmedApiKey(event.target.value)} /></label>
              <button className="primary" disabled={!pubmedEmail.trim() || saving} onClick={() => void savePubMed()}>{saving ? "Saving..." : "Save"}</button>
              {settings.literature.pubmed.apiKeyConfigured ? <button className="secondary danger" disabled={saving} onClick={() => void onUpdate({ pubmedApiKey: { operation: "remove" } }).catch(() => undefined)}>Remove key</button> : null}
            </div>
          </section>
          <section className="settings-section-block credential-editor">
            <div className="credential-heading">
              <div><h4>OpenAlex</h4><p>A free OpenAlex API key is required for current API access.</p></div>
              <span className={`status-chip ${settings.literature.openalex.status}`}>{settings.literature.openalex.status.replaceAll("_", " ")}</span>
            </div>
            <div className="credential-control-row">
              <label className="settings-field"><span>API key</span><input type="password" autoComplete="off" value={openalexApiKey} placeholder="Leave blank to keep existing" onChange={(event) => setOpenalexApiKey(event.target.value)} /></label>
              <button className="primary" disabled={!openalexApiKey.trim() || saving} onClick={() => void saveOpenAlex()}>{saving ? "Saving..." : "Save"}</button>
              {settings.literature.openalex.apiKeyConfigured ? <button className="secondary danger" disabled={saving} onClick={() => void onUpdate({ openalexApiKey: { operation: "remove" } }).catch(() => undefined)}>Remove</button> : null}
            </div>
          </section>
          <section className="settings-section-block credential-editor">
            <div className="credential-heading">
              <div><h4>Custom</h4><p>Write-only secrets for authenticated MCP Connectors.</p></div>
            </div>
            <div className="service-list credential-provider-list">
              {settings.credentials.custom.map((credential) => (
                <div className="service-row" key={credential.id}>
                  <span><KeyRound size={17} /><strong>{credential.name}</strong><small>{credential.id}</small></span>
                  <span className="credential-row-actions">
                    <span className={`status-chip ${credential.configured ? "ready" : "needs_configuration"}`}>
                      {credential.configured ? "Configured" : "Not configured"}
                    </span>
                    <button
                      className="icon-control danger"
                      aria-label={`Remove ${credential.name}`}
                      title="Remove"
                      disabled={saving}
                      onClick={() => {
                        if (window.confirm(`Remove ${credential.name}? Connectors using it must be detached first.`)) {
                          void onUpdate({ customCredential: { operation: "remove", id: credential.id } }).catch(() => undefined);
                        }
                      }}
                    >
                      <Trash2 size={16} />
                    </button>
                  </span>
                </div>
              ))}
            </div>
            <div className="credential-control-row custom-credential-editor">
              <label className="settings-field"><span>Name</span><input value={customCredentialName} onChange={(event) => setCustomCredentialName(event.target.value)} /></label>
              <label className="settings-field"><span>Credential ID</span><input spellCheck={false} value={customCredentialId} onChange={(event) => setCustomCredentialId(event.target.value)} /></label>
              <label className="settings-field"><span>Secret value</span><input type="password" autoComplete="off" value={customCredentialValue} onChange={(event) => setCustomCredentialValue(event.target.value)} /></label>
              <button className="primary" disabled={!customCredentialId.trim() || !customCredentialName.trim() || !customCredentialValue || saving} onClick={() => void saveCustomCredential()}><Plus size={16} />Add</button>
            </div>
          </section>
          <p className="settings-footnote">Secret values are write-only: existing values are never returned to or rendered by this interface.</p>
        </>
      ) : null}
    </div>
  );
}
