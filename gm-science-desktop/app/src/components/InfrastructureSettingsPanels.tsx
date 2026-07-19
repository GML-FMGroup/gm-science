import { useEffect, useMemo, useState } from "react";
import { Cpu, Network, Plus, RefreshCw, ShieldCheck, Trash2 } from "lucide-react";
import type {
  GmScienceComputeHealth,
  GmScienceComputeTarget,
  GmScienceSettings,
  UpdateGmScienceSettingsInput,
} from "../types";

interface CommonSettingsProps {
  settings: GmScienceSettings | null;
  loading: boolean;
  saving: boolean;
  error: string | null;
  onUpdate: (input: UpdateGmScienceSettingsInput) => Promise<void>;
}

interface ComputeSettingsPanelProps extends CommonSettingsProps {
  onCheck: (targetId: string) => Promise<GmScienceComputeHealth>;
}

function statusLabel(value: string): string {
  return value.replaceAll("_", " ");
}

export function PermissionsSettingsPanel({
  settings,
  loading,
  saving,
  error,
  onUpdate,
}: CommonSettingsProps) {
  const items = settings?.permissions.items ?? [];
  const grantedCount = items.filter((item) => item.granted).length;

  async function setPermission(id: string, granted: boolean): Promise<void> {
    await onUpdate({ permissionGrants: { [id]: granted } });
  }

  async function setAll(granted: boolean): Promise<void> {
    await onUpdate({
      permissionGrants: Object.fromEntries(items.map((item) => [item.id, granted])),
    });
  }

  return (
    <div className="settings-page science-settings-page infrastructure-settings-page">
      <div className="settings-page-title">
        <div><h3>Permissions</h3><p>Durable authorization for Agent and capability registry changes.</p></div>
        <span className="status-chip ready">{grantedCount}/{items.length} granted</span>
      </div>
      {error ? <p className="composer-error">{error}</p> : null}
      <div className="settings-notice">
        <ShieldCheck size={19} />
        <div><strong>Registry authorization</strong><p>These grants are checked by the backend before persistent changes. They do not provide process sandbox isolation.</p></div>
      </div>
      <section className="settings-section-block">
        <div className="infrastructure-section-heading">
          <div><h4>Registry writes</h4><p>Agent, Skill, and Connector mutations that persist across Sessions.</p></div>
          <div className="settings-actions-row">
            <button className="secondary" disabled={saving || items.every((item) => item.granted)} onClick={() => void setAll(true).catch(() => undefined)}>Grant all</button>
            <button className="secondary danger" disabled={saving || items.every((item) => !item.granted)} onClick={() => void setAll(false).catch(() => undefined)}>Revoke all</button>
          </div>
        </div>
        {loading && !settings ? <p>Loading permissions...</p> : null}
        <div className="permission-list governed-permission-list">
          {items.map((item) => (
            <div key={item.id}>
              <span><strong>{item.name}</strong><small>{item.description}</small></span>
              <span className="permission-control">
                <small>Global</small>
                <button
                  className={item.granted ? "capability-switch on" : "capability-switch"}
                  type="button"
                  role="switch"
                  aria-checked={item.granted}
                  aria-label={`Grant ${item.name}`}
                  disabled={saving}
                  onClick={() => void setPermission(item.id, !item.granted).catch(() => undefined)}
                ><span /></button>
              </span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

export function NetworkSettingsPanel({
  settings,
  loading,
  saving,
  error,
  onUpdate,
}: CommonSettingsProps) {
  const [enabled, setEnabled] = useState(true);
  const [enforceAllowlist, setEnforceAllowlist] = useState(true);
  const [allowPrivateNetworks, setAllowPrivateNetworks] = useState(false);
  const [condaMirror, setCondaMirror] = useState("");
  const [pythonIndex, setPythonIndex] = useState("");
  const [caBundle, setCaBundle] = useState("");
  const [customDomains, setCustomDomains] = useState("");
  const [categoryEnabled, setCategoryEnabled] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!settings) {
      return;
    }
    setEnabled(settings.network.enabled);
    setEnforceAllowlist(settings.network.enforceAllowlist);
    setAllowPrivateNetworks(settings.network.allowPrivateNetworks);
    setCondaMirror(settings.network.packageMirrors.condaChannelMirror);
    setPythonIndex(settings.network.packageMirrors.pythonPackageIndex);
    setCaBundle(settings.network.packageMirrors.caBundlePath);
    setCustomDomains(settings.network.customDomains.join("\n"));
    setCategoryEnabled(Object.fromEntries(settings.network.categories.map((item) => [item.id, item.enabled])));
  }, [settings]);

  async function save(): Promise<void> {
    await onUpdate({
      network: {
        enabled,
        enforceAllowlist,
        allowPrivateNetworks,
        condaChannelMirror: condaMirror.trim(),
        pythonPackageIndex: pythonIndex.trim(),
        caBundlePath: caBundle.trim(),
        categoryEnabled,
        customDomains: customDomains.split(/[\n,]/).map((item) => item.trim()).filter(Boolean),
      },
    });
  }

  return (
    <div className="settings-page science-settings-page infrastructure-settings-page">
      <div className="settings-page-title">
        <div><h3>Network</h3><p>Package mirrors and outbound domains used by managed research tools.</p></div>
        <button className="primary" disabled={!settings || saving} onClick={() => void save().catch(() => undefined)}>{saving ? "Saving..." : "Save"}</button>
      </div>
      {error ? <p className="composer-error">{error}</p> : null}
      {loading && !settings ? <p>Loading Network settings...</p> : null}
      {settings ? (
        <>
          <section className="settings-section-block">
            <div className="network-master-controls">
              <label><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />Enable managed network access</label>
              <label><input type="checkbox" checked={enforceAllowlist} onChange={(event) => setEnforceAllowlist(event.target.checked)} />Enforce domain allowlist</label>
              <label><input type="checkbox" checked={allowPrivateNetworks} onChange={(event) => setAllowPrivateNetworks(event.target.checked)} />Allow private network hosts</label>
            </div>
          </section>
          <section className="settings-section-block">
            <div className="infrastructure-section-heading"><div><h4>Package mirror</h4><p>Managed local runs inherit these package and TLS settings.</p></div><Network size={20} /></div>
            <div className="connection-fields network-fields">
              <label className="settings-field full"><span>Conda channel mirror</span><input aria-label="Conda channel mirror" value={condaMirror} placeholder="https://artifactory.example.com/conda" onChange={(event) => setCondaMirror(event.target.value)} /></label>
              <label className="settings-field full"><span>Python package index (pip)</span><input aria-label="Python package index" value={pythonIndex} placeholder="https://artifactory.example.com/pypi/simple" onChange={(event) => setPythonIndex(event.target.value)} /></label>
              <label className="settings-field full"><span>CA bundle path</span><input aria-label="CA bundle path" value={caBundle} placeholder="/opt/corp/ca-bundle.pem" onChange={(event) => setCaBundle(event.target.value)} /></label>
            </div>
          </section>
          <section className="settings-section-block">
            <h4>gm-science domains</h4>
            <div className="network-category-list">
              {settings.network.categories.map((category) => (
                <div className="network-category-row" key={category.id}>
                  <div><strong>{category.name}</strong><p>{category.description}</p><small>{category.domains.length > 0 ? category.domains.join(", ") : "No configured domains"}</small></div>
                  <button className={categoryEnabled[category.id] ? "capability-switch on" : "capability-switch"} type="button" role="switch" aria-checked={categoryEnabled[category.id] ?? false} aria-label={`Enable ${category.name}`} onClick={() => setCategoryEnabled((current) => ({ ...current, [category.id]: !current[category.id] }))}><span /></button>
                </div>
              ))}
            </div>
          </section>
          <section className="settings-section-block">
            <label className="settings-field"><span>Custom domains</span><textarea aria-label="Custom Network domains" rows={5} value={customDomains} placeholder={"data.example.org\n*.lab.example.org"} onChange={(event) => setCustomDomains(event.target.value)} /></label>
            <p className="settings-footnote">{settings.network.enforcementBoundary}</p>
          </section>
        </>
      ) : null}
    </div>
  );
}

type TargetForm = {
  id: string;
  type: "ssh" | "model_endpoint";
  name: string;
  host: string;
  port: string;
  username: string;
  identityFile: string;
  url: string;
  healthPath: string;
  apiKey: string;
};

const EMPTY_TARGET: TargetForm = {
  id: "",
  type: "ssh",
  name: "",
  host: "",
  port: "22",
  username: "",
  identityFile: "",
  url: "",
  healthPath: "/health",
  apiKey: "",
};

function metadataText(target: GmScienceComputeTarget, name: string): string {
  const value = target.metadata[name];
  return typeof value === "string" || typeof value === "number" ? String(value) : "";
}

function ComputeTargetRow({
  target,
  checking,
  health,
  onCheck,
  onRemove,
}: {
  target: GmScienceComputeTarget;
  checking: boolean;
  health?: GmScienceComputeHealth;
  onCheck: () => void;
  onRemove?: () => void;
}) {
  const location = target.type === "ssh"
    ? [metadataText(target, "username"), metadataText(target, "host")].filter(Boolean).join("@")
    : metadataText(target, "url");
  return (
    <div className="compute-target-row">
      <div className="compute-target-copy"><strong>{target.name}</strong>{location ? <small>{location}</small> : null}<p>{health?.detail ?? target.statusDetail}</p></div>
      <span className={`status-chip ${health?.status ?? target.status}`}>{statusLabel(health?.status ?? target.status)}</span>
      <button className="secondary icon-text-button" disabled={checking} onClick={onCheck}><RefreshCw size={15} />{checking ? "Checking" : "Check"}</button>
      {onRemove ? <button className="icon-control danger" aria-label={`Remove ${target.name}`} title={`Remove ${target.name}`} onClick={onRemove}><Trash2 size={16} /></button> : null}
    </div>
  );
}

export function ComputeSettingsPanel({
  settings,
  loading,
  saving,
  error,
  onUpdate,
  onCheck,
}: ComputeSettingsPanelProps) {
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState<TargetForm>(EMPTY_TARGET);
  const [checkingId, setCheckingId] = useState("");
  const [checkError, setCheckError] = useState<string | null>(null);
  const [healthById, setHealthById] = useState<Record<string, GmScienceComputeHealth>>({});
  const targets = settings?.compute.targets ?? [];
  const groups = useMemo(() => ({
    local: targets.filter((item) => item.type === "local"),
    ssh: targets.filter((item) => item.type === "ssh"),
    cloud: targets.filter((item) => item.type === "cloud_provider"),
    endpoint: targets.filter((item) => item.type === "model_endpoint"),
  }), [targets]);

  async function check(targetId: string): Promise<void> {
    setCheckingId(targetId);
    setCheckError(null);
    try {
      const health = await onCheck(targetId);
      setHealthById((current) => ({ ...current, [targetId]: health }));
    } catch (nextError) {
      setCheckError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setCheckingId("");
    }
  }

  async function addTarget(): Promise<void> {
    await onUpdate({
      computeTarget: {
        operation: "upsert",
        target: {
          id: form.id.trim(),
          type: form.type,
          name: form.name.trim(),
          enabled: true,
          host: form.type === "ssh" ? form.host.trim() : undefined,
          port: form.type === "ssh" ? Number(form.port || 22) : undefined,
          username: form.type === "ssh" ? form.username.trim() : undefined,
          identityFile: form.type === "ssh" ? form.identityFile.trim() : undefined,
          url: form.type === "model_endpoint" ? form.url.trim() : undefined,
          healthPath: form.type === "model_endpoint" ? form.healthPath.trim() : undefined,
          apiKey: form.type === "model_endpoint" && form.apiKey.trim() ? { operation: "replace", value: form.apiKey.trim() } : undefined,
        },
      },
    });
    setAdding(false);
    setForm(EMPTY_TARGET);
  }

  async function removeTarget(target: GmScienceComputeTarget): Promise<void> {
    if (!window.confirm(`Remove Compute Target "${target.name}"? Stored target credentials will also be removed.`)) {
      return;
    }
    await onUpdate({ computeTarget: { operation: "remove", id: target.id } });
  }

  function rows(items: GmScienceComputeTarget[]) {
    return items.map((target) => (
      <ComputeTargetRow
        key={target.id}
        target={target}
        checking={checkingId === target.id}
        health={healthById[target.id]}
        onCheck={() => void check(target.id).catch(() => undefined)}
        onRemove={target.id === "local" || target.id === "modal" || target.id === "nvidia_bionemo_nim" ? undefined : () => void removeTarget(target).catch(() => undefined)}
      />
    ));
  }

  return (
    <div className="settings-page science-settings-page infrastructure-settings-page">
      <div className="settings-page-title">
        <div><h3>Compute</h3><p>Local execution, SSH hosts, cloud providers, and model endpoints.</p></div>
        <button className="secondary icon-text-button" disabled={adding || saving} onClick={() => setAdding(true)}><Plus size={16} />Add target</button>
      </div>
      {error || checkError ? <p className="composer-error">{error ?? checkError}</p> : null}
      {loading && !settings ? <p>Loading Compute Targets...</p> : null}
      {adding ? (
        <section className="settings-section-block compute-target-editor">
          <div className="infrastructure-section-heading"><div><h4>New Compute Target</h4><p>Remote targets are registered and checked now; execution remains Local until an adapter is implemented.</p></div></div>
          <div className="connection-fields">
            <label className="settings-field"><span>Type</span><select value={form.type} onChange={(event) => setForm((current) => ({ ...current, type: event.target.value === "model_endpoint" ? "model_endpoint" : "ssh" }))}><option value="ssh">SSH host</option><option value="model_endpoint">Model endpoint</option></select></label>
            <label className="settings-field"><span>ID</span><input aria-label="Compute Target ID" value={form.id} placeholder="lab_cluster" onChange={(event) => setForm((current) => ({ ...current, id: event.target.value }))} /></label>
            <label className="settings-field full"><span>Name</span><input aria-label="Compute Target name" value={form.name} placeholder="Lab cluster" onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} /></label>
            {form.type === "ssh" ? <><label className="settings-field"><span>Host</span><input aria-label="SSH host" value={form.host} onChange={(event) => setForm((current) => ({ ...current, host: event.target.value }))} /></label><label className="settings-field"><span>Port</span><input aria-label="SSH port" inputMode="numeric" value={form.port} onChange={(event) => setForm((current) => ({ ...current, port: event.target.value }))} /></label><label className="settings-field"><span>Username</span><input aria-label="SSH username" value={form.username} onChange={(event) => setForm((current) => ({ ...current, username: event.target.value }))} /></label><label className="settings-field"><span>Identity file</span><input aria-label="SSH identity file" value={form.identityFile} placeholder="~/.ssh/id_ed25519" onChange={(event) => setForm((current) => ({ ...current, identityFile: event.target.value }))} /></label></> : <><label className="settings-field full"><span>Endpoint URL</span><input aria-label="Model endpoint URL" value={form.url} placeholder="https://nim.example.org/v1" onChange={(event) => setForm((current) => ({ ...current, url: event.target.value }))} /></label><label className="settings-field"><span>Health path</span><input aria-label="Model endpoint health path" value={form.healthPath} onChange={(event) => setForm((current) => ({ ...current, healthPath: event.target.value }))} /></label><label className="settings-field"><span>API key</span><input aria-label="Model endpoint API key" type="password" autoComplete="off" value={form.apiKey} onChange={(event) => setForm((current) => ({ ...current, apiKey: event.target.value }))} /></label></>}
          </div>
          <div className="settings-actions-row"><button className="secondary" onClick={() => { setAdding(false); setForm(EMPTY_TARGET); }}>Cancel</button><button className="primary" disabled={saving || !form.id.trim() || !form.name.trim() || (form.type === "ssh" ? !form.host.trim() : !form.url.trim())} onClick={() => void addTarget().catch(() => undefined)}>{saving ? "Saving..." : "Add"}</button></div>
        </section>
      ) : null}
      {settings ? <>
        <section className="settings-section-block"><div className="infrastructure-section-heading"><div><h4>Local</h4><p>Managed Python TaskRun on this computer.</p></div><Cpu size={20} /></div>{rows(groups.local)}</section>
        <section className="settings-section-block"><h4>SSH hosts</h4>{groups.ssh.length > 0 ? rows(groups.ssh) : <p className="muted-value">No SSH hosts configured.</p>}</section>
        <section className="settings-section-block"><h4>Cloud providers</h4>{rows(groups.cloud)}</section>
        <section className="settings-section-block"><h4>Model endpoints</h4>{rows(groups.endpoint)}</section>
      </> : null}
    </div>
  );
}
