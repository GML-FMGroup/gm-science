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

function metadataText(item: GmScienceCapability, key: string): string {
  const value = item.metadata[key];
  return typeof value === "string" || typeof value === "number" ? String(value) : "";
}

function metadataList(item: GmScienceCapability, key: string): string[] {
  const value = item.metadata[key];
  return Array.isArray(value) ? value.filter((entry): entry is string => typeof entry === "string") : [];
}

function SkillDetails({ item }: { item: GmScienceCapability }) {
  return (
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
  );
}

function McpConnectorDetails({ item }: { item: GmScienceCapability }) {
  const environmentNames = metadataList(item, "configured_env_names");
  const configuredHeaderNames = metadataList(item, "configured_header_names");
  const runtimeHeaderNames = metadataList(item, "runtime_header_names");
  const headerNames = [...new Set([...configuredHeaderNames, ...runtimeHeaderNames])];
  const toolFilter = metadataList(item, "tool_filter");
  const connection =
    metadataText(item, "command_name") || metadataText(item, "endpoint_origin") || "Not configured";

  return (
    <div className="capability-details" id={`capability-details-${item.id}`}>
      <dl>
        <div>
          <dt>Identifier</dt>
          <dd>{item.id}</dd>
        </div>
        <div>
          <dt>Transport</dt>
          <dd>{metadataText(item, "transport") || "Not configured"}</dd>
        </div>
        <div>
          <dt>Tool prefix</dt>
          <dd>{metadataText(item, "tool_prefix") || "Not configured"}</dd>
        </div>
        <div>
          <dt>Connection</dt>
          <dd>{connection}</dd>
        </div>
        <div>
          <dt>Confirmation</dt>
          <dd>{item.metadata.require_confirmation === true ? "Required" : "Not required"}</dd>
        </div>
      </dl>
      {toolFilter.length > 0 ? (
        <div className="capability-files">
          <strong>Allowed tools</strong>
          <ul>
            {toolFilter.map((name) => (
              <li key={name}>{name}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="capability-detail-lists">
        <div className="capability-files">
          <strong>Environment variables</strong>
          {environmentNames.length > 0 ? (
            <ul>
              {environmentNames.map((name) => (
                <li key={name}>{name}</li>
              ))}
            </ul>
          ) : (
            <span>None configured</span>
          )}
        </div>
        <div className="capability-files">
          <strong>HTTP headers</strong>
          {headerNames.length > 0 ? (
            <ul>
              {headerNames.map((name) => (
                <li key={name}>{name}</li>
              ))}
            </ul>
          ) : (
            <span>None configured</span>
          )}
        </div>
      </div>
    </div>
  );
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
        return `${item.name} ${item.id} ${item.description} ${sourceLabels[item.source]} ${metadataText(
          item,
          "server_name",
        )} ${metadataText(item, "transport")}`
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
          <span>{visibleItems.length} shown</span>
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
                const isMcpConnector = kind === "connector" && item.metadata.connector_type === "mcp";
                const hasDetails = kind === "skill" || isMcpConnector;
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
                      {expanded && kind === "skill" ? <SkillDetails item={item} /> : null}
                      {expanded && isMcpConnector ? <McpConnectorDetails item={item} /> : null}
                    </div>
                    <div className="capability-controls">
                      {hasDetails ? (
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
