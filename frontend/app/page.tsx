"use client";

import { useEffect, useMemo, useState } from "react";
import { CorrectionEditor } from "../components/CorrectionEditor";
import { ImageOverlay, type TokenBox } from "../components/ImageOverlay";
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
  const isProcessing = documentData ? ["uploaded", "processing"].includes(documentData.status) : false;

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

  const uploadDocument = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    setSummary(null);
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
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!documentData || !isProcessing) return;
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
  }, [apiBase, documentData, isProcessing]);

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

  const saveProgress = async (reviewComplete: boolean) => {
    if (!documentData) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${apiBase}/documents/${documentData.document_id}/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          corrections: buildCorrectionsPayload(),
          reviewed_token_ids: Array.from(reviewedTokenIds),
          review_complete: reviewComplete,
        }),
      });

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || "Validation failed");
      }

      if (reviewComplete) {
        const summaryResponse = await fetch(`${apiBase}/documents/${documentData.document_id}/summary`);
        if (!summaryResponse.ok) {
          const message = await summaryResponse.text();
          throw new Error(message || "Summary failed");
        }
        const summaryData = (await summaryResponse.json()) as SummaryPayload;
        setSummary(summaryData);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Validation failed";
      console.error("Validation failed", err);
      setError(message);
    } finally {
      setLoading(false);
    }
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
    } finally {
      setLoading(false);
    }
  };

  const handleMarkReviewed = () => {
    if (!selectedToken) return;
    setReviewedTokenIds((prev) => new Set([...prev, selectedToken.id]));
  };

  const handleRevert = () => {
    if (!selectedToken) return;
    setCorrections((prev) => {
      const next = { ...prev };
      delete next[selectedToken.id];
      return next;
    });
  };

  return (
    <>
      {loading && !documentData ? (
        <div className="loading-overlay" role="status" aria-live="polite">
          <div className="loading-panel">
            <div className="daisy" aria-hidden="true">
              <span className="daisy-petal" />
              <span className="daisy-petal" />
              <span className="daisy-petal" />
              <span className="daisy-petal" />
              <span className="daisy-petal" />
              <span className="daisy-petal" />
              <span className="daisy-petal" />
              <span className="daisy-petal" />
              <span className="daisy-core" />
            </div>
            <div className="loading-title">Running OCR</div>
            <div className="form-hint">First run may download model assets.</div>
          </div>
        </div>
      ) : null}
      <header className="header">
        <div className="header-left">
          <span className={`status-dot ${documentData ? "status-ready" : "status-indexing"}`} />
          <span className="logo">VERA</span>
          <span className="header-divider">/</span>
          <span className="header-title">Verification-first OCR</span>
        </div>
        <div className="header-right">
          <span className="header-title">JPG, PNG, PDF</span>
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
                />
                <button type="button" onClick={uploadDocument} disabled={!file || loading} className="btn btn-primary">
                  {loading ? "Uploading..." : "Run OCR"}
                </button>
                <label className="form-check">
                  <input
                    type="checkbox"
                    checked={showAllTokens}
                    onChange={(event) => setShowAllTokens(event.target.checked)}
                  />
                  <span className="form-check-label">Show all tokens</span>
                </label>
              </div>
              {loading && !documentData ? (
                <div className="alert alert-info">
                  Running OCR. First run may download model assets.
                </div>
              ) : null}
              {isProcessing ? (
                <div className="alert alert-info">OCR is running. Tokens will appear when processing completes.</div>
              ) : null}
              {error ? <div className="alert alert-error">{error}</div> : null}
            </div>
          </div>

          <div className="vera-grid">
            <div className="vera-stack">
              <div className="card">
                <div className="card-header">
                  <div className="card-title">Document</div>
                  {documentData ? (
                    <span
                      className={`status-pill ${
                        documentData.status === "failed"
                          ? "status-pill-error"
                          : isProcessing
                          ? "status-pill-processing"
                          : "status-pill-ready"
                      }`}
                    >
                      {documentData.status === "failed"
                        ? "Failed"
                        : isProcessing
                        ? "Processing"
                        : "Ready"}
                    </span>
                  ) : null}
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
                </div>
                <div className="card-body">
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
                  <div className="card-title">Review</div>
                </div>
                <div className="card-body vera-stack">
                  <div className="form-hint">
                    {flaggedTokens.length} uncertain items · {reviewedCount} confirmed
                  </div>
                  <div className="progress-bar">
                    <div className="progress-fill" style={{ width: `${reviewProgress}%` }} />
                  </div>
                  <TokenList
                    tokens={flaggedTokens}
                    selectedTokenId={selectedTokenId}
                    onSelect={setSelectedTokenId}
                    reviewedTokenIds={reviewedTokenIds}
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
                    onSave={(value) => {
                      if (!selectedToken) return;
                      setCorrections((prev) => ({ ...prev, [selectedToken.id]: value }));
                      setReviewedTokenIds((prev) => new Set([...prev, selectedToken.id]));
                    }}
                    onMarkReviewed={handleMarkReviewed}
                    onRevert={handleRevert}
                  />
                  <div className="vera-stack">
                    <button
                      type="button"
                      onClick={() => saveProgress(false)}
                      disabled={!documentData || loading}
                      className="btn btn-secondary"
                    >
                      Save progress
                    </button>
                    <button
                      type="button"
                      onClick={() => saveProgress(true)}
                      disabled={!documentData || loading}
                      className="btn btn-primary"
                    >
                      Confirm and generate summary
                    </button>
                  </div>
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
                    disabled={!summary || loading}
                    className="btn btn-secondary"
                  >
                    Export JSON
                  </button>
                  <button
                    type="button"
                    onClick={() => exportDocument("csv")}
                    disabled={!summary || loading}
                    className="btn btn-secondary"
                  >
                    Export CSV
                  </button>
                  <button
                    type="button"
                    onClick={() => exportDocument("txt")}
                    disabled={!summary || loading}
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
