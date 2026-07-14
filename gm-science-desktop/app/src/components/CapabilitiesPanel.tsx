import type { GmScienceCapability, GmScienceCapabilityKind } from "../types";

interface CapabilitiesPanelProps {
  kind: GmScienceCapabilityKind;
  projectName: string;
  items: GmScienceCapability[];
  loading: boolean;
  saving: boolean;
  dirty: boolean;
  error: string | null;
  onToggle: (capabilityId: string) => void;
  onSave: () => void;
  onRefresh: () => void;
}

const headings: Record<GmScienceCapabilityKind, string> = {
  skill: "Skills",
  connector: "Connectors",
  specialist: "Specialists",
};

function statusLabel(status: GmScienceCapability["status"]): string {
  if (status === "needs_configuration") {
    return "Needs configuration";
  }
  return status === "ready" ? "Ready" : "Disabled";
}

export function CapabilitiesPanel({
  kind,
  projectName,
  items,
  loading,
  saving,
  dirty,
  error,
  onToggle,
  onSave,
  onRefresh,
}: CapabilitiesPanelProps) {
  const visibleItems = items.filter((item) => item.kind === kind);
  const hasProject = Boolean(projectName);

  return (
    <section className="capabilities-panel" aria-labelledby="capabilities-heading">
      <header className="capabilities-panel-header">
        <div>
          <h2 id="capabilities-heading">{headings[kind]}</h2>
          <p>{hasProject ? projectName : "Global capability status"}</p>
        </div>
        <div className="capability-actions">
          <button className="secondary" onClick={onRefresh} disabled={loading || saving}>
            Refresh
          </button>
          {hasProject ? (
            <button className="primary" onClick={onSave} disabled={!dirty || saving || loading}>
              {saving ? "Saving..." : "Save changes"}
            </button>
          ) : null}
        </div>
      </header>

      {error ? <p className="composer-error capability-error">{error}</p> : null}
      {loading ? <div className="capability-empty">Loading capabilities...</div> : null}
      {!loading && visibleItems.length === 0 ? <div className="capability-empty">No capabilities available.</div> : null}

      <div className="capability-list">
        {visibleItems.map((item) => {
          const checked = item.projectEnabled ?? item.defaultEnabled;
          const cannotEnable = !item.available && !checked;
          return (
            <article className="capability-row" key={item.id}>
              <div className="capability-copy">
                <div className="capability-title-row">
                  <strong>{item.name}</strong>
                  <span className={`capability-status ${item.status}`}>{statusLabel(item.status)}</span>
                  {item.metadata.auto_dispatch === true ? <span className="capability-tag">Auto</span> : null}
                </div>
                <p>{item.description}</p>
                {item.statusDetail ? <small>{item.statusDetail}</small> : null}
              </div>
              <button
                className={checked ? "capability-switch on" : "capability-switch"}
                type="button"
                role="switch"
                aria-checked={checked}
                aria-label={`Enable ${item.name}`}
                disabled={!hasProject || saving || cannotEnable}
                onClick={() => onToggle(item.id)}
              >
                <span />
              </button>
            </article>
          );
        })}
      </div>
    </section>
  );
}
