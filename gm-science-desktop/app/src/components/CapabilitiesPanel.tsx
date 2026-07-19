import { useMemo, useState } from "react";
import { Plus, RefreshCw } from "lucide-react";
import type { GmScienceCapability, GmScienceCapabilityKind } from "../types";

interface CapabilitiesPanelProps {
  kind: GmScienceCapabilityKind;
  items: GmScienceCapability[];
  loading: boolean;
  saving: boolean;
  error: string | null;
  onToggle: (capabilityId: string) => void;
  onRefresh: () => void;
  onAdd: () => void;
}

const headings: Record<GmScienceCapabilityKind, string> = {
  skill: "Skills",
  connector: "Connectors",
  specialist: "Specialists",
};

const groupOrder: Record<GmScienceCapabilityKind, string[]> = {
  skill: ["featured", "imported", "personal"],
  connector: ["featured", "directory", "native", "organization", "custom"],
  specialist: ["built_in", "organization", "custom"],
};

const groupLabels: Record<GmScienceCapabilityKind, Record<string, string>> = {
  skill: { featured: "Featured", imported: "Imported", personal: "Personal" },
  connector: {
    featured: "Featured",
    directory: "Directory",
    native: "Native",
    organization: "Organization",
    custom: "Custom",
  },
  specialist: { built_in: "Built-in", organization: "Organization", custom: "Custom" },
};

function capabilityGroup(item: GmScienceCapability, kind: GmScienceCapabilityKind): string {
  const explicit = metadataText(item, "catalog_group");
  if (explicit && groupOrder[kind].includes(explicit)) {
    return explicit;
  }
  if (kind === "skill") {
    return item.source === "built_in" ? "featured" : item.source === "external" ? "imported" : "personal";
  }
  if (kind === "connector") {
    return item.source === "built_in" ? "featured" : item.source === "external" ? "directory" : "custom";
  }
  return item.source === "built_in" ? "built_in" : item.source === "external" ? "organization" : "custom";
}

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

function accessLabel(value: unknown): string {
  return value === true ? "Allowed" : "Not allowed";
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

function SpecialistDetails({ item }: { item: GmScienceCapability }) {
  const assignedSkills = metadataList(item, "assigned_skills");
  const assignedConnectors = metadataList(item, "assigned_connectors");
  const instructions = metadataText(item, "additional_instructions");

  return (
    <div className="capability-details" id={`capability-details-${item.id}`}>
      <dl>
        <div>
          <dt>Agent ID</dt>
          <dd>{item.id}</dd>
        </div>
        <div>
          <dt>Model</dt>
          <dd>{metadataText(item, "model") || "inherit"}</dd>
        </div>
        <div>
          <dt>Execution</dt>
          <dd>{metadataText(item, "execution_mode") || "agent_tool"}</dd>
        </div>
        <div>
          <dt>Network</dt>
          <dd>{accessLabel(item.metadata.network_access)}</dd>
        </div>
        <div>
          <dt>Shell</dt>
          <dd>{accessLabel(item.metadata.shell_access)}</dd>
        </div>
        <div>
          <dt>Read-only</dt>
          <dd>{item.metadata.read_only === true ? "Yes" : "No"}</dd>
        </div>
      </dl>
      {instructions ? (
        <div className="capability-instructions">
          <strong>Additional instructions</strong>
          <p>{instructions}</p>
        </div>
      ) : null}
      <div className="capability-detail-lists">
        <div className="capability-files">
          <strong>Assigned Skills</strong>
          {assignedSkills.length > 0 ? (
            <ul>
              {assignedSkills.map((name) => (
                <li key={name}>{name}</li>
              ))}
            </ul>
          ) : (
            <span>None assigned</span>
          )}
        </div>
        <div className="capability-files">
          <strong>Assigned Connectors</strong>
          {assignedConnectors.length > 0 ? (
            <ul>
              {assignedConnectors.map((name) => (
                <li key={name}>{name}</li>
              ))}
            </ul>
          ) : (
            <span>None assigned</span>
          )}
        </div>
      </div>
    </div>
  );
}

export function CapabilitiesPanel({
  kind,
  items,
  loading,
  saving,
  error,
  onToggle,
  onRefresh,
  onAdd,
}: CapabilitiesPanelProps) {
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const kindItems = useMemo(() => items.filter((item) => item.kind === kind), [items, kind]);
  const visibleItems = useMemo(
    () =>
      kindItems.filter((item) => {
        if (statusFilter === "available" && !item.available) {
          return false;
        }
        if (statusFilter === "needs_configuration" && item.status !== "needs_configuration") {
          return false;
        }
        if (statusFilter === "unavailable" && item.available) {
          return false;
        }
        if (!normalizedQuery) {
          return true;
        }
        return `${item.name} ${item.id} ${item.description} ${groupLabels[kind][capabilityGroup(item, kind)]} ${metadataText(
          item,
          "server_name",
        )} ${metadataText(item, "transport")} ${metadataList(item, "assigned_skills").join(" ")} ${metadataList(
          item,
          "assigned_connectors",
        ).join(" ")}`
          .toLocaleLowerCase()
          .includes(normalizedQuery);
      }),
    [kindItems, kind, normalizedQuery, statusFilter],
  );
  const groups = groupOrder[kind]
    .map((groupId) => ({
      id: groupId,
      label: groupLabels[kind][groupId],
      items: visibleItems.filter((item) => capabilityGroup(item, kind) === groupId),
    }))
    .filter((group) => group.items.length > 0);
  const hasProject = items.some((item) => item.projectEnabled !== null);
  const searchLabel = `Search ${headings[kind].toLocaleLowerCase()}`;

  return (
    <section className="capabilities-panel" aria-label={headings[kind]}>
      {error ? <p className="composer-error capability-error">{error}</p> : null}
      {loading ? <div className="capability-empty">Loading capabilities...</div> : null}
      {!loading ? (
        <div className="capability-toolbar">
          <select
            aria-label={`Filter ${headings[kind].toLocaleLowerCase()}`}
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
          >
            <option value="all">All ({kindItems.length})</option>
            <option value="available">Available</option>
            <option value="needs_configuration">Needs configuration</option>
            <option value="unavailable">Unavailable</option>
          </select>
          <input
            type="search"
            value={query}
            aria-label={searchLabel}
            placeholder={`${searchLabel}...`}
            onChange={(event) => setQuery(event.target.value)}
          />
          <button
            className="icon-control"
            type="button"
            aria-label={`Refresh ${headings[kind].toLocaleLowerCase()}`}
            title={`Refresh ${headings[kind].toLocaleLowerCase()}`}
            onClick={onRefresh}
            disabled={loading || saving}
          >
            <RefreshCw size={16} />
          </button>
          <button className="secondary small capability-add-button" type="button" onClick={onAdd} disabled={saving}>
            <Plus size={15} />Add {kind}
          </button>
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
            key={group.id}
            aria-labelledby={`${kind}-${group.id}-heading`}
          >
            <h3 id={`${kind}-${group.id}-heading`}>
              <span>{group.label}</span>
              <small>{group.items.length}</small>
            </h3>
            <div className="capability-list">
              {group.items.map((item) => {
                const checked = item.projectEnabled ?? item.defaultEnabled;
                const cannotEnable = !item.available && !checked;
                const expanded = expandedId === item.id;
                const isMcpConnector = kind === "connector" && item.metadata.connector_type === "mcp";
                const hasDetails = kind === "skill" || kind === "specialist" || isMcpConnector;
                return (
                  <article className="capability-row" key={item.id}>
                    <div className="capability-copy">
                      <div className="capability-title-row">
                        <strong>{item.name}</strong>
                        <span className={`capability-source ${item.source}`}>{group.label}</span>
                        <span className={`capability-status ${item.status}`}>{statusLabel(item.status)}</span>
                        {item.metadata.auto_dispatch === true ? <span className="capability-tag">Auto</span> : null}
                      </div>
                      <p>{item.description}</p>
                      {item.statusDetail ? <small>{item.statusDetail}</small> : null}
                      {expanded && kind === "skill" ? <SkillDetails item={item} /> : null}
                      {expanded && isMcpConnector ? <McpConnectorDetails item={item} /> : null}
                      {expanded && kind === "specialist" ? <SpecialistDetails item={item} /> : null}
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
