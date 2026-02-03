"use client";

import { useEffect, useMemo, useState } from "react";
import { CorrectionEditor } from "../components/CorrectionEditor";
import { ImageOverlay, type TokenBox } from "../components/ImageOverlay";
import { OllamaConsole } from "../components/OllamaConsole";
import { TokenList } from "../components/TokenList";
import { SummaryView } from "../components/SummaryView";

type DocumentPayload = {
  document_id: string;
  image_url: string;
  image_width: number;
  image_height: number;
  status: string;
  structured_fields: Record<string, string>;
  tokens: Array<{
    id: string;
    line_id: string;
    line_index: number;
    token_index: number;
    text: string;
    confidence: number;
    confidence_label: "trusted" | "medium" | "low";
    forced_review: boolean;
    bbox: [number, number, number, number];
    flags: string[];
  }>;
};

type SummaryPayload = {
  bullet_summary: string[];
  structured_fields: Record<string, string>;
};

type ToastMessage = {
  id: string;
  message: string;
  variant: "error" | "info";
};

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function severityScore(token: TokenBox) {
  if (token.confidenceLabel === "low") return 3;
  if (token.forcedReview) return 2;
  return 1;
}

export default function HomePage() {
  const [selectedTokenId, setSelectedTokenId] = useState<string | null>(null);
  const [corrections, setCorrections] = useState<Record<string, string>>({});
  const [reviewedTokenIds, setReviewedTokenIds] = useState<Set<string>>(new Set());
  const [documentData, setDocumentData] = useState<DocumentPayload | null>(null);
  const [summary, setSummary] = useState<SummaryPayload | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAllTokens, setShowAllTokens] = useState(false);
  const [pollingEnabled, setPollingEnabled] = useState(true);
  const [processingCanceled, setProcessingCanceled] = useState(false);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [selectedModel, setSelectedModel] = useState("llama3.1");
  const [aiEnabled, setAiEnabled] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [summarySource, setSummarySource] = useState<"ai" | "offline" | null>(null);
  const [ollamaHealth, setOllamaHealth] = useState<{ reachable: boolean } | null>(null);
  const [ollamaWarned, setOllamaWarned] = useState(false);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const isProcessing = documentData ? ["uploaded", "processing"].includes(documentData.status) : false;
  const processingActive = isProcessing && pollingEnabled;
  const interactionDisabled = loading || processingActive;
  const statusDotClass = isProcessing ? "status-indexing" : "status-ready";

  const allTokens = useMemo<TokenBox[]>(() => {
    if (!documentData) return [];
    return documentData.tokens.map((token) => ({
      id: token.id,
      text: token.text,
      confidence: token.confidence,
      confidenceLabel: token.confidence_label,
      forcedReview: token.forced_review,
      flags: token.flags,
      bbox: token.bbox,
    }));
  }, [documentData]);

  const flaggedTokens = useMemo(
    () =>
      allTokens
        .filter((token) => token.forcedReview || token.confidenceLabel !== "trusted")
        .sort((a, b) => severityScore(b) - severityScore(a)),
    [allTokens]
  );

  const tokenById = useMemo(() => {
    const map = new Map<string, TokenBox>();
    allTokens.forEach((token) => map.set(token.id, token));
    return map;
  }, [allTokens]);

  const selectedToken = flaggedTokens.find((token) => token.id === selectedTokenId) ?? null;
  const correctionValue = selectedToken ? corrections[selectedToken.id] ?? selectedToken.text : "";
  const displayTokens = showAllTokens ? allTokens : flaggedTokens;

  const reviewedCount = flaggedTokens.filter((token) => reviewedTokenIds.has(token.id)).length;
  const reviewProgress = flaggedTokens.length ? Math.round((reviewedCount / flaggedTokens.length) * 100) : 0;

  const pushToast = (message: string, variant: ToastMessage["variant"] = "error") => {
    const id =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random()}`;
    setToasts((prev) => [...prev, { id, message, variant }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((toast) => toast.id !== id));
    }, 5000);
  };

  const uploadDocument = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    setSummary(null);
    setSummarySource(null);
    setSummaryLoading(false);
    setPollingEnabled(true);
    setProcessingCanceled(false);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch(`${apiBase}/documents/upload`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || "Upload failed");
      }

      const data = (await response.json()) as DocumentPayload;
      setDocumentData({
        ...data,
        image_url: `${apiBase}${data.image_url}`,
      });
      setCorrections({});
      setReviewedTokenIds(new Set());
      setSelectedTokenId(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Upload failed";
      console.error("Upload failed", err);
      setError(message);
      pushToast(message, "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!documentData || !processingActive) return;
    const interval = window.setInterval(async () => {
      try {
        const response = await fetch(`${apiBase}/documents/${documentData.document_id}`);
        if (!response.ok) return;
        const data = (await response.json()) as DocumentPayload;
        setDocumentData({
          ...data,
          image_url: `${apiBase}${data.image_url}`,
        });
        if (data.status === "failed") {
          setError("OCR processing failed. Please retry or upload a different document.");
          window.clearInterval(interval);
        }
      } catch (err) {
        console.error("Status polling failed", err);
      }
    }, 1500);
    return () => window.clearInterval(interval);
  }, [apiBase, documentData, processingActive]);

  const buildCorrectionsPayload = () => {
    const payload: Array<{ token_id: string; corrected_text: string }> = [];
    Object.entries(corrections).forEach(([tokenId, value]) => {
      const original = tokenById.get(tokenId)?.text;
      if (original !== undefined && value !== original) {
        payload.push({ token_id: tokenId, corrected_text: value });
      }
    });
    return payload;
  };

  const confirmReview = async () => {
    if (!documentData) return;
    if (aiEnabled && !selectedModel) {
      pushToast("Select a model before generating AI summaries.", "error");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${apiBase}/documents/${documentData.document_id}/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          corrections: buildCorrectionsPayload(),
          reviewed_token_ids: Array.from(reviewedTokenIds),
          review_complete: true,
        }),
      });

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || "Validation failed");
      }

      setSummaryLoading(true);
      try {
        await requestSummary();
      } catch (err) {
        const message = err instanceof Error ? err.message : "Summary failed";
        console.error("Summary failed", err);
        setError(message);
        pushToast(message, "error");
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Validation failed";
      console.error("Validation failed", err);
      setError(message);
      pushToast(message, "error");
    } finally {
      setSummaryLoading(false);
      setLoading(false);
    }
  };

  const requestSummary = async () => {
    if (!documentData) return;
    const useAi = aiEnabled && selectedModel;
    if (aiEnabled && !selectedModel) {
      throw new Error("Select a model to generate AI summaries.");
    }
    const modelParam = useAi ? `?model=${encodeURIComponent(selectedModel)}` : "";
    const summaryResponse = await fetch(`${apiBase}/documents/${documentData.document_id}/summary${modelParam}`);
    if (!summaryResponse.ok) {
      const message = await summaryResponse.text();
      throw new Error(message || "Summary failed");
    }
    const summaryData = (await summaryResponse.json()) as SummaryPayload;
    setSummary(summaryData);
    setSummarySource(useAi ? "ai" : "offline");
  };

  const exportDocument = async (format: "json" | "csv" | "txt") => {
    if (!documentData) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${apiBase}/documents/${documentData.document_id}/export?format=${format}`);
      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || "Export failed");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `vera-export.${format}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Export failed";
      console.error("Export failed", err);
      setError(message);
      pushToast(message, "error");
    } finally {
      setLoading(false);
    }
  };


  const refreshSummary = async () => {
    if (!summary || !documentData) return;
    setLoading(true);
    setSummaryLoading(true);
    setError(null);
    try {
      await requestSummary();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Summary failed";
      console.error("Summary failed", err);
      setError(message);
      pushToast(message, "error");
    } finally {
      setSummaryLoading(false);
      setLoading(false);
    }
  };

  const fetchOllamaHealth = async () => {
    try {
      const response = await fetch(`${apiBase}/llm/health`);
      if (!response.ok) {
        throw new Error("Ollama is not reachable");
      }
      const data = (await response.json()) as { reachable: boolean };
      setOllamaHealth({ reachable: Boolean(data.reachable) });
      if (data.reachable) {
        setOllamaWarned(false);
      }
    } catch {
      setOllamaHealth({ reachable: false });
    }
  };

  useEffect(() => {
    if (!settingsOpen) return;
    fetchOllamaHealth();
  }, [settingsOpen]);

  useEffect(() => {
    if (!aiEnabled || !ollamaHealth || ollamaHealth.reachable) return;
    if (!ollamaWarned) {
      pushToast("Ollama is not reachable from the backend. AI summaries may fail.", "error");
      setOllamaWarned(true);
    }
  }, [aiEnabled, ollamaHealth, ollamaWarned]);

  const findNextTokenId = (currentId: string, nextReviewed: Set<string>) => {
    if (!flaggedTokens.length) return null;
    const startIndex = flaggedTokens.findIndex((token) => token.id === currentId);
    const isUnreviewed = (tokenId: string) => !nextReviewed.has(tokenId);

    for (let index = startIndex + 1; index < flaggedTokens.length; index += 1) {
      if (isUnreviewed(flaggedTokens[index].id)) return flaggedTokens[index].id;
    }

    for (let index = 0; index <= startIndex; index += 1) {
      if (isUnreviewed(flaggedTokens[index].id)) return flaggedTokens[index].id;
    }

    return null;
  };

  const cancelProcessing = async () => {
    if (!documentData) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${apiBase}/documents/${documentData.document_id}/cancel`, {
        method: "POST",
      });
      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || "Cancel failed");
      }
      const data = (await response.json()) as { status: string };
      setDocumentData((prev) =>
        prev
          ? {
              ...prev,
              status: data.status,
            }
          : prev
      );
      setPollingEnabled(false);
      setProcessingCanceled(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Cancel failed";
      console.error("Cancel failed", err);
      setError(message);
      pushToast(message, "error");
    } finally {
      setLoading(false);
    }
  };

  const resumeProcessing = () => {
    setPollingEnabled(true);
    setProcessingCanceled(false);
  };

  const handleMarkReviewed = () => {
    if (!selectedToken || interactionDisabled) return;
    setReviewedTokenIds((prev) => {
      const next = new Set(prev);
      next.add(selectedToken.id);
      setSelectedTokenId(findNextTokenId(selectedToken.id, next));
      return next;
    });
  };

  const handleUnmarkReviewed = () => {
    if (!selectedToken || interactionDisabled) return;
    setReviewedTokenIds((prev) => {
      const next = new Set(prev);
      next.delete(selectedToken.id);
      return next;
    });
  };

  const handleRevert = () => {
    if (!selectedToken || interactionDisabled) return;
    setCorrections((prev) => {
      const next = { ...prev };
      delete next[selectedToken.id];
      return next;
    });
  };

  return (
    <>
      {toasts.length ? (
        <div className="toast-stack" role="status" aria-live="polite">
          {toasts.map((toast) => (
            <div
              key={toast.id}
              className={`toast toast-${toast.variant}`}
            >
              {toast.message}
            </div>
          ))}
        </div>
      ) : null}
      {settingsOpen ? (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <div className="modal-panel">
            <div className="modal-header">
              <div className="modal-title">Settings</div>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setSettingsOpen(false)}>
                Close
              </button>
            </div>
            <div className="modal-body vera-stack">
              <div className="settings-row">
                <span className="form-label">Ollama status</span>
                {ollamaHealth ? (
                  <span
                    className={`summary-badge ${
                      ollamaHealth.reachable ? "summary-badge-ai" : "summary-badge-offline"
                    }`}
                  >
                    {ollamaHealth.reachable ? "Connected" : "Not reachable"}
                  </span>
                ) : (
                  <span className="summary-badge summary-badge-offline">Checking...</span>
                )}
              </div>
              <label className="form-check">
                <input
                  type="checkbox"
                  checked={aiEnabled}
                  onChange={(event) => setAiEnabled(event.target.checked)}
                />
                <span className="form-check-label">Enable AI summaries (Ollama)</span>
              </label>
              {aiEnabled ? (
                <OllamaConsole
                  apiBase={apiBase}
                  selectedModel={selectedModel}
                  onSelectModel={setSelectedModel}
                  onToast={pushToast}
                  disabled={interactionDisabled}
                />
              ) : (
                <div className="form-hint">AI summaries are disabled. Offline summaries will be used.</div>
              )}
            </div>
          </div>
        </div>
      ) : null}
      <header className="header">
        <div className="header-left">
          <span className={`status-dot ${statusDotClass}`} />
          <span className="logo">VERA</span>
          <span className="header-divider">/</span>
          <span className="header-title">Verification-first OCR</span>
        </div>
        <div className="header-right">
          <span className="header-title">JPG, PNG, PDF</span>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setSettingsOpen(true)}>
            Settings
          </button>
        </div>
      </header>

      <main className="vera-main">
        <section className="vera-stack">
          <div className="card">
            <div className="card-header">
              <div className="card-title">Upload</div>
            </div>
            <div className="card-body vera-stack">
              <div className="vera-upload-actions">
                <input
                  type="file"
                  accept="image/png,image/jpeg,application/pdf"
                  onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                  disabled={interactionDisabled}
                />
                <button
                  type="button"
                  onClick={uploadDocument}
                  disabled={!file || interactionDisabled}
                  className="btn btn-primary"
                >
                  {processingActive ? "Processing..." : loading && !documentData ? "Uploading..." : "Run OCR"}
                </button>
              </div>
              {processingActive ? (
                <div className="processing-banner" role="status" aria-live="polite">
                  <div className="processing-info">
                    <div className="processing-title">Processing OCR</div>
                    <div className="processing-subtitle">Extracting text and confidence scores.</div>
                  </div>
                  <div className="processing-actions">
                    <button type="button" onClick={cancelProcessing} className="btn btn-secondary" disabled={loading}>
                      Cancel processing
                    </button>
                  </div>
                  <div className="processing-bar" aria-hidden="true">
                    <div className="processing-bar-fill" />
                  </div>
                </div>
              ) : null}
              {isProcessing && processingCanceled ? (
                <div className="alert alert-info processing-paused">
                  <span>Processing canceled locally. Resume status checks to fetch results.</span>
                  <button type="button" onClick={resumeProcessing} className="btn btn-secondary btn-sm">
                    Resume status checks
                  </button>
                </div>
              ) : null}
              {loading && !documentData ? (
                <div className="alert alert-info">
                  Running OCR. First run may download model assets.
                </div>
              ) : null}
              {processingActive ? (
                <div className="alert alert-info">OCR is running. Tokens will appear when processing completes.</div>
              ) : null}
              {documentData?.status === "canceled" ? (
                <div className="alert alert-error">Processing was canceled. Upload a new document to restart.</div>
              ) : null}
            </div>
          </div>

          <div className="vera-grid">
            <div className="vera-stack">
              <div className="card">
                <div className="card-header">
                  <div className="card-title">Document</div>
                  <div className="card-header-actions">
                    <button
                      type="button"
                      onClick={() => setShowAllTokens((prev) => !prev)}
                      className="btn btn-secondary btn-sm"
                      disabled={interactionDisabled || !documentData}
                    >
                      {showAllTokens ? "Show flagged tokens" : "Show all tokens"}
                    </button>
                    {documentData ? (
                      <span
                        className={`status-pill ${
                          documentData.status === "failed"
                            ? "status-pill-error"
                            : documentData.status === "canceled"
                            ? "status-pill-paused"
                            : isProcessing
                            ? processingCanceled
                              ? "status-pill-paused"
                              : "status-pill-processing"
                            : "status-pill-ready"
                        }`}
                      >
                        {documentData.status === "failed"
                          ? "Failed"
                          : documentData.status === "canceled"
                          ? "Canceled"
                          : isProcessing
                          ? processingCanceled
                            ? "Paused"
                            : "Processing"
                          : "Ready"}
                      </span>
                    ) : null}
                  </div>
                </div>
                <div className="card-body">
                  {documentData ? (
                    <ImageOverlay
                      imageUrl={documentData.image_url}
                      imageWidth={documentData.image_width}
                      imageHeight={documentData.image_height}
                      tokens={displayTokens}
                      selectedTokenId={selectedTokenId}
                      onSelect={setSelectedTokenId}
                      disabled={interactionDisabled}
                    />
                  ) : (
                    <div className="upload-zone">
                      <div className="upload-text">Drop a file to begin</div>
                      <div className="upload-hint">Supports JPG, PNG, and PDF</div>
                    </div>
                  )}
                </div>
              </div>

              <div className="card">
                <div className="card-header">
                  <div className="card-title">Summary</div>
                  <div className="card-header-actions">
                    {summarySource ? (
                      <span className={`summary-badge summary-badge-${summarySource}`}>
                        {summarySource === "ai" ? "AI" : "Offline"}
                      </span>
                    ) : null}
                    {summary ? (
                      <button
                        type="button"
                        onClick={refreshSummary}
                        disabled={interactionDisabled}
                        className="btn btn-secondary btn-sm"
                      >
                        Regenerate
                      </button>
                    ) : null}
                  </div>
                </div>
                <div className="card-body">
                  {summaryLoading ? (
                    <div className="processing-banner" role="status" aria-live="polite">
                      <div className="processing-info">
                        <div className="processing-title">Generating text</div>
                        <div className="processing-subtitle">
                          {aiEnabled ? "Waiting for Ollama response." : "Compiling summary."}
                        </div>
                      </div>
                      <div className="processing-bar" aria-hidden="true">
                        <div className="processing-bar-fill" />
                      </div>
                    </div>
                  ) : null}
                  <SummaryView
                    bulletSummary={summary?.bullet_summary ?? []}
                    structuredFields={summary?.structured_fields}
                  />
                </div>
              </div>
            </div>

            <aside className="vera-stack">
              <div className="card">
                <div className="card-header">
                  <div className="card-title">Uncertain text</div>
                </div>
                <div className="card-body vera-stack">
                  <div className="form-hint">
                    {flaggedTokens.length} uncertain items · {reviewedCount} reviewed
                  </div>
                  <div className="progress-bar">
                    <div className="progress-fill" style={{ width: `${reviewProgress}%` }} />
                  </div>
                  <div className="form-hint">
                    Uncertain text is flagged for low confidence or forced review.
                  </div>
                  <TokenList
                    tokens={flaggedTokens}
                    selectedTokenId={selectedTokenId}
                    onSelect={setSelectedTokenId}
                    reviewedTokenIds={reviewedTokenIds}
                    disabled={interactionDisabled}
                  />
                </div>
              </div>

              <div className="card">
                <div className="card-header">
                  <div className="card-title">Edit</div>
                </div>
                <div className="card-body vera-stack">
                  <CorrectionEditor
                    token={selectedToken}
                    value={correctionValue}
                    onChange={(value) => {
                      if (!selectedToken) return;
                      setCorrections((prev) => ({ ...prev, [selectedToken.id]: value }));
                    }}
                    onMarkReviewed={handleMarkReviewed}
                    onUnmarkReviewed={handleUnmarkReviewed}
                    onRevert={handleRevert}
                    disabled={interactionDisabled}
                    isReviewed={selectedToken ? reviewedTokenIds.has(selectedToken.id) : false}
                  />
                  <button
                    type="button"
                    onClick={confirmReview}
                    disabled={!documentData || interactionDisabled}
                    className="btn btn-primary"
                  >
                    Confirm and generate summary
                  </button>
                </div>
              </div>

              <div className="card">
                <div className="card-header">
                  <div className="card-title">Export</div>
                </div>
                <div className="card-body vera-stack">
                  <button
                    type="button"
                    onClick={() => exportDocument("json")}
                    disabled={!summary || interactionDisabled}
                    className="btn btn-secondary"
                  >
                    Export JSON
                  </button>
                  <button
                    type="button"
                    onClick={() => exportDocument("csv")}
                    disabled={!summary || interactionDisabled}
                    className="btn btn-secondary"
                  >
                    Export CSV
                  </button>
                  <button
                    type="button"
                    onClick={() => exportDocument("txt")}
                    disabled={!summary || interactionDisabled}
                    className="btn btn-secondary"
                  >
                    Export TXT
                  </button>
                </div>
              </div>
            </aside>
          </div>
        </section>
      </main>
    </>
  );
}
