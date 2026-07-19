import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  FileText,
  GitBranch,
  History,
  Download,
  FileOutput,
  FolderOpen,
  Link,
  MoreHorizontal,
  Pencil,
  RefreshCw,
  Star,
  Trash2,
  EyeOff,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { GmScienceResource, GmScienceResourceDetail } from "../types";

interface ArtifactInspectorProps {
  tabs: GmScienceResource[];
  activeResourceId: string;
  detail: GmScienceResourceDetail | null;
  loading: boolean;
  error: string | null;
  actionError: string | null;
  provenanceOpen: boolean;
  onBack: () => void;
  onSelectTab: (resource: GmScienceResource) => void;
  onCloseTab: (resourceId: string) => void;
  onRetry: () => void;
  onViewInContext: () => void;
  onOpenProvenance: () => void;
  onCloseProvenance: () => void;
  onOpenRelation: (resourceId: string) => void;
  onRename: () => void;
  onToggleStar: () => void;
  onHide: () => void;
  onDelete: () => void;
  onCopyLink: () => void;
  onDownload: () => void;
  onReveal: () => void;
  onExport: () => void;
}

function displayValue(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function labelForKey(key: string): string {
  return key.replaceAll("_", " ").replace(/^./, (value) => value.toUpperCase());
}

function isMarkdown(detail: GmScienceResourceDetail): boolean {
  return detail.resource.mimeType.split(";", 1)[0].trim().toLowerCase() === "text/markdown"
    || detail.resource.relativePath.toLowerCase().endsWith(".md");
}

function descriptorMessage(detail: GmScienceResourceDetail): string {
  if (detail.preview.contentStatus === "external_descriptor_only") {
    return "This Artifact is stored outside the local Project. Its reference is available, but remote content is not fetched automatically.";
  }
  if (detail.preview.contentStatus === "binary_descriptor_only") {
    return "This file type does not have a local preview yet. The Artifact remains available as research context and provenance.";
  }
  if (detail.preview.contentStatus === "unavailable_descriptor_only") {
    return "The local file could not be read. Refresh Files after checking that it still exists inside the Project workspace.";
  }
  if (detail.preview.contentStatus === "budget_exhausted_descriptor_only") {
    return "The configured preview budget was exhausted before this Artifact could be read.";
  }
  return "This Artifact currently provides metadata and provenance without a text preview.";
}

export function ArtifactInspector({
  tabs,
  activeResourceId,
  detail,
  loading,
  error,
  actionError,
  provenanceOpen,
  onBack,
  onSelectTab,
  onCloseTab,
  onRetry,
  onViewInContext,
  onOpenProvenance,
  onCloseProvenance,
  onOpenRelation,
  onRename,
  onToggleStar,
  onHide,
  onDelete,
  onCopyLink,
  onDownload,
  onReveal,
  onExport,
}: ArtifactInspectorProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setMenuOpen(false);
  }, [activeResourceId]);

  useEffect(() => {
    if (!menuOpen) {
      return;
    }
    const closeOnPointerDown = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
      }
    };
    document.addEventListener("pointerdown", closeOnPointerDown);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnPointerDown);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [menuOpen]);

  return (
    <section className="artifact-inspector" aria-label="Artifact detail">
      <header className="artifact-inspector-tabs">
        <button className="icon-control" aria-label="Back to artifacts" title="Back to artifacts" onClick={onBack}>
          <ArrowLeft size={17} />
        </button>
        <div className="artifact-tab-strip" role="tablist" aria-label="Open artifacts">
          {tabs.map((resource) => (
            <div
              className={resource.id === activeResourceId ? "artifact-tab active" : "artifact-tab"}
              key={resource.id}
            >
              <button
                role="tab"
                aria-selected={resource.id === activeResourceId}
                onClick={() => onSelectTab(resource)}
                title={resource.displayName}
              >
                <FileText size={14} />
                <span>{resource.displayName}</span>
              </button>
              <button
                className="artifact-tab-close"
                aria-label={`Close ${resource.displayName}`}
                title={`Close ${resource.displayName}`}
                onClick={() => onCloseTab(resource.id)}
              >
                <X size={13} />
              </button>
            </div>
          ))}
        </div>
        <div className="artifact-actions" ref={menuRef}>
          <button
            className="icon-control"
            aria-label="Artifact actions"
            title="Artifact actions"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((current) => !current)}
          >
            <MoreHorizontal size={18} />
          </button>
          {menuOpen ? (
            <div className="artifact-actions-menu" role="menu">
              {detail?.artifact ? <button role="menuitem" onClick={() => { setMenuOpen(false); onToggleStar(); }}><Star size={16} />{detail.resource.metadata.starred === true ? "Unstar" : "Star"}</button> : null}
              {detail?.artifact ? <button role="menuitem" onClick={() => { setMenuOpen(false); onHide(); }}><EyeOff size={16} />Hide</button> : null}
              <button
                role="menuitem"
                onClick={() => {
                  setMenuOpen(false);
                  onViewInContext();
                }}
              >
                <History size={16} />
                View in context
              </button>
              <button
                role="menuitem"
                onClick={() => {
                  setMenuOpen(false);
                  onOpenProvenance();
                }}
              >
                <GitBranch size={16} />
                Provenance
              </button>
              <button role="menuitem" onClick={() => { setMenuOpen(false); onCopyLink(); }}><Link size={16} />Copy link</button>
              {detail?.artifact ? <button role="menuitem" onClick={() => { setMenuOpen(false); onRename(); }}><Pencil size={16} />Rename</button> : null}
              <button role="menuitem" onClick={() => { setMenuOpen(false); onDownload(); }}><Download size={16} />Download</button>
              <button role="menuitem" onClick={() => { setMenuOpen(false); onReveal(); }}><FolderOpen size={16} />Reveal in Finder</button>
              <button role="menuitem" onClick={() => { setMenuOpen(false); onExport(); }}><FileOutput size={16} />Export</button>
              {detail?.artifact ? <button className="danger" role="menuitem" onClick={() => { setMenuOpen(false); onDelete(); }}><Trash2 size={16} />Delete</button> : null}
            </div>
          ) : null}
        </div>
      </header>

      <div className="artifact-inspector-body">
        {loading ? (
          <div className="artifact-inspector-state">
            <RefreshCw className="spin" size={20} />
            <span>Loading Artifact...</span>
          </div>
        ) : error ? (
          <div className="artifact-inspector-state error">
            <strong>Artifact unavailable</strong>
            <span>{error}</span>
            <button className="secondary small" onClick={onRetry}>
              <RefreshCw size={15} />
              Retry
            </button>
          </div>
        ) : detail ? (
          <>
            <div className="artifact-document-heading">
              <div>
                <h2>{detail.resource.displayName}</h2>
                <p>
                  {[detail.resource.artifactType.replaceAll("_", " "), detail.resource.mimeType]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>
              {detail.preview.truncated ? <span>Preview truncated</span> : null}
            </div>
            {actionError ? <p className="artifact-action-error">{actionError}</p> : null}
            {detail.preview.contentIncluded ? (
              detail.preview.displayMode === "table" && detail.preview.table ? (
                <div className="artifact-table-preview" role="region" aria-label="Table preview" tabIndex={0}>
                  <table>
                    <thead>
                      <tr>{detail.preview.table.columns.map((column, index) => <th key={`${column}-${index}`}>{column}</th>)}</tr>
                    </thead>
                    <tbody>
                      {detail.preview.table.rows.map((row, rowIndex) => (
                        <tr key={rowIndex}>{row.map((value, columnIndex) => <td key={columnIndex}>{value}</td>)}</tr>
                      ))}
                    </tbody>
                  </table>
                  {detail.preview.table.truncated ? <p>Table preview truncated</p> : null}
                </div>
              ) : detail.preview.displayMode === "markdown" || isMarkdown(detail) ? (
                <article className="artifact-markdown rich-markdown">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{detail.preview.content}</ReactMarkdown>
                </article>
              ) : (
                <pre className={detail.preview.displayMode === "json" ? "artifact-text-preview json" : "artifact-text-preview"}>{detail.preview.content}</pre>
              )
            ) : (
              <div className="artifact-descriptor">
                <FileText size={24} />
                <strong>Preview unavailable</strong>
                <p>{descriptorMessage(detail)}</p>
                <dl>
                  {detail.resource.relativePath ? (
                    <>
                      <dt>Project path</dt>
                      <dd>{detail.resource.relativePath}</dd>
                    </>
                  ) : null}
                  {detail.resource.url ? (
                    <>
                      <dt>Source</dt>
                      <dd>{detail.resource.url}</dd>
                    </>
                  ) : null}
                  <dt>Access</dt>
                  <dd>{detail.resource.accessMode.replaceAll("_", " ")}</dd>
                </dl>
              </div>
            )}
          </>
        ) : null}
      </div>

      {provenanceOpen && detail ? (
        <aside className="artifact-provenance" aria-label="Artifact provenance">
          <header>
            <div>
              <h3>Provenance</h3>
              <p>{detail.resource.displayName}</p>
            </div>
            <button className="icon-control" aria-label="Close provenance" title="Close provenance" onClick={onCloseProvenance}>
              <X size={17} />
            </button>
          </header>
          <div className="artifact-provenance-content">
            <section>
              <h4>Origin</h4>
              <dl>
                <dt>Created</dt>
                <dd>{detail.artifact?.createdAt || detail.resource.createdAt}</dd>
                <dt>Session</dt>
                <dd>{detail.artifact?.sessionId || detail.resource.sessionId || "Not attached"}</dd>
                {Object.entries(detail.artifact?.provenance ?? {}).map(([key, value]) => (
                  <div className="artifact-provenance-row" key={key}>
                    <dt>{labelForKey(key)}</dt>
                    <dd>{displayValue(value)}</dd>
                  </div>
                ))}
              </dl>
            </section>
            {Object.keys(detail.artifact?.metadata ?? {}).length ? (
              <section>
                <h4>Research metadata</h4>
                <dl>
                  {Object.entries(detail.artifact?.metadata ?? {}).map(([key, value]) => (
                    <div className="artifact-provenance-row" key={key}>
                      <dt>{labelForKey(key)}</dt>
                      <dd>{displayValue(value)}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            ) : null}
            {detail.relations.length ? (
              <section>
                <h4>Related Artifacts</h4>
                <div className="artifact-relation-list">
                  {detail.relations.map((relation) => (
                    <button key={`${relation.direction}:${relation.relation}:${relation.artifactId}`} onClick={() => onOpenRelation(relation.resourceId)}>
                      <span>
                        <strong>{relation.title}</strong>
                        <small>{relation.direction} · {relation.relation} · {relation.artifactType}</small>
                      </span>
                      <FileText size={16} />
                    </button>
                  ))}
                </div>
              </section>
            ) : null}
          </div>
        </aside>
      ) : null}
    </section>
  );
}
