import {
  Activity,
  Cloud,
  Database,
  FolderOpen,
  HardDrive,
  RefreshCw,
  Timer,
  TriangleAlert,
} from "lucide-react";
import type {
  GmScienceStorageSnapshot,
  GmScienceUsageSnapshot,
  GmScienceUsageWindow,
} from "../types";

interface StorageSettingsPanelProps {
  snapshot: GmScienceStorageSnapshot | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => Promise<void>;
}

interface UsageSettingsPanelProps {
  snapshot: GmScienceUsageSnapshot | null;
  window: GmScienceUsageWindow;
  loading: boolean;
  error: string | null;
  onWindowChange: (window: GmScienceUsageWindow) => void;
  onRefresh: () => Promise<void>;
}

const WINDOW_LABELS: Array<{ id: GmScienceUsageWindow; label: string }> = [
  { id: "24h", label: "24h" },
  { id: "7d", label: "7 days" },
  { id: "30d", label: "30 days" },
];

function formatBytes(value: number): string {
  const safeValue = Math.max(0, value);
  if (safeValue < 1024) {
    return `${safeValue} B`;
  }
  const units = ["KB", "MB", "GB", "TB"];
  let shown = safeValue / 1024;
  let unitIndex = 0;
  while (shown >= 1024 && unitIndex < units.length - 1) {
    shown /= 1024;
    unitIndex += 1;
  }
  return `${shown >= 10 ? shown.toFixed(1) : shown.toFixed(2)} ${units[unitIndex]}`;
}

function formatCount(value: number): string {
  return new Intl.NumberFormat("en-US", { notation: value >= 100_000 ? "compact" : "standard" }).format(value);
}

function formatDuration(value: number): string {
  const totalSeconds = Math.floor(Math.max(0, value) / 1000);
  if (totalSeconds < 60) {
    return `${totalSeconds}s`;
  }
  const minutes = Math.floor(totalSeconds / 60);
  if (minutes < 60) {
    return `${minutes}m ${totalSeconds % 60}s`;
  }
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

function refreshButton(loading: boolean, onRefresh: () => Promise<void>, label: string) {
  return (
    <button
      className="icon-button"
      type="button"
      aria-label={label}
      title={label}
      disabled={loading}
      onClick={() => void onRefresh().catch(() => undefined)}
    >
      <RefreshCw size={16} className={loading ? "spin" : ""} />
    </button>
  );
}

export function StorageSettingsPanel({
  snapshot,
  loading,
  error,
  onRefresh,
}: StorageSettingsPanelProps) {
  return (
    <div className="settings-page science-settings-page observability-settings-page">
      <div className="settings-page-title">
        <div><h3>Storage</h3><p>Projects, files, and history stored on this computer.</p></div>
        {refreshButton(loading, onRefresh, "Refresh storage usage")}
      </div>
      {error ? <p className="composer-error">{error}</p> : null}
      <section className="settings-section-block observability-location-row">
        <div>
          <h4>Data location</h4>
          <p className="path-value">{snapshot?.dataLocation || "Loading local data location..."}</p>
          {snapshot ? (
            <small>{snapshot.writable ? "Writable" : "Read only"} · {snapshot.totalFiles.toLocaleString()} files</small>
          ) : null}
        </div>
        <HardDrive size={21} />
      </section>
      <section className="settings-section-block">
        <div className="observability-section-heading">
          <div><h4>Disk usage</h4><p>{snapshot ? formatBytes(snapshot.totalBytes) : "Scanning..."}</p></div>
          {snapshot ? <span className="muted-value">{snapshot.elapsedMs} ms</span> : null}
        </div>
        {!snapshot && loading ? <div className="observability-empty"><Activity size={18} /><span>Scanning local data...</span></div> : null}
        {snapshot ? (
          <div className="storage-breakdown-list">
            {snapshot.categories.map((category) => {
              const share = snapshot.totalBytes > 0 ? (category.bytes / snapshot.totalBytes) * 100 : 0;
              return (
                <div className="storage-breakdown-row" key={category.id}>
                  <span className="storage-category-icon">
                    {category.id === "workspaces" ? <FolderOpen size={16} /> : <Database size={16} />}
                  </span>
                  <div>
                    <span><strong>{category.name}</strong><small>{category.files.toLocaleString()} files</small></span>
                    <div className="usage-bar" aria-hidden="true"><span style={{ width: `${Math.max(0, Math.min(100, share))}%` }} /></div>
                  </div>
                  <strong>{formatBytes(category.bytes)}</strong>
                </div>
              );
            })}
          </div>
        ) : null}
        {snapshot && !snapshot.scanComplete ? (
          <div className="settings-notice warning"><TriangleAlert size={18} /><div><strong>Partial scan</strong><p>{snapshot.partialReason}</p></div></div>
        ) : null}
        {(snapshot?.issues ?? []).map((issue) => <p className="settings-inline-error" key={issue}>{issue}</p>)}
      </section>
      <section className="settings-section-block observability-location-row">
        <div><h4>Cloud storage</h4><p>{snapshot?.cloudStorage.detail || "Checking cloud storage support..."}</p></div>
        <Cloud size={20} />
      </section>
    </div>
  );
}

export function UsageSettingsPanel({
  snapshot,
  window,
  loading,
  error,
  onWindowChange,
  onRefresh,
}: UsageSettingsPanelProps) {
  const largestModelTotal = Math.max(0, ...(snapshot?.tokens.byModel.map((item) => item.totalTokens) ?? []));
  return (
    <div className="settings-page science-settings-page observability-settings-page">
      <div className="settings-page-title">
        <div><h3>Usage</h3><p>Locally recorded model and managed runtime activity.</p></div>
        {refreshButton(loading, onRefresh, "Refresh local usage")}
      </div>
      {error ? <p className="composer-error">{error}</p> : null}
      <section className="settings-section-block">
        <div className="observability-section-heading usage-period-heading">
          <div><h4>Where tokens go</h4><p>Local estimate</p></div>
          <div className="segmented-control" aria-label="Usage period">
            {WINDOW_LABELS.map((option) => (
              <button
                key={option.id}
                type="button"
                className={window === option.id ? "active" : ""}
                aria-pressed={window === option.id}
                onClick={() => onWindowChange(option.id)}
              >{option.label}</button>
            ))}
          </div>
        </div>
        {!snapshot && loading ? <div className="observability-empty"><Activity size={18} /><span>Reading local usage...</span></div> : null}
        {snapshot ? (
          <>
            <div className="usage-metric-grid">
              <div><span>Requests</span><strong>{formatCount(snapshot.tokens.requests)}</strong></div>
              <div><span>Input tokens</span><strong>{formatCount(snapshot.tokens.inputTokens)}</strong></div>
              <div><span>Output tokens</span><strong>{formatCount(snapshot.tokens.outputTokens)}</strong></div>
              <div><span>Total tokens</span><strong>{formatCount(snapshot.tokens.totalTokens)}</strong></div>
            </div>
            {snapshot.tokens.byModel.length > 0 ? (
              <div className="usage-model-list">
                {snapshot.tokens.byModel.map((item) => (
                  <div key={`${item.provider}:${item.model}`}>
                    <span><strong>{item.model}</strong><small>{item.provider} · {item.requests} requests</small></span>
                    <div className="usage-bar"><span style={{ width: `${largestModelTotal > 0 ? (item.totalTokens / largestModelTotal) * 100 : 0}%` }} /></div>
                    <strong>{formatCount(item.totalTokens)}</strong>
                  </div>
                ))}
              </div>
            ) : (
              <div className="observability-empty"><Activity size={18} /><span>No recorded model activity in this period.</span></div>
            )}
          </>
        ) : null}
      </section>
      <section className="settings-section-block">
        <div className="observability-section-heading"><div><h4>Managed runs</h4><p>Local TaskRun activity in the selected period.</p></div><Timer size={19} /></div>
        {snapshot ? (
          <>
            <div className="usage-metric-grid runtime-metrics">
              <div><span>Runs</span><strong>{formatCount(snapshot.runs.runs)}</strong></div>
              <div><span>Active</span><strong>{formatCount(snapshot.runs.activeRuns)}</strong></div>
              <div><span>Terminal</span><strong>{formatCount(snapshot.runs.terminalRuns)}</strong></div>
              <div><span>Runtime</span><strong>{formatDuration(snapshot.runs.runtimeMs)}</strong></div>
            </div>
            {snapshot.runs.byStatus.length > 0 ? (
              <div className="usage-status-list">
                {snapshot.runs.byStatus.map((item) => (
                  <div key={item.status}><span>{item.status.replaceAll("_", " ")}</span><strong>{item.runs}</strong></div>
                ))}
              </div>
            ) : null}
          </>
        ) : null}
      </section>
      {snapshot && !snapshot.cost.available ? (
        <div className="settings-notice"><TriangleAlert size={18} /><div><strong>Cost unavailable</strong><p>{snapshot.cost.reason}</p></div></div>
      ) : null}
    </div>
  );
}
