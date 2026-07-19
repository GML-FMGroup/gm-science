import { useEffect, useMemo, useState } from "react";
import { ArrowLeft } from "lucide-react";
import type {
  CreateGmScienceConnectorInput,
  CreateGmScienceSkillInput,
  CreateGmScienceSpecialistInput,
  GmScienceCapability,
  GmScienceCapabilityKind,
} from "../types";

interface CapabilityCreatePanelProps {
  kind: GmScienceCapabilityKind;
  capabilities: GmScienceCapability[];
  saving: boolean;
  error: string | null;
  onCancel: () => void;
  onCreateSkill: (input: CreateGmScienceSkillInput) => Promise<void>;
  onCreateConnector: (input: CreateGmScienceConnectorInput) => Promise<void>;
  onCreateSpecialist: (input: CreateGmScienceSpecialistInput) => Promise<void>;
}

const labels: Record<GmScienceCapabilityKind, { title: string; id: string }> = {
  skill: { title: "Add skill", id: "Skill ID" },
  connector: { title: "Add connector", id: "Connector ID" },
  specialist: { title: "Add specialist", id: "Agent ID" },
};

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
  saving,
  error,
  onCancel,
  onCreateSkill,
  onCreateConnector,
  onCreateSpecialist,
}: CapabilityCreatePanelProps) {
  const [name, setName] = useState("");
  const [id, setId] = useState("");
  const [idEdited, setIdEdited] = useState(false);
  const [description, setDescription] = useState("");
  const [content, setContent] = useState("");
  const [instructions, setInstructions] = useState("");
  const [connectionType, setConnectionType] = useState<"remote" | "local">("remote");
  const [url, setUrl] = useState("");
  const [commandLine, setCommandLine] = useState("");
  const [skills, setSkills] = useState<string[]>([]);
  const [connectors, setConnectors] = useState<string[]>([]);

  useEffect(() => {
    if (!idEdited) {
      setId(capabilityId(name, kind));
    }
  }, [idEdited, kind, name]);

  const availableSkills = useMemo(
    () => capabilities.filter((item) => item.kind === "skill" && item.available),
    [capabilities],
  );
  const availableConnectors = useMemo(
    () => capabilities.filter((item) => item.kind === "connector" && item.available),
    [capabilities],
  );
  const valid = Boolean(
    name.trim()
      && id.trim()
      && description.trim()
      && (kind !== "skill" || content.trim())
      && (kind !== "connector" || (connectionType === "remote" ? url.trim() : commandLine.trim()))
      && (kind !== "specialist" || instructions.trim()),
  );

  async function submit(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!valid || saving) {
      return;
    }
    if (kind === "skill") {
      await onCreateSkill({ id: id.trim(), name: name.trim(), description: description.trim(), content });
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
    });
  }

  function toggle(values: string[], value: string, setter: (next: string[]) => void): void {
    setter(values.includes(value) ? values.filter((item) => item !== value) : [...values, value]);
  }

  return (
    <form className="capability-create-page" aria-label={labels[kind].title} onSubmit={(event) => void submit(event)}>
      <div className="capability-create-heading">
        <button className="icon-control" type="button" onClick={onCancel} aria-label="Back to capability list" title="Back to capability list">
          <ArrowLeft size={18} />
        </button>
        <h3>{labels[kind].title}</h3>
      </div>

      {error ? <p className="composer-error capability-create-error">{error}</p> : null}

      {kind === "connector" ? (
        <div className="segmented-control capability-create-mode" aria-label="Connector type">
          <button type="button" className={connectionType === "remote" ? "active" : ""} onClick={() => setConnectionType("remote")}>Remote URL</button>
          <button type="button" className={connectionType === "local" ? "active" : ""} onClick={() => setConnectionType("local")}>Local command</button>
        </div>
      ) : null}

      <div className="capability-create-fields">
        <label>
          <span>Name</span>
          <input autoFocus value={name} maxLength={120} onChange={(event) => setName(event.target.value)} />
        </label>
        <label>
          <span>{labels[kind].id}</span>
          <input
            value={id}
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
          <label className="full capability-editor-field">
            <span>Markdown content</span>
            <textarea value={content} maxLength={200000} rows={14} spellCheck={false} onChange={(event) => setContent(event.target.value)} />
          </label>
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
                  <label key={item.id}>
                    <input type="checkbox" checked={connectors.includes(item.id)} onChange={() => toggle(connectors, item.id, setConnectors)} />
                    <span><strong>{item.name}</strong><small>{item.description}</small></span>
                  </label>
                ))}
                {availableConnectors.length === 0 ? <span className="capability-assignment-empty">No Connectors available</span> : null}
              </div>
            </fieldset>
          </>
        ) : null}
      </div>

      <div className="capability-create-actions">
        <button className="secondary" type="button" onClick={onCancel} disabled={saving}>Cancel</button>
        <button className="primary" type="submit" disabled={!valid || saving}>{saving ? "Creating..." : "Create"}</button>
      </div>
    </form>
  );
}
