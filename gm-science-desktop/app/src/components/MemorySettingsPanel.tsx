import { useCallback, useEffect, useMemo, useState } from "react";
import { Check, Plus, RefreshCw, Trash2, X } from "lucide-react";
import type {
  GmScienceMemoryNote,
  GmScienceMemoryScope,
  GmScienceMemoryWorkspace,
  GmScienceSettings,
} from "../types";

interface MemorySettingsPanelProps {
  projectId: string;
  projectName: string;
  settings: GmScienceSettings | null;
  settingsLoading: boolean;
  settingsSaving: boolean;
  settingsError: string | null;
  onSetGlobalEnabled: (enabled: boolean) => Promise<void>;
}

interface NoteDraft {
  id: string;
  category: string;
  text: string;
}

const EMPTY_DRAFT: NoteDraft = { id: "", category: "", text: "" };

function formatTimestamp(value: string): string {
  if (!value) {
    return "";
  }
  const timestamp = new Date(value);
  return Number.isNaN(timestamp.getTime()) ? value : timestamp.toLocaleString();
}

export function MemorySettingsPanel({
  projectId,
  projectName,
  settings,
  settingsLoading,
  settingsSaving,
  settingsError,
  onSetGlobalEnabled,
}: MemorySettingsPanelProps) {
  const [workspace, setWorkspace] = useState<GmScienceMemoryWorkspace | null>(null);
  const [scope, setScope] = useState<GmScienceMemoryScope>("user");
  const [draft, setDraft] = useState<NoteDraft>(EMPTY_DRAFT);
  const [editorOpen, setEditorOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!projectId) {
      setWorkspace(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setWorkspace(await window.ppxClient.getGmScienceMemory(projectId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    setDraft(EMPTY_DRAFT);
    setEditorOpen(false);
    void refresh();
  }, [refresh]);

  const notes = useMemo(
    () => (workspace?.notes ?? []).filter((note) => note.scope === scope),
    [scope, workspace?.notes],
  );
  const pendingCandidates = useMemo(
    () => (workspace?.candidates ?? []).filter(
      (candidate) => candidate.scope === scope && candidate.status === "pending",
    ),
    [scope, workspace?.candidates],
  );

  function editNote(note: GmScienceMemoryNote): void {
    setDraft({ id: note.id, category: note.category, text: note.text });
    setEditorOpen(true);
    setError(null);
  }

  async function saveNote(): Promise<void> {
    const category = draft.category.trim();
    const text = draft.text.trim();
    if (!category || !text || !projectId) {
      setError("Category and note text are required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      if (draft.id) {
        await window.ppxClient.updateGmScienceMemoryNote(projectId, draft.id, { category, text });
      } else {
        await window.ppxClient.createGmScienceMemoryNote(projectId, { scope, category, text });
      }
      setDraft(EMPTY_DRAFT);
      setEditorOpen(false);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSaving(false);
    }
  }

  async function deleteNote(note: GmScienceMemoryNote): Promise<void> {
    if (!window.confirm(`Delete the Memory note in "${note.category}"?`)) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await window.ppxClient.deleteGmScienceMemoryNote(projectId, note.id);
      if (draft.id === note.id) {
        setDraft(EMPTY_DRAFT);
        setEditorOpen(false);
      }
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSaving(false);
    }
  }

  async function clearScope(): Promise<void> {
    const label = scope === "user" ? "User" : "Project";
    if (!window.confirm(`Clear all approved ${label} Memory notes?`)) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await window.ppxClient.clearGmScienceMemory(projectId, scope);
      setDraft(EMPTY_DRAFT);
      setEditorOpen(false);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSaving(false);
    }
  }

  async function reviewCandidate(candidateId: string, decision: "approve" | "reject"): Promise<void> {
    setSaving(true);
    setError(null);
    try {
      await window.ppxClient.reviewGmScienceMemoryCandidate(projectId, candidateId, decision);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSaving(false);
    }
  }

  const globalEnabled = settings?.memory.enabled ?? false;
  const displayError = error || settingsError;

  return (
    <div className="settings-page science-settings-page memory-settings-page">
      <div className="settings-page-title memory-page-title">
        <div><h3>Memory</h3><p>Approved User and Project research context.</p></div>
        <label className="session-option-toggle memory-global-toggle">
          <span>{globalEnabled ? "On" : "Off"}</span>
          <input
            aria-label="Enable Memory"
            type="checkbox"
            checked={globalEnabled}
            disabled={!settings || settingsLoading || settingsSaving}
            onChange={(event) => void onSetGlobalEnabled(event.target.checked).catch(() => undefined)}
          />
        </label>
      </div>
      {!globalEnabled && settings ? (
        <div className="settings-notice memory-off-notice">
          <div><strong>Memory is off</strong><p>Existing notes remain editable. New proposals and recall are paused.</p></div>
        </div>
      ) : null}
      {displayError ? <p className="composer-error">{displayError}</p> : null}
      {!projectId ? <p className="memory-empty">Open a Project to manage Memory.</p> : (
        <>
          <div className="memory-scope-tabs" role="tablist" aria-label="Memory scope">
            <button
              role="tab"
              aria-selected={scope === "user"}
              className={scope === "user" ? "active" : ""}
              onClick={() => { setScope("user"); setDraft(EMPTY_DRAFT); setEditorOpen(false); }}
            >
              User
            </button>
            <button
              role="tab"
              aria-selected={scope === "project"}
              className={scope === "project" ? "active" : ""}
              onClick={() => { setScope("project"); setDraft(EMPTY_DRAFT); setEditorOpen(false); }}
            >
              {projectName || "Current Project"}
            </button>
          </div>

          {pendingCandidates.length > 0 ? (
            <section className="settings-section-block memory-candidate-section">
              <h4>Pending review <span>{pendingCandidates.length}</span></h4>
              <div className="memory-row-list">
                {pendingCandidates.map((candidate) => (
                  <article className="memory-candidate-row" key={candidate.id}>
                    <div className="memory-row-heading">
                      <strong>{candidate.category}</strong>
                      <small>{candidate.model || "Configured model"}</small>
                    </div>
                    <p>{candidate.text}</p>
                    <div className="memory-candidate-rationale">
                      <span>{candidate.rationale}</span>
                      {candidate.sourceSessionId ? <small>Session {candidate.sourceSessionId}</small> : null}
                    </div>
                    <div className="memory-row-actions">
                      <button className="secondary" disabled={saving} onClick={() => void reviewCandidate(candidate.id, "reject")}><X size={15} />Reject</button>
                      <button className="primary" disabled={saving} onClick={() => void reviewCandidate(candidate.id, "approve")}><Check size={15} />Approve</button>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ) : null}

          <section className="settings-section-block memory-notes-section">
            <div className="memory-section-heading">
              <div><h4>{scope === "user" ? "About you" : "Project Memory"}</h4><p>{notes.length} approved {notes.length === 1 ? "note" : "notes"}</p></div>
              <div className="memory-row-actions">
                <button className="icon-control" title="Refresh Memory" aria-label="Refresh Memory" disabled={loading} onClick={() => void refresh()}><RefreshCw size={16} className={loading ? "spin" : ""} /></button>
                <button className="secondary" disabled={saving} onClick={() => { setDraft(EMPTY_DRAFT); setEditorOpen(true); }}><Plus size={15} />Add</button>
                {notes.length > 0 ? <button className="secondary danger" disabled={saving} onClick={() => void clearScope()}><Trash2 size={15} />Clear all</button> : null}
              </div>
            </div>

            {editorOpen ? (
              <div className="memory-editor">
                <label className="settings-field"><span>Category</span><input value={draft.category} disabled={saving} placeholder={scope === "user" ? "About you" : "Project context"} onChange={(event) => setDraft((current) => ({ ...current, category: event.target.value }))} /></label>
                <label className="settings-field full"><span>Note</span><textarea value={draft.text} disabled={saving} rows={3} onChange={(event) => setDraft((current) => ({ ...current, text: event.target.value }))} /></label>
                <div className="memory-row-actions">
                  <button className="secondary" disabled={saving} onClick={() => { setDraft(EMPTY_DRAFT); setEditorOpen(false); }}>Cancel</button>
                  <button className="primary" disabled={saving || !draft.category.trim() || !draft.text.trim()} onClick={() => void saveNote()}>{saving ? "Saving..." : draft.id ? "Save note" : "Add note"}</button>
                </div>
              </div>
            ) : null}

            {loading && !workspace ? <p className="memory-empty">Loading Memory...</p> : null}
            {!loading && notes.length === 0 ? <p className="memory-empty">No approved notes in this scope.</p> : null}
            <div className="memory-row-list">
              {notes.map((note) => (
                <article className="memory-note-row" key={note.id}>
                  <button className="memory-note-content" onClick={() => editNote(note)}>
                    <span className="memory-row-heading"><strong>{note.category}</strong><small>{formatTimestamp(note.updatedAt)}</small></span>
                    <span>{note.text}</span>
                    <small>{note.usage.count > 0 ? `Recalled ${note.usage.count} times across ${note.usage.sessionIds.length} sessions` : "Not recalled yet"}</small>
                  </button>
                  <button className="icon-control danger" title="Delete note" aria-label={`Delete ${note.category} note`} disabled={saving} onClick={() => void deleteNote(note)}><Trash2 size={15} /></button>
                </article>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
