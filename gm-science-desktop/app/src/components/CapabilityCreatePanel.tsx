import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, FolderOpen, GitFork, Plus, Trash2, Upload } from "lucide-react";
import type {
  CreateGmScienceConnectorInput,
  CreateGmScienceSkillInput,
  CreateGmScienceSpecialistInput,
  GmScienceCapability,
  GmScienceCapabilityDefinition,
  GmScienceCapabilityKind,
  GmScienceCustomCredential,
  GmScienceSkillDraft,
  ImportGmScienceSkillInput,
} from "../types";

interface CapabilityCreatePanelProps {
  kind: GmScienceCapabilityKind;
  capabilities: GmScienceCapability[];
  credentials: GmScienceCustomCredential[];
  saving: boolean;
  error: string | null;
  definition?: GmScienceCapabilityDefinition | null;
  draft?: GmScienceSkillDraft | null;
  onCancel: () => void;
  onCreateSkill: (input: CreateGmScienceSkillInput) => Promise<void>;
  onCreateConnector: (input: CreateGmScienceConnectorInput) => Promise<void>;
  onCreateSpecialist: (input: CreateGmScienceSpecialistInput) => Promise<void>;
  onImportSkill: (input: ImportGmScienceSkillInput) => Promise<void>;
  onSaveSkillDraft: (input: CreateGmScienceSkillInput) => Promise<void>;
  onPublishSkillDraft: (draftId: string) => Promise<void>;
  onSelectSkillSource: (mode: "file" | "directory") => Promise<string | null>;
}

const labels: Record<GmScienceCapabilityKind, { title: string; id: string }> = {
  skill: { title: "Add skill", id: "Skill ID" },
  connector: { title: "Add connector", id: "Connector ID" },
  specialist: { title: "Add specialist", id: "Agent ID" },
};

interface SecretBinding {
  key: string;
  name: string;
  value: string;
}

function bindingMap(bindings: SecretBinding[]): Record<string, string> {
  return Object.fromEntries(
    bindings
      .filter((binding) => binding.name.trim() && binding.value)
      .map((binding) => [binding.name.trim(), binding.value]),
  );
}

function SecretBindingsEditor({
  label,
  bindings,
  credentials,
  onChange,
}: {
  label: string;
  bindings: SecretBinding[];
  credentials: GmScienceCustomCredential[];
  onChange: (bindings: SecretBinding[]) => void;
}) {
  return (
    <fieldset className="full connector-secret-field">
      <legend>{label}</legend>
      <div className="connector-secret-list">
        {bindings.map((binding) => (
          <div key={binding.key} className="connector-secret-row">
            <input
              aria-label={`${label} name`}
              placeholder="Name"
              spellCheck={false}
              value={binding.name}
              onChange={(event) => onChange(bindings.map((item) => item.key === binding.key ? { ...item, name: event.target.value } : item))}
            />
            <select
              aria-label={`${label} value`}
              value={binding.value}
              onChange={(event) => onChange(bindings.map((item) => item.key === binding.key ? { ...item, value: event.target.value } : item))}
            >
              <option value="">Select credential</option>
              {credentials.map((credential) => (
                <option key={credential.id} value={credential.id}>{credential.name}</option>
              ))}
            </select>
            <button className="icon-control" type="button" aria-label={`Remove ${label} entry`} title="Remove" onClick={() => onChange(bindings.filter((item) => item.key !== binding.key))}>
              <Trash2 size={16} />
            </button>
          </div>
        ))}
      </div>
      <button className="secondary connector-secret-add" type="button" onClick={() => onChange([...bindings, { key: `${Date.now()}-${bindings.length}`, name: "", value: "" }])}>
        <Plus size={16} /> Add
      </button>
      <small>Connector definitions store credential references only. Manage secret values in Credentials.</small>
    </fieldset>
  );
}

function capabilityId(name: string, kind: GmScienceCapabilityKind): string {
  const separator = kind === "specialist" ? "_" : "-";
  return name
    .normalize("NFKD")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, separator)
    .replace(new RegExp(`^\\${separator}+|\\${separator}+$`, "g"), "")
    .replace(new RegExp(`\\${separator}{2,}`, "g"), separator);
}

export function CapabilityCreatePanel({
  kind,
  capabilities,
  credentials,
  saving,
  error,
  definition = null,
  draft = null,
  onCancel,
  onCreateSkill,
  onCreateConnector,
  onCreateSpecialist,
  onImportSkill,
  onSaveSkillDraft,
  onPublishSkillDraft,
  onSelectSkillSource,
}: CapabilityCreatePanelProps) {
  const [name, setName] = useState("");
  const [id, setId] = useState("");
  const [idEdited, setIdEdited] = useState(false);
  const [description, setDescription] = useState("");
  const [content, setContent] = useState("");
  const [version, setVersion] = useState("");
  const [license, setLicense] = useState("");
  const [instructions, setInstructions] = useState("");
  const [connectionType, setConnectionType] = useState<"remote" | "local">("remote");
  const [url, setUrl] = useState("");
  const [commandLine, setCommandLine] = useState("");
  const [toolFilter, setToolFilter] = useState("");
  const [requireConfirmation, setRequireConfirmation] = useState(false);
  const [headers, setHeaders] = useState<SecretBinding[]>([]);
  const [environment, setEnvironment] = useState<SecretBinding[]>([]);
  const [skills, setSkills] = useState<string[]>([]);
  const [connectors, setConnectors] = useState<string[]>([]);
  const [connectorTools, setConnectorTools] = useState<Record<string, string>>({});
  const [skillMode, setSkillMode] = useState<"write" | "upload" | "github">("write");
  const [sourcePath, setSourcePath] = useState("");
  const [githubUrl, setGithubUrl] = useState("");

  useEffect(() => {
    if (draft) {
      setName(draft.name);
      setId(draft.id);
      setIdEdited(true);
      setDescription(draft.description);
      setContent(draft.content);
      setVersion(draft.version);
      setLicense(draft.license);
      return;
    }
    if (!definition) {
      return;
    }
    setName(definition.name);
    setId(definition.id);
    setIdEdited(true);
    setDescription(definition.description);
    if (definition.kind === "skill") {
      setContent(definition.content);
      setVersion(definition.version);
      setLicense(definition.license);
    } else if (definition.kind === "connector") {
      setConnectionType(definition.connectionType);
      setUrl(definition.url ?? "");
      setCommandLine(definition.commandLine ?? "");
      setToolFilter(definition.toolFilter.join("\n"));
      setRequireConfirmation(definition.requireConfirmation);
      setHeaders(Object.entries(definition.headerCredentialRefs).map(([name, value], index) => ({ key: `header-${index}`, name, value })));
      setEnvironment(Object.entries(definition.environmentCredentialRefs).map(([name, value], index) => ({ key: `environment-${index}`, name, value })));
    } else {
      setInstructions(definition.instructions);
      setSkills(definition.skills);
      setConnectors(definition.connectors);
      setConnectorTools(Object.fromEntries(
        Object.entries(definition.connectorTools).map(([connectorId, tools]) => [connectorId, tools.join("\n")]),
      ));
    }
  }, [definition, draft]);

  useEffect(() => {
    if (!definition && !draft && !idEdited) {
      setId(capabilityId(name, kind));
    }
  }, [definition, draft, idEdited, kind, name]);

  const availableSkills = useMemo(
    () => capabilities.filter((item) => item.kind === "skill" && item.available),
    [capabilities],
  );
  const availableConnectors = useMemo(
    () => capabilities.filter((item) => item.kind === "connector" && item.available),
    [capabilities],
  );
  const valid = Boolean(
    kind === "skill" && !definition && !draft && skillMode === "upload"
      ? sourcePath.trim()
      : kind === "skill" && !definition && !draft && skillMode === "github"
        ? githubUrl.trim()
        : name.trim()
      && id.trim()
      && description.trim()
      && (kind !== "skill" || content.trim())
      && (kind !== "connector" || (connectionType === "remote" ? url.trim() : commandLine.trim()))
      && (kind !== "connector" || (connectionType === "remote" ? headers : environment).every((binding) => Boolean(binding.name.trim() && binding.value)))
      && (kind !== "specialist" || instructions.trim()),
  );
  const draftValid = kind === "skill" && skillMode === "write" && Boolean(name.trim() && id.trim());

  function skillInput(): CreateGmScienceSkillInput {
    return {
      id: id.trim(),
      name: name.trim(),
      description: description.trim(),
      content,
      ...(version.trim() ? { version: version.trim() } : {}),
      ...(license.trim() ? { license: license.trim() } : {}),
    };
  }

  async function submit(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!valid || saving) {
      return;
    }
    if (kind === "skill" && !definition && !draft && skillMode !== "write") {
      await onImportSkill({
        sourceType: skillMode === "upload" ? "local" : "github",
        sourcePath: skillMode === "upload" ? sourcePath.trim() : undefined,
        url: skillMode === "github" ? githubUrl.trim() : undefined,
        id: id.trim() || undefined,
      });
      return;
    }
    if (kind === "skill") {
      if (draft) {
        await onSaveSkillDraft(skillInput());
        await onPublishSkillDraft(draft.id);
      } else {
        await onCreateSkill(skillInput());
      }
      return;
    }
    if (kind === "connector") {
      await onCreateConnector({
        id: id.trim(),
        name: name.trim(),
        description: description.trim(),
        connectionType,
        url: connectionType === "remote" ? url.trim() : undefined,
        commandLine: connectionType === "local" ? commandLine.trim() : undefined,
        toolFilter: toolFilter.split(/[\n,]/).map((value) => value.trim()).filter(Boolean),
        requireConfirmation,
        headerCredentialRefs: connectionType === "remote" ? bindingMap(headers) : undefined,
        environmentCredentialRefs: connectionType === "local" ? bindingMap(environment) : undefined,
      });
      return;
    }
    await onCreateSpecialist({
      id: id.trim(),
      name: name.trim(),
      description: description.trim(),
      instructions,
      skills,
      connectors,
      connectorTools: Object.fromEntries(
        Object.entries(connectorTools)
          .map(([connectorId, tools]) => [
            connectorId,
            tools.split(/[\n,]/).map((value) => value.trim()).filter(Boolean),
          ])
          .filter(([, tools]) => tools.length > 0),
      ),
    });
  }

  function toggle(values: string[], value: string, setter: (next: string[]) => void): void {
    setter(values.includes(value) ? values.filter((item) => item !== value) : [...values, value]);
  }

  function toggleConnector(connectorId: string): void {
    if (connectors.includes(connectorId)) {
      setConnectors(connectors.filter((item) => item !== connectorId));
      setConnectorTools((current) => {
        const next = { ...current };
        delete next[connectorId];
        return next;
      });
      return;
    }
    setConnectors([...connectors, connectorId]);
  }

  return (
    <form className="capability-create-page" aria-label={definition ? `Edit ${kind}` : draft ? "Edit Skill draft" : labels[kind].title} onSubmit={(event) => void submit(event)}>
      <div className="capability-create-heading">
        <button className="icon-control" type="button" onClick={onCancel} aria-label="Back to capability list" title="Back to capability list">
          <ArrowLeft size={18} />
        </button>
        <h3>{definition ? `Edit ${kind}` : draft ? "Edit Skill draft" : labels[kind].title}</h3>
      </div>

      {error ? <p className="composer-error capability-create-error">{error}</p> : null}

      {kind === "skill" && !definition && !draft ? (
        <div className="segmented-control capability-create-mode" aria-label="Skill source">
          <button type="button" className={skillMode === "write" ? "active" : ""} onClick={() => setSkillMode("write")}>Write</button>
          <button type="button" className={skillMode === "upload" ? "active" : ""} onClick={() => setSkillMode("upload")}>Upload</button>
          <button type="button" className={skillMode === "github" ? "active" : ""} onClick={() => setSkillMode("github")}>GitHub</button>
        </div>
      ) : null}

      {kind === "connector" ? (
        <div className="segmented-control capability-create-mode" aria-label="Connector type">
          <button type="button" className={connectionType === "remote" ? "active" : ""} onClick={() => setConnectionType("remote")}>Remote URL</button>
          <button type="button" className={connectionType === "local" ? "active" : ""} onClick={() => setConnectionType("local")}>Local command</button>
        </div>
      ) : null}

      {kind === "skill" && !definition && !draft && skillMode === "upload" ? (
        <div className="capability-import-panel">
          <Upload size={20} />
          <strong>Import a Skill bundle</strong>
          <p>Choose a Skill folder, a SKILL.md file, or a zip bundle. Referenced files are copied into the local registry.</p>
          <div className="capability-import-actions">
            <button className="secondary" type="button" onClick={() => void onSelectSkillSource("directory").then((value) => value && setSourcePath(value))}><FolderOpen size={16} />Choose folder</button>
            <button className="secondary" type="button" onClick={() => void onSelectSkillSource("file").then((value) => value && setSourcePath(value))}><Upload size={16} />Choose file</button>
          </div>
          {sourcePath ? <code>{sourcePath}</code> : null}
          <label>
            <span>Override Skill ID (optional)</span>
            <input value={id} maxLength={64} spellCheck={false} onChange={(event) => { setIdEdited(true); setId(event.target.value); }} />
          </label>
        </div>
      ) : null}

      {kind === "skill" && !definition && !draft && skillMode === "github" ? (
        <div className="capability-import-panel">
          <GitFork size={20} />
          <strong>Import from public GitHub</strong>
          <label>
            <span>Repository or Skill folder URL</span>
            <input autoFocus type="url" value={githubUrl} placeholder="https://github.com/owner/repository/tree/main/skill" onChange={(event) => setGithubUrl(event.target.value)} />
          </label>
          <label>
            <span>Override Skill ID (optional)</span>
            <input value={id} maxLength={64} spellCheck={false} onChange={(event) => { setIdEdited(true); setId(event.target.value); }} />
          </label>
        </div>
      ) : null}

      {kind !== "skill" || definition || skillMode === "write" ? <div className="capability-create-fields">
        <label>
          <span>Name</span>
          <input autoFocus value={name} maxLength={120} onChange={(event) => setName(event.target.value)} />
        </label>
        <label>
          <span>{labels[kind].id}</span>
          <input
            value={id}
            disabled={Boolean(definition || draft)}
            maxLength={64}
            spellCheck={false}
            onChange={(event) => {
              setIdEdited(true);
              setId(event.target.value);
            }}
          />
        </label>
        <label className="full">
          <span>Description</span>
          <textarea value={description} maxLength={2000} rows={3} onChange={(event) => setDescription(event.target.value)} />
        </label>

        {kind === "skill" ? (
          <>
            <label>
              <span>Version</span>
              <input value={version} maxLength={80} onChange={(event) => setVersion(event.target.value)} />
            </label>
            <label>
              <span>License</span>
              <input value={license} maxLength={120} onChange={(event) => setLicense(event.target.value)} />
            </label>
            <label className="full capability-editor-field">
              <span>Markdown content</span>
              <textarea value={content} maxLength={200000} rows={14} spellCheck={false} onChange={(event) => setContent(event.target.value)} />
            </label>
          </>
        ) : null}

        {kind === "connector" && connectionType === "remote" ? (
          <label className="full">
            <span>Remote MCP server URL</span>
            <input type="url" value={url} maxLength={4096} spellCheck={false} onChange={(event) => setUrl(event.target.value)} />
          </label>
        ) : null}

        {kind === "connector" && connectionType === "local" ? (
          <label className="full">
            <span>Command line</span>
            <input value={commandLine} maxLength={8192} spellCheck={false} onChange={(event) => setCommandLine(event.target.value)} />
          </label>
        ) : null}

        {kind === "connector" ? (
          <>
            <label className="full">
              <span>Allowed tools (optional)</span>
              <textarea
                value={toolFilter}
                rows={3}
                placeholder="One MCP tool name per line"
                spellCheck={false}
                onChange={(event) => setToolFilter(event.target.value)}
              />
            </label>
            {connectionType === "remote" ? (
              <SecretBindingsEditor label="Request headers" bindings={headers} credentials={credentials} onChange={setHeaders} />
            ) : (
              <SecretBindingsEditor label="Environment variables" bindings={environment} credentials={credentials} onChange={setEnvironment} />
            )}
            <label className="full settings-check connector-confirmation-toggle">
              <input type="checkbox" checked={requireConfirmation} onChange={(event) => setRequireConfirmation(event.target.checked)} />
              <span>
                <strong>Confirm tool calls</strong>
                <small>Ask before this Connector executes a tool.</small>
              </span>
            </label>
          </>
        ) : null}

        {kind === "specialist" ? (
          <>
            <label className="full capability-editor-field">
              <span>Instructions</span>
              <textarea value={instructions} maxLength={100000} rows={9} onChange={(event) => setInstructions(event.target.value)} />
            </label>
            <fieldset className="full capability-assignment-field">
              <legend>Skills</legend>
              <div className="capability-assignment-list">
                {availableSkills.map((item) => (
                  <label key={item.id}>
                    <input type="checkbox" checked={skills.includes(item.id)} onChange={() => toggle(skills, item.id, setSkills)} />
                    <span><strong>{item.name}</strong><small>{item.description}</small></span>
                  </label>
                ))}
                {availableSkills.length === 0 ? <span className="capability-assignment-empty">No Skills available</span> : null}
              </div>
            </fieldset>
            <fieldset className="full capability-assignment-field">
              <legend>Connectors</legend>
              <div className="capability-assignment-list">
                {availableConnectors.map((item) => (
                  <div className="specialist-connector-assignment" key={item.id}>
                    <label>
                      <input type="checkbox" checked={connectors.includes(item.id)} onChange={() => toggleConnector(item.id)} />
                      <span><strong>{item.name}</strong><small>{item.description}</small></span>
                    </label>
                    {connectors.includes(item.id) && item.id.toLowerCase().startsWith("mcp:") ? (
                      <label className="specialist-tool-filter">
                        <span>Allowed tools for {item.name} (optional)</span>
                        <textarea
                          rows={3}
                          value={connectorTools[item.id] ?? ""}
                          placeholder="One MCP tool name per line"
                          onChange={(event) => setConnectorTools((current) => ({ ...current, [item.id]: event.target.value }))}
                        />
                      </label>
                    ) : null}
                  </div>
                ))}
                {availableConnectors.length === 0 ? <span className="capability-assignment-empty">No Connectors available</span> : null}
              </div>
            </fieldset>
          </>
        ) : null}
      </div> : null}

      <div className="capability-create-actions">
        <button className="secondary" type="button" onClick={onCancel} disabled={saving}>Cancel</button>
        {kind === "skill" && !definition && skillMode === "write" ? (
          <button className="secondary" type="button" disabled={!draftValid || saving} onClick={() => void onSaveSkillDraft(skillInput())}>
            {saving ? "Saving..." : "Save draft"}
          </button>
        ) : null}
        <button className="primary" type="submit" disabled={!valid || saving}>
          {saving ? (definition || draft ? "Saving..." : "Creating...") : definition ? "Save" : draft ? "Publish" : skillMode === "write" || kind !== "skill" ? "Create" : "Import"}
        </button>
      </div>
    </form>
  );
}
