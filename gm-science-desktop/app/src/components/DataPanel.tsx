import { useEffect, useMemo, useRef, useState } from "react";
import type { GmScienceAnalysis, GmScienceDataset, GmScienceRun } from "../types";

interface DataPanelProps {
  projectId: string;
  sessionId?: string;
  onRunStarted: (run: GmScienceRun) => void;
  onWorkspaceChanged: () => Promise<void> | void;
}

interface AnalysisFormState {
  title: string;
  objective: string;
  datasetArtifactIds: string[];
}

const ACTIVE_ANALYSIS_STATUSES = new Set<GmScienceAnalysis["status"]>([
  "queued",
  "running",
  "paused",
  "waiting_user",
  "waiting_approval",
  "interrupted",
  "stale",
]);

function formatBytes(value: number): string {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function fileTitle(name: string): string {
  return name.replace(/\.(csv|tsv|json|jsonl|ndjson)$/i, "") || "Dataset";
}

export function DataPanel({ projectId, sessionId, onRunStarted, onWorkspaceChanged }: DataPanelProps) {
  const [datasets, setDatasets] = useState<GmScienceDataset[]>([]);
  const [analyses, setAnalyses] = useState<GmScienceAnalysis[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<GmScienceDataset | null>(null);
  const [selectedAnalysis, setSelectedAnalysis] = useState<GmScienceAnalysis | null>(null);
  const [analysisModalOpen, setAnalysisModalOpen] = useState(false);
  const [analysisForm, setAnalysisForm] = useState<AnalysisFormState>({
    title: "",
    objective: "",
    datasetArtifactIds: [],
  });
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [creating, setCreating] = useState(false);
  const [runningAnalysisId, setRunningAnalysisId] = useState("");
  const [error, setError] = useState("");
  const analysesRef = useRef<GmScienceAnalysis[]>([]);

  const hasActiveAnalysis = useMemo(
    () => analyses.some((analysis) => ACTIVE_ANALYSIS_STATUSES.has(analysis.status)),
    [analyses],
  );

  useEffect(() => {
    analysesRef.current = analyses;
  }, [analyses]);

  useEffect(() => {
    setDatasets([]);
    setAnalyses([]);
    setSelectedDataset(null);
    setSelectedAnalysis(null);
    setError("");
    void refreshAll(true);
  }, [projectId]);

  useEffect(() => {
    if (!hasActiveAnalysis) {
      return;
    }
    const timer = window.setInterval(() => void refreshAnalyses(), 1200);
    return () => window.clearInterval(timer);
  }, [hasActiveAnalysis, projectId]);

  async function refreshAll(initial = false): Promise<void> {
    if (initial) {
      setLoading(true);
    }
    try {
      const [datasetPayload, analysisPayload] = await Promise.all([
        window.ppxClient.listGmScienceDatasets(projectId),
        window.ppxClient.listGmScienceAnalyses(projectId),
      ]);
      setDatasets(datasetPayload.datasets);
      setAnalyses(analysisPayload.analyses);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  }

  async function refreshAnalyses(): Promise<void> {
    try {
      const payload = await window.ppxClient.listGmScienceAnalyses(projectId);
      const previous = new Map(analysesRef.current.map((analysis) => [analysis.id, analysis.status]));
      const becameTerminal = payload.analyses.some(
        (analysis) =>
          previous.has(analysis.id) &&
          ACTIVE_ANALYSIS_STATUSES.has(previous.get(analysis.id)!) &&
          !ACTIVE_ANALYSIS_STATUSES.has(analysis.status),
      );
      setAnalyses(payload.analyses);
      if (selectedAnalysis) {
        const next = payload.analyses.find((analysis) => analysis.id === selectedAnalysis.id);
        if (next) {
          setSelectedAnalysis((current) => ({
            ...next,
            source: current?.id === next.id ? current.source : next.source,
          }));
        }
      }
      if (becameTerminal) {
        await onWorkspaceChanged();
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function importDataset(): Promise<void> {
    setError("");
    const selection = await window.ppxClient.selectGmScienceDatasetFile();
    if (!selection) {
      return;
    }
    setImporting(true);
    try {
      const payload = await window.ppxClient.importGmScienceDataset(projectId, {
        sourcePath: selection.path,
        title: fileTitle(selection.name),
        sessionId,
      });
      setDatasets((current) => [payload.dataset, ...current.filter((item) => item.artifactId !== payload.dataset.artifactId)]);
      setSelectedDataset(payload.dataset);
      await onWorkspaceChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setImporting(false);
    }
  }

  async function inspectDataset(dataset: GmScienceDataset): Promise<void> {
    setError("");
    if (dataset.profile) {
      setSelectedDataset(dataset);
      return;
    }
    try {
      const payload = await window.ppxClient.getGmScienceDataset(projectId, dataset.artifactId);
      setSelectedDataset(payload.dataset);
      setDatasets((current) =>
        current.map((item) => (item.artifactId === payload.dataset.artifactId ? payload.dataset : item)),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  function openAnalysisModal(): void {
    setAnalysisForm({
      title: "",
      objective: "",
      datasetArtifactIds: selectedDataset ? [selectedDataset.artifactId] : datasets[0] ? [datasets[0].artifactId] : [],
    });
    setError("");
    setAnalysisModalOpen(true);
  }

  function toggleAnalysisDataset(artifactId: string): void {
    setAnalysisForm((current) => ({
      ...current,
      datasetArtifactIds: current.datasetArtifactIds.includes(artifactId)
        ? current.datasetArtifactIds.filter((value) => value !== artifactId)
        : [...current.datasetArtifactIds, artifactId],
    }));
  }

  async function createAnalysis(): Promise<void> {
    if (!analysisForm.objective.trim() || analysisForm.datasetArtifactIds.length === 0) {
      setError("Analysis objective and at least one dataset are required.");
      return;
    }
    setCreating(true);
    setError("");
    try {
      const payload = await window.ppxClient.createGmScienceAnalysis(projectId, {
        title: analysisForm.title.trim() || undefined,
        objective: analysisForm.objective.trim(),
        datasetArtifactIds: analysisForm.datasetArtifactIds,
        sessionId,
      });
      setAnalyses((current) => [payload.analysis, ...current.filter((item) => item.id !== payload.analysis.id)]);
      setSelectedAnalysis(payload.analysis);
      setAnalysisModalOpen(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setCreating(false);
    }
  }

  async function inspectAnalysis(analysis: GmScienceAnalysis): Promise<void> {
    setError("");
    if (analysis.source) {
      setSelectedAnalysis(analysis);
      return;
    }
    try {
      const payload = await window.ppxClient.getGmScienceAnalysis(projectId, analysis.id);
      setSelectedAnalysis(payload.analysis);
      setAnalyses((current) =>
        current.map((item) => (item.id === payload.analysis.id ? payload.analysis : item)),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function runAnalysis(analysis: GmScienceAnalysis): Promise<void> {
    setRunningAnalysisId(analysis.id);
    setError("");
    try {
      const payload = await window.ppxClient.runGmScienceAnalysis(projectId, analysis.id);
      setSelectedAnalysis(payload.analysis);
      setAnalyses((current) => current.map((item) => (item.id === payload.analysis.id ? payload.analysis : item)));
      if (payload.analysis.run) {
        onRunStarted(payload.analysis.run);
      }
      if (!ACTIVE_ANALYSIS_STATUSES.has(payload.analysis.status)) {
        await onWorkspaceChanged();
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setRunningAnalysisId("");
    }
  }

  return (
    <div className="data-panel">
      <div className="data-toolbar">
        <span>{hasActiveAnalysis ? "Analysis in progress" : `${datasets.length} datasets`}</span>
        <div>
          <button className="secondary small" disabled={importing} onClick={() => void importDataset()}>
            {importing ? "Importing..." : "Import"}
          </button>
          <button className="secondary small" disabled={datasets.length === 0} onClick={openAnalysisModal}>
            New analysis
          </button>
        </div>
      </div>
      {error ? <p className="science-runs-error">{error}</p> : null}
      {loading ? <div className="artifact-empty">Loading data...</div> : null}
      {!loading && datasets.length === 0 ? <div className="artifact-empty">No datasets yet</div> : null}

      <div className="dataset-list">
        {datasets.map((dataset) => (
          <button
            key={dataset.artifactId}
            className={selectedDataset?.artifactId === dataset.artifactId ? "dataset-item active" : "dataset-item"}
            onClick={() => void inspectDataset(dataset)}
          >
            <span>
              <strong>{dataset.title}</strong>
              <small>{dataset.format.toUpperCase()} · {formatBytes(dataset.sizeBytes)}</small>
            </span>
            <span className="dataset-shape">{dataset.rowCount} × {dataset.columnCount}</span>
          </button>
        ))}
      </div>

      {selectedDataset?.profile ? (
        <section className="dataset-profile" aria-label={`${selectedDataset.title} profile`}>
          <header>
            <strong>Schema</strong>
            <span>{selectedDataset.profiledRowCount} profiled rows</span>
          </header>
          <div className="dataset-columns">
            {selectedDataset.profile.columns.map((column) => (
              <div key={column.name} className="dataset-column">
                <span><strong>{column.name}</strong><small>{column.inferredType}</small></span>
                <span>{column.missingCount ? `${column.missingCount} missing` : "complete"}</span>
              </div>
            ))}
          </div>
          {selectedDataset.profile.warnings.map((warning) => <p key={warning} className="data-warning">{warning}</p>)}
        </section>
      ) : null}

      <section className="analysis-list-section">
        <header><strong>Analyses</strong><span>{analyses.length}</span></header>
        {analyses.map((analysis) => (
          <button
            key={analysis.id}
            className={selectedAnalysis?.id === analysis.id ? "analysis-item active" : "analysis-item"}
            onClick={() => void inspectAnalysis(analysis)}
          >
            <span><strong>{analysis.title}</strong><small>{analysis.plan.operations.length} planned operations</small></span>
            <span className={`science-run-status ${analysis.status}`}>{analysis.status.replaceAll("_", " ")}</span>
          </button>
        ))}
        {analyses.length === 0 ? <div className="artifact-empty compact">No analyses yet</div> : null}
      </section>

      {selectedAnalysis ? (
        <section className="analysis-review" aria-label={`${selectedAnalysis.title} review`}>
          <header>
            <div><strong>{selectedAnalysis.title}</strong><p>{selectedAnalysis.objective}</p></div>
            {selectedAnalysis.status === "draft" ? (
              <button
                className="primary small"
                disabled={runningAnalysisId === selectedAnalysis.id}
                onClick={() => void runAnalysis(selectedAnalysis)}
              >
                {runningAnalysisId === selectedAnalysis.id ? "Starting..." : "Approve & run"}
              </button>
            ) : null}
          </header>
          <ol className="analysis-steps">
            {selectedAnalysis.plan.steps.map((step) => (
              <li key={step.id}><strong>{step.title}</strong><span>{step.description}</span></li>
            ))}
          </ol>
          {selectedAnalysis.plan.warnings.map((warning) => <p key={warning} className="data-warning strong">{warning}</p>)}
          <details className="analysis-details">
            <summary>Assumptions</summary>
            <ul>{selectedAnalysis.plan.assumptions.map((item) => <li key={item}>{item}</li>)}</ul>
          </details>
          {selectedAnalysis.source ? (
            <details className="analysis-details source">
              <summary>Python source</summary>
              <pre>{selectedAnalysis.source}</pre>
            </details>
          ) : null}
          {selectedAnalysis.reportArtifactId ? <small>Report: {selectedAnalysis.reportArtifactId}</small> : null}
        </section>
      ) : null}

      {analysisModalOpen ? (
        <div className="modal-backdrop" role="presentation">
          <section className="project-modal analysis-modal" role="dialog" aria-modal="true" aria-labelledby="new-analysis-title">
            <header>
              <div><h2 id="new-analysis-title">New Data Analysis</h2><p>Create a plan for review before local execution.</p></div>
              <button className="icon-button" onClick={() => setAnalysisModalOpen(false)} aria-label="Close analysis dialog">×</button>
            </header>
            <div className="analysis-form-body">
              <label className="settings-field"><span>Title</span><input value={analysisForm.title} placeholder="Optional analysis title" onChange={(event) => setAnalysisForm((current) => ({ ...current, title: event.target.value }))} /></label>
              <label className="settings-field"><span>Objective</span><textarea autoFocus value={analysisForm.objective} placeholder="What should be checked or compared?" onChange={(event) => setAnalysisForm((current) => ({ ...current, objective: event.target.value }))} /></label>
              <fieldset className="analysis-dataset-picker">
                <legend>Datasets</legend>
                {datasets.map((dataset) => (
                  <label key={dataset.artifactId}>
                    <input type="checkbox" checked={analysisForm.datasetArtifactIds.includes(dataset.artifactId)} onChange={() => toggleAnalysisDataset(dataset.artifactId)} />
                    <span><strong>{dataset.title}</strong><small>{dataset.rowCount} rows · {dataset.columnCount} columns</small></span>
                  </label>
                ))}
              </fieldset>
              {error ? <p className="composer-error">{error}</p> : null}
            </div>
            <footer>
              <button className="secondary" onClick={() => setAnalysisModalOpen(false)}>Cancel</button>
              <button className="primary" disabled={creating || !analysisForm.objective.trim() || analysisForm.datasetArtifactIds.length === 0} onClick={() => void createAnalysis()}>{creating ? "Planning..." : "Create plan"}</button>
            </footer>
          </section>
        </div>
      ) : null}
    </div>
  );
}
