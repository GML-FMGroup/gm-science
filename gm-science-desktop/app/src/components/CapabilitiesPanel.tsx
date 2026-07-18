import { useMemo, useState } from "react";
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

const sourceOrder: GmScienceCapability["source"][] = ["built_in", "local", "external"];

const sourceLabels: Record<GmScienceCapability["source"], string> = {
  built_in: "Built-in",
  local: "Local",
  external: "External",
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
  const [query, setQuery] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const visibleItems = useMemo(
    () =>
      items.filter((item) => {
        if (item.kind !== kind) {
          return false;
        }
        if (!normalizedQuery) {
          return true;
        }
        return `${item.name} ${item.id} ${item.description} ${sourceLabels[item.source]}`
          .toLocaleLowerCase()
          .includes(normalizedQuery);
      }),
    [items, kind, normalizedQuery],
  );
  const groups = sourceOrder
    .map((source) => ({ source, items: visibleItems.filter((item) => item.source === source) }))
    .filter((group) => group.items.length > 0);
  const hasProject = Boolean(projectName);
  const searchLabel = `Search ${headings[kind].toLocaleLowerCase()}`;

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
      {!loading ? (
        <div className="capability-toolbar">
          <input
            type="search"
            value={query}
            aria-label={searchLabel}
            placeholder={`${searchLabel}...`}
            onChange={(event) => setQuery(event.target.value)}
          />
          <span>{visibleItems.length} available</span>
        </div>
      ) : null}
      {!loading && visibleItems.length === 0 ? (
        <div className="capability-empty">
          {normalizedQuery ? `No matching ${headings[kind].toLocaleLowerCase()}.` : "No capabilities available."}
        </div>
      ) : null}

      <div className="capability-groups">
        {groups.map((group) => (
          <section
            className="capability-group"
            key={group.source}
            aria-labelledby={`${kind}-${group.source}-heading`}
          >
            <h3 id={`${kind}-${group.source}-heading`}>
              <span>{sourceLabels[group.source]}</span>
              <small>{group.items.length}</small>
            </h3>
            <div className="capability-list">
              {group.items.map((item) => {
                const checked = item.projectEnabled ?? item.defaultEnabled;
                const cannotEnable = !item.available && !checked;
                const expanded = expandedId === item.id;
                return (
                  <article className="capability-row" key={item.id}>
                    <div className="capability-copy">
                      <div className="capability-title-row">
                        <strong>{item.name}</strong>
                        <span className={`capability-source ${item.source}`}>{sourceLabels[item.source]}</span>
                        <span className={`capability-status ${item.status}`}>{statusLabel(item.status)}</span>
                        {item.metadata.auto_dispatch === true ? <span className="capability-tag">Auto</span> : null}
                      </div>
                      <p>{item.description}</p>
                      {item.statusDetail ? <small>{item.statusDetail}</small> : null}
                      {expanded ? (
                        <div className="capability-details" id={`capability-details-${item.id}`}>
                          <dl>
                            <div>
                              <dt>Identifier</dt>
                              <dd>{item.id}</dd>
                            </div>
                            <div>
                              <dt>Version</dt>
                              <dd>{item.version || "Not declared"}</dd>
                            </div>
                            <div>
                              <dt>License</dt>
                              <dd>{item.license || "Not declared"}</dd>
                            </div>
                          </dl>
                          <div className="capability-files">
                            <strong>Files</strong>
                            {item.files.length > 0 ? (
                              <ul>
                                {item.files.map((file) => (
                                  <li key={file}>{file}</li>
                                ))}
                              </ul>
                            ) : (
                              <span>No files reported</span>
                            )}
                          </div>
                        </div>
                      ) : null}
                    </div>
                    <div className="capability-controls">
                      {kind === "skill" ? (
                        <button
                          className="capability-details-button"
                          type="button"
                          aria-expanded={expanded}
                          aria-controls={`capability-details-${item.id}`}
                          aria-label={`${expanded ? "Hide" : "Show"} details for ${item.name}`}
                          onClick={() => setExpandedId(expanded ? null : item.id)}
                        >
                          {expanded ? "Hide" : "Details"}
                        </button>
                      ) : null}
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
                    </div>
                  </article>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </section>
  );
}
