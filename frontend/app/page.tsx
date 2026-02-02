"use client";

import { useMemo, useState } from "react";
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
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setLoading(false);
    }
  };

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
      setError(err instanceof Error ? err.message : "Validation failed");
    } finally {
      setLoading(false);
    }
  };

  const exportDocument = async (format: "json" | "csv") => {
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
      setError(err instanceof Error ? err.message : "Export failed");
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
    <main
      style={{
        minHeight: "100vh",
        padding: "28px",
        fontFamily: '"Spectral", "Georgia", serif',
        background: "linear-gradient(120deg, #f8efe2 0%, #f0f6ff 100%)",
        color: "#2b2b2b",
      }}
    >
      <header style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 12, letterSpacing: "0.24em", textTransform: "uppercase" }}>VERA</div>
        <h1 style={{ margin: "8px 0", fontSize: 36 }}>Validated Extraction &amp; Review Assistant</h1>
        <p style={{ maxWidth: 640, opacity: 0.8 }}>
          Review only the uncertain tokens. Confirm everything before summaries become available.
        </p>
      </header>

      <section style={{ display: "grid", gap: 20, gridTemplateColumns: "minmax(0, 1.2fr) minmax(0, 0.8fr)" }}>
        <div style={{ display: "grid", gap: 16 }}>
          <div
            style={{
              display: "grid",
              gap: 12,
              padding: 16,
              borderRadius: 16,
              background: "#fff9ef",
              border: "1px solid #e6d5b2",
            }}
          >
            <div style={{ fontSize: 12, letterSpacing: "0.2em", textTransform: "uppercase", color: "#7a5c22" }}>
              Upload
            </div>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <input
                type="file"
                accept="image/png,image/jpeg"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
              <button
                type="button"
                onClick={uploadDocument}
                disabled={!file || loading}
                style={{
                  padding: "8px 12px",
                  borderRadius: 10,
                  border: "none",
                  background: "#1f4b99",
                  color: "#fff",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                {loading ? "Uploading..." : "Run OCR"}
              </button>
            </div>
            {error ? <div style={{ color: "#c0392b" }}>{error}</div> : null}
          </div>

          {documentData ? (
            <ImageOverlay
              imageUrl={documentData.image_url}
              imageWidth={documentData.image_width}
              imageHeight={documentData.image_height}
              tokens={flaggedTokens}
              selectedTokenId={selectedTokenId}
              onSelect={setSelectedTokenId}
            />
          ) : (
            <div style={{ padding: 24, borderRadius: 16, background: "#f7f1e6", color: "#6b5b3e" }}>
              Upload a receipt or invoice image to start the review flow.
            </div>
          )}

          <SummaryView bulletSummary={summary?.bullet_summary ?? []} structuredFields={summary?.structured_fields ?? {}} />
        </div>

        <aside
          style={{
            background: "#fff9ef",
            borderRadius: 18,
            padding: 18,
            border: "1px solid #e6d5b2",
            display: "grid",
            gap: 18,
            alignContent: "start",
          }}
        >
          <div style={{ display: "grid", gap: 8 }}>
            <div style={{ fontSize: 12, letterSpacing: "0.2em", textTransform: "uppercase", color: "#7a5c22" }}>
              Review Queue
            </div>
            <div style={{ fontSize: 14, opacity: 0.8 }}>{flaggedTokens.length} tokens need review</div>
            <TokenList
              tokens={flaggedTokens}
              selectedTokenId={selectedTokenId}
              onSelect={setSelectedTokenId}
              reviewedTokenIds={reviewedTokenIds}
            />
          </div>

          <div style={{ borderTop: "1px solid #e6d5b2", paddingTop: 16 }}>
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
          </div>

          <div style={{ display: "grid", gap: 10 }}>
            <button
              type="button"
              onClick={() => saveProgress(false)}
              disabled={!documentData || loading}
              style={{
                marginTop: 8,
                padding: "12px 14px",
                borderRadius: 12,
                border: "1px solid #d6c6a4",
                background: "#fff",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Save progress
            </button>
            <button
              type="button"
              onClick={() => saveProgress(true)}
              disabled={!documentData || loading}
              style={{
                padding: "12px 14px",
                borderRadius: 12,
                border: "none",
                background: "#1f4b99",
                color: "#fff",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Confirm review and generate summary
            </button>
          </div>

          <div style={{ borderTop: "1px solid #e6d5b2", paddingTop: 16, display: "grid", gap: 10 }}>
            <button
              type="button"
              onClick={() => exportDocument("json")}
              disabled={!summary || loading}
              style={{
                padding: "10px 12px",
                borderRadius: 10,
                border: "1px solid #d6c6a4",
                background: "#fff",
                cursor: "pointer",
              }}
            >
              Export JSON
            </button>
            <button
              type="button"
              onClick={() => exportDocument("csv")}
              disabled={!summary || loading}
              style={{
                padding: "10px 12px",
                borderRadius: 10,
                border: "1px solid #d6c6a4",
                background: "#fff",
                cursor: "pointer",
              }}
            >
              Export CSV
            </button>
          </div>
        </aside>
      </section>
    </main>
  );
}
