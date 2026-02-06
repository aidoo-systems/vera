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
  page_count: number;
  review_complete: boolean;
  pages: Array<{
    page_id: string;
    page_index: number;
    image_url: string;
    image_width?: number;
    image_height?: number;
    status: string;
    review_complete: boolean;
    version?: number;
  }>;
  structured_fields: Record<string, string>;
};

type PagePayload = {
  document_id: string;
  page_id: string;
  page_index: number;
  image_url: string;
  image_width: number;
  image_height: number;
  status: string;
  review_complete: boolean;
  version?: number;
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

type PageStatusPayload = {
  page_id: string;
  page_index: number;
  status: string;
  review_complete: boolean;
  token_count: number;
  forced_review_count: number;
  updated_at: string | null;
  version: number;
};

type DocumentStatusPayload = {
  document_id: string;
  status: string;
  review_complete: boolean;
  pages: PageStatusPayload[];
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

const getResponseMessage = async (response: Response, fallback: string) => {
  let detail = "";
  let bodyText = "";
  try {
    bodyText = await response.text();
  } catch {
    bodyText = "";
  }
  if (bodyText) {
    try {
      const data = JSON.parse(bodyText) as { detail?: string };
      if (typeof data.detail === "string") {
        detail = data.detail;
      }
    } catch {
      detail = bodyText;
    }
  }

  if (response.status === 409 && detail === "Review incomplete") {
    return "Please review all required tokens before generating the summary.";
  }

  if (response.status === 409 && detail === "Review out of date") {
    return "This page was updated elsewhere. Refresh and try again.";
  }

  if (response.status === 409 && detail === "Document not validated") {
    return "Finish the review before generating a summary or export.";
  }

  if (response.status === 503 && detail === "Background worker is not available") {
    return "The background worker isn't running. Start it and try again.";
  }

  if (response.status === 413 && detail === "File exceeds upload size limit") {
    return "The file is too large. Please upload a smaller document.";
  }

  if (response.status === 429) {
    return "You're uploading too quickly. Please wait a moment and try again.";
  }

  return detail || fallback;
};

function severityScore(token: TokenBox) {
  if (token.confidenceLabel === "low") return 3;
  if (token.forcedReview) return 2;
  return 1;
}

export default function HomePage() {
  const [selectedTokenId, setSelectedTokenId] = useState<string | null>(null);
  const [documentData, setDocumentData] = useState<DocumentPayload | null>(null);
  const [pageData, setPageData] = useState<PagePayload | null>(null);
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [correctionsByPage, setCorrectionsByPage] = useState<Record<string, Record<string, string>>>({});
  const [reviewedTokenIdsByPage, setReviewedTokenIdsByPage] = useState<Record<string, Set<string>>>({});
  const [pageSummaries, setPageSummaries] = useState<Record<string, SummaryPayload>>({});
  const [pageSummarySources, setPageSummarySources] = useState<Record<string, "ai" | "offline">>({});
  const [documentSummary, setDocumentSummary] = useState<SummaryPayload | null>(null);
  const [documentSummarySource, setDocumentSummarySource] = useState<"ai" | "offline" | null>(null);
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
  const [ollamaHealth, setOllamaHealth] = useState<{ reachable: boolean } | null>(null);
  const [ollamaWarned, setOllamaWarned] = useState(false);
  const [pageSummaryLoading, setPageSummaryLoading] = useState(false);
  const [documentSummaryLoading, setDocumentSummaryLoading] = useState(false);
  const [statusStreamActive, setStatusStreamActive] = useState(false);
  const isProcessing = documentData
    ? documentData.pages.some((page) => ["uploaded", "processing"].includes(page.status))
    : false;
  const processingActive = isProcessing && pollingEnabled;
  const interactionDisabled = loading || processingActive;
  const statusDotClass = isProcessing ? "status-indexing" : "status-ready";
  const ollamaConnected = Boolean(ollamaHealth?.reachable);
  const aiToggleDisabled = interactionDisabled || !ollamaConnected;

  const pageStatusClass = (status: string, reviewed: boolean) => {
    if (reviewed) return "status-pill-ready";
    if (status === "failed") return "status-pill-error";
    if (status === "canceled") return "status-pill-paused";
    if (["uploaded", "processing"].includes(status)) return "status-pill-processing";
    return "status-pill-ready";
  };

  const activeCorrections = useMemo(() => {
    if (!selectedPageId) return {};
    return correctionsByPage[selectedPageId] ?? {};
  }, [correctionsByPage, selectedPageId]);

  const activeReviewedTokenIds = useMemo(() => {
    if (!selectedPageId) return new Set<string>();
    return reviewedTokenIdsByPage[selectedPageId] ?? new Set<string>();
  }, [reviewedTokenIdsByPage, selectedPageId]);

  const activePageSummary = selectedPageId ? pageSummaries[selectedPageId] ?? null : null;
  const activePageSummarySource = selectedPageId ? pageSummarySources[selectedPageId] ?? null : null;

  const allTokens = useMemo<TokenBox[]>(() => {
    if (!pageData) return [];
    return pageData.tokens.map((token) => ({
      id: token.id,
      text: token.text,
      confidence: token.confidence,
      confidenceLabel: token.confidence_label,
      forcedReview: token.forced_review,
      flags: token.flags,
      bbox: token.bbox,
    }));
  }, [pageData]);

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
  const correctionValue = selectedToken ? activeCorrections[selectedToken.id] ?? selectedToken.text : "";
  const displayTokens = showAllTokens ? allTokens : flaggedTokens;

  const reviewedCount = flaggedTokens.filter((token) => activeReviewedTokenIds.has(token.id)).length;
  const reviewProgress = flaggedTokens.length ? Math.round((reviewedCount / flaggedTokens.length) * 100) : 0;
  const reviewedPages = documentData ? documentData.pages.filter((page) => page.review_complete).length : 0;
  const pageProgress = documentData?.pages.length ? Math.round((reviewedPages / documentData.pages.length) * 100) : 0;
  const remainingCount = Math.max(flaggedTokens.length - reviewedCount, 0);
  const selectedPageIndex = documentData
    ? documentData.pages.findIndex((page) => page.page_id === selectedPageId)
    : -1;
  const currentPageNumber = selectedPageIndex >= 0 ? selectedPageIndex + 1 : 0;
  const totalPages = documentData?.pages.length ?? 0;

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
    setPageSummaries({});
    setPageSummarySources({});
    setDocumentSummary(null);
    setDocumentSummarySource(null);
    setPageSummaryLoading(false);
    setDocumentSummaryLoading(false);
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
        const message = await getResponseMessage(response, "Upload failed");
        throw new Error(message);
      }

      const data = (await response.json()) as DocumentPayload;
      const pagesWithUrls = data.pages.map((page) => ({
        ...page,
        image_url: `${apiBase}${page.image_url}`,
      }));
      const nextDocument = {
        ...data,
        image_url: `${apiBase}${data.image_url}`,
        pages: pagesWithUrls,
      };
      setDocumentData(nextDocument);
      setCorrectionsByPage({});
      setReviewedTokenIdsByPage({});
      setSelectedTokenId(null);
      if (pagesWithUrls.length) {
        const firstPageId = pagesWithUrls[0].page_id;
        setSelectedPageId(firstPageId);
        await fetchPage(nextDocument.document_id, firstPageId);
      } else {
        setSelectedPageId(null);
        setPageData(null);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Upload failed";
      console.error("Upload failed", err);
      setError(message);
      pushToast(message, "error");
    } finally {
      setLoading(false);
    }
  };

  const fetchPage = async (documentId: string, pageId: string) => {
    try {
      const response = await fetch(`${apiBase}/documents/${documentId}/pages/${pageId}`);
      if (!response.ok) {
        const message = await getResponseMessage(response, "Failed to load page");
        throw new Error(message);
      }
      const data = (await response.json()) as PagePayload;
      setPageData({
        ...data,
        image_url: `${apiBase}${data.image_url}`,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load page";
      console.error("Page fetch failed", err);
      setError(message);
      pushToast(message, "error");
    }
  };

  const refreshDocument = async () => {
    if (!documentData) return;
    const response = await fetch(`${apiBase}/documents/${documentData.document_id}`);
    if (!response.ok) {
      const message = await getResponseMessage(response, "Failed to refresh document");
      throw new Error(message);
    }
    const data = (await response.json()) as DocumentPayload;
    const pagesWithUrls = data.pages.map((page) => ({
      ...page,
      image_url: `${apiBase}${page.image_url}`,
    }));
    setDocumentData({
      ...data,
      image_url: `${apiBase}${data.image_url}`,
      pages: pagesWithUrls,
    });
  };

  const applyStatusUpdate = (statusData: DocumentStatusPayload) => {
    setDocumentData((prev) => {
      if (!prev) return prev;
      const pageMap = new Map(statusData.pages.map((page) => [page.page_id, page]));
      const nextPages = prev.pages.map((page) => {
        const update = pageMap.get(page.page_id);
        if (!update) return page;
        return {
          ...page,
          status: update.status,
          review_complete: update.review_complete,
          version: update.version ?? page.version,
        };
      });
      return {
        ...prev,
        status: statusData.status ?? prev.status,
        review_complete: statusData.review_complete ?? prev.review_complete,
        pages: nextPages,
      };
    });

    if (pageData) {
      const update = statusData.pages.find((page) => page.page_id === pageData.page_id);
      if (update) {
        if (update.status === "ocr_done" && pageData.status !== "ocr_done" && documentData) {
          void fetchPage(documentData.document_id, pageData.page_id);
        }
        setPageData((prev) =>
          prev
            ? {
                ...prev,
                status: update.status,
                review_complete: update.review_complete,
                version: update.version ?? prev.version,
              }
            : prev
        );
      }
    }
  };

  const fetchPageStatuses = async () => {
    if (!documentData) return;
    const response = await fetch(`${apiBase}/documents/${documentData.document_id}/pages/status`);
    if (!response.ok) {
      const message = await getResponseMessage(response, "Failed to load status");
      throw new Error(message);
    }
    const statusData = (await response.json()) as DocumentStatusPayload;
    applyStatusUpdate(statusData);
    return statusData;
  };

  useEffect(() => {
    if (!documentData || !processingActive || statusStreamActive) return;
    const interval = window.setInterval(async () => {
      try {
        const statusData = await fetchPageStatuses();
        if (!statusData) return;
        const nextPage = statusData.pages.find((page) => page.page_id === selectedPageId);
        if (nextPage && nextPage.status === "ocr_done" && pageData?.status !== "ocr_done") {
          await fetchPage(documentData.document_id, selectedPageId!);
        }
        if (statusData.status === "failed") {
          setError("OCR processing failed. Please retry or upload a different document.");
          window.clearInterval(interval);
        }
      } catch (err) {
        console.error("Status polling failed", err);
      }
    }, 1500);
    return () => window.clearInterval(interval);
  }, [apiBase, documentData, processingActive, selectedPageId, pageData, statusStreamActive]);

  useEffect(() => {
    if (!documentData || !pollingEnabled) return;
    if (typeof window === "undefined" || !("EventSource" in window)) return;

    const stream = new EventSource(`${apiBase}/documents/${documentData.document_id}/status/stream`);
    const handleMessage = (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data) as DocumentStatusPayload;
        if ((payload as { error?: string }).error) {
          return;
        }
        applyStatusUpdate(payload);
        if (payload.status === "failed") {
          setError("OCR processing failed. Please retry or upload a different document.");
        }
      } catch (err) {
        console.error("Status stream parse failed", err);
      }
    };

    const handleOpen = () => {
      setStatusStreamActive(true);
    };

    const handleError = () => {
      stream.close();
      setStatusStreamActive(false);
    };

    stream.addEventListener("message", handleMessage);
    stream.addEventListener("open", handleOpen);
    stream.addEventListener("error", handleError);

    return () => {
      stream.removeEventListener("message", handleMessage);
      stream.removeEventListener("open", handleOpen);
      stream.removeEventListener("error", handleError);
      stream.close();
      setStatusStreamActive(false);
    };
  }, [apiBase, documentData, pollingEnabled]);

  useEffect(() => {
    if (selectedPageId || !documentData?.pages.length) return;
    setSelectedPageId(documentData.pages[0].page_id);
  }, [documentData, selectedPageId]);

  useEffect(() => {
    if (!documentData || !selectedPageId) return;
    if (pageData?.page_id === selectedPageId) return;
    fetchPage(documentData.document_id, selectedPageId);
  }, [documentData, pageData?.page_id, selectedPageId]);

  const buildCorrectionsPayload = () => {
    const payload: Array<{ token_id: string; corrected_text: string }> = [];
    Object.entries(activeCorrections).forEach(([tokenId, value]) => {
      const original = tokenById.get(tokenId)?.text;
      if (original !== undefined && value !== original) {
        payload.push({ token_id: tokenId, corrected_text: value });
      }
    });
    return payload;
  };

  const confirmReview = async () => {
    if (!documentData || !pageData) return;
    if (aiEnabled && !selectedModel) {
      pushToast("Select a model before generating AI summaries.", "error");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(
        `${apiBase}/documents/${documentData.document_id}/pages/${pageData.page_id}/validate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            corrections: buildCorrectionsPayload(),
            reviewed_token_ids: Array.from(activeReviewedTokenIds),
            review_complete: true,
            page_version: pageData.version ?? null,
          }),
        }
      );

      if (!response.ok) {
        const message = await getResponseMessage(response, "Validation failed");
        throw new Error(message);
      }

      setPageSummaryLoading(true);
      try {
        await requestPageSummary();
        await fetchPage(documentData.document_id, pageData.page_id);
        await refreshDocument();
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
      setPageSummaryLoading(false);
      setLoading(false);
    }
  };

  const requestPageSummary = async () => {
    if (!documentData || !pageData) return;
    const useAi = aiEnabled && selectedModel;
    if (aiEnabled && !selectedModel) {
      throw new Error("Select a model to generate AI summaries.");
    }
    const modelParam = useAi ? `?model=${encodeURIComponent(selectedModel)}` : "";
    const summaryResponse = await fetch(
      `${apiBase}/documents/${documentData.document_id}/pages/${pageData.page_id}/summary${modelParam}`
    );
    if (!summaryResponse.ok) {
      const message = await getResponseMessage(summaryResponse, "Summary failed");
      throw new Error(message);
    }
    const summaryData = (await summaryResponse.json()) as SummaryPayload;
    const pageKey = selectedPageId ?? pageData.page_id;
    setPageSummaries((prev) => ({ ...prev, [pageKey]: summaryData }));
    setPageSummarySources((prev) => ({ ...prev, [pageKey]: useAi ? "ai" : "offline" }));
  };

  const requestDocumentSummary = async () => {
    if (!documentData) return;
    const useAi = aiEnabled && selectedModel;
    if (aiEnabled && !selectedModel) {
      throw new Error("Select a model to generate AI summaries.");
    }
    const modelParam = useAi ? `?model=${encodeURIComponent(selectedModel)}` : "";
    const summaryResponse = await fetch(`${apiBase}/documents/${documentData.document_id}/summary${modelParam}`);
    if (!summaryResponse.ok) {
      const message = await getResponseMessage(summaryResponse, "Summary failed");
      throw new Error(message);
    }
    const summaryData = (await summaryResponse.json()) as SummaryPayload;
    setDocumentSummary(summaryData);
    setDocumentSummarySource(useAi ? "ai" : "offline");
  };

  const exportDocument = async (format: "json" | "csv" | "txt") => {
    if (!documentData) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${apiBase}/documents/${documentData.document_id}/export?format=${format}`);
      if (!response.ok) {
        const message = await getResponseMessage(response, "Export failed");
        throw new Error(message);
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

  const exportPage = async (format: "json" | "csv" | "txt") => {
    if (!documentData || !pageData) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(
        `${apiBase}/documents/${documentData.document_id}/pages/${pageData.page_id}/export?format=${format}`
      );
      if (!response.ok) {
        const message = await getResponseMessage(response, "Export failed");
        throw new Error(message);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `vera-export-page-${pageData.page_index + 1}.${format}`;
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


  const refreshPageSummary = async () => {
    if (!activePageSummary || !documentData || !pageData) return;
    setLoading(true);
    setPageSummaryLoading(true);
    setError(null);
    try {
      await requestPageSummary();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Summary failed";
      console.error("Summary failed", err);
      setError(message);
      pushToast(message, "error");
    } finally {
      setPageSummaryLoading(false);
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!aiEnabled || !pageData?.review_complete) return;
    if (pageSummaryLoading) return;
    if (activePageSummarySource === "ai") return;
    if (!selectedModel) return;
    generatePageSummary();
  }, [
    aiEnabled,
    pageData?.review_complete,
    selectedPageId,
    activePageSummarySource,
    selectedModel,
    pageSummaryLoading,
  ]);

  const generatePageSummary = async () => {
    if (!documentData || !pageData) return;
    setLoading(true);
    setPageSummaryLoading(true);
    setError(null);
    try {
      await requestPageSummary();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Summary failed";
      console.error("Summary failed", err);
      setError(message);
      pushToast(message, "error");
    } finally {
      setPageSummaryLoading(false);
      setLoading(false);
    }
  };

  const refreshDocumentSummary = async () => {
    if (!documentSummary || !documentData) return;
    setLoading(true);
    setDocumentSummaryLoading(true);
    setError(null);
    try {
      await requestDocumentSummary();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Summary failed";
      console.error("Summary failed", err);
      setError(message);
      pushToast(message, "error");
    } finally {
      setDocumentSummaryLoading(false);
      setLoading(false);
    }
  };

  const generateDocumentSummary = async () => {
    if (!documentData) return;
    setLoading(true);
    setDocumentSummaryLoading(true);
    setError(null);
    try {
      await requestDocumentSummary();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Summary failed";
      console.error("Summary failed", err);
      setError(message);
      pushToast(message, "error");
    } finally {
      setDocumentSummaryLoading(false);
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
    let mounted = true;
    const pollHealth = async () => {
      if (!mounted) return;
      await fetchOllamaHealth();
    };
    pollHealth();
    const interval = window.setInterval(pollHealth, 5000);
    return () => {
      mounted = false;
      window.clearInterval(interval);
    };
  }, [settingsOpen]);

  useEffect(() => {
    if (!aiEnabled || !ollamaHealth || ollamaHealth.reachable) return;
    if (!ollamaWarned) {
      pushToast("Ollama is not reachable from the backend. AI summaries may fail.", "error");
      setOllamaWarned(true);
    }
  }, [aiEnabled, ollamaHealth, ollamaWarned]);

  useEffect(() => {
    if (!aiEnabled || !ollamaHealth || ollamaHealth.reachable) return;
    setAiEnabled(false);
  }, [aiEnabled, ollamaHealth]);

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
        const message = await getResponseMessage(response, "Cancel failed");
        throw new Error(message);
      }
      const data = (await response.json()) as { status: string };
      setDocumentData((prev) =>
        prev
          ? {
              ...prev,
              status: data.status,
              pages: prev.pages.map((page) => ({ ...page, status: data.status })),
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
    if (!selectedToken || interactionDisabled || !selectedPageId) return;
    setReviewedTokenIdsByPage((prev) => {
      const next = { ...prev };
      const current = new Set(next[selectedPageId] ?? []);
      current.add(selectedToken.id);
      next[selectedPageId] = current;
      setSelectedTokenId(findNextTokenId(selectedToken.id, current));
      return next;
    });
  };

  const handleUnmarkReviewed = () => {
    if (!selectedToken || interactionDisabled || !selectedPageId) return;
    setReviewedTokenIdsByPage((prev) => {
      const next = { ...prev };
      const current = new Set(next[selectedPageId] ?? []);
      current.delete(selectedToken.id);
      next[selectedPageId] = current;
      return next;
    });
  };

  const handleRevert = () => {
    if (!selectedToken || interactionDisabled || !selectedPageId) return;
    setCorrectionsByPage((prev) => {
      const next = { ...prev };
      const pageCorrections = { ...(next[selectedPageId] ?? {}) };
      delete pageCorrections[selectedToken.id];
      next[selectedPageId] = pageCorrections;
      return next;
    });
  };

  const jumpToNextUnreviewed = () => {
    if (!flaggedTokens.length || interactionDisabled) return;
    const unreviewed = flaggedTokens.find((token) => !activeReviewedTokenIds.has(token.id));
    if (!unreviewed) return;
    setSelectedTokenId(unreviewed.id);
  };

  const goToPage = async (nextIndex: number) => {
    if (!documentData) return;
    const nextPage = documentData.pages[nextIndex];
    if (!nextPage) return;
    setSelectedPageId(nextPage.page_id);
    setSelectedTokenId(null);
    await fetchPage(documentData.document_id, nextPage.page_id);
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
                  disabled={aiToggleDisabled}
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
              ) : !ollamaConnected ? (
                <div className="form-hint">Connect to Ollama to enable AI summaries.</div>
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
              <div className="card document-card">
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
                <div className="card-body document-card-body">
                  {documentData ? (
                    <div className="vera-stack">
                      {totalPages > 1 ? (
                        <>
                          <div className="page-toolbar">
                            <div className="page-indicator">
                              Page {currentPageNumber || 1} of {totalPages || 1}
                            </div>
                            <div className="page-actions">
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={() => goToPage(Math.max(selectedPageIndex - 1, 0))}
                                disabled={interactionDisabled || selectedPageIndex <= 0}
                              >
                                Previous
                              </button>
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={() => goToPage(Math.min(selectedPageIndex + 1, totalPages - 1))}
                                disabled={interactionDisabled || selectedPageIndex < 0 || selectedPageIndex >= totalPages - 1}
                              >
                                Next
                              </button>
                            </div>
                          </div>
                          <div className="page-strip" role="tablist" aria-label="Document pages">
                            {documentData.pages.map((page) => (
                              <button
                                key={page.page_id}
                                type="button"
                                role="tab"
                                aria-selected={page.page_id === selectedPageId}
                                className={`page-thumb${page.page_id === selectedPageId ? " is-active" : ""}`}
                                onClick={async () => {
                                  setSelectedPageId(page.page_id);
                                  setSelectedTokenId(null);
                                  await fetchPage(documentData.document_id, page.page_id);
                                }}
                                disabled={interactionDisabled}
                              >
                                <img src={page.image_url} alt={`Page ${page.page_index + 1}`} />
                                <span className="page-thumb-label">Page {page.page_index + 1}</span>
                                <span
                                  className={`page-thumb-status status-pill ${pageStatusClass(
                                    page.status,
                                    page.review_complete
                                  )}`}
                                >
                                  {page.review_complete
                                    ? "Reviewed"
                                    : page.status === "ocr_done"
                                    ? "Ready"
                                    : page.status === "failed"
                                    ? "Failed"
                                    : page.status === "canceled"
                                    ? "Canceled"
                                    : "Processing"}
                                </span>
                                {['uploaded', 'processing'].includes(page.status) ? (
                                  <span className="page-thumb-progress" aria-hidden="true" />
                                ) : null}
                              </button>
                            ))}
                          </div>
                        </>
                      ) : null}
                      {pageData ? (
                        <ImageOverlay
                          imageUrl={pageData.image_url}
                          imageWidth={pageData.image_width}
                          imageHeight={pageData.image_height}
                          tokens={displayTokens}
                          selectedTokenId={selectedTokenId}
                          onSelect={setSelectedTokenId}
                          disabled={interactionDisabled}
                        />
                      ) : (
                        <div className="upload-zone">
                          <div className="upload-text">Loading page…</div>
                          <div className="upload-hint">Fetching tokens and image data.</div>
                        </div>
                      )}
                    </div>
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
                  <div className="card-title">Page summary</div>
                  <div className="card-header-actions">
                    {activePageSummarySource ? (
                      <span className={`summary-badge summary-badge-${activePageSummarySource}`}>
                        {activePageSummarySource === "ai" ? "AI" : "Offline"}
                      </span>
                    ) : null}
                    {!activePageSummary && pageData?.review_complete ? (
                      <button
                        type="button"
                        onClick={generatePageSummary}
                        disabled={interactionDisabled}
                        className="btn btn-secondary btn-sm"
                      >
                        Generate
                      </button>
                    ) : null}
                    {activePageSummary ? (
                      <button
                        type="button"
                        onClick={refreshPageSummary}
                        disabled={interactionDisabled}
                        className="btn btn-secondary btn-sm"
                      >
                        Regenerate
                      </button>
                    ) : null}
                  </div>
                </div>
                <div className="card-body">
                  {pageSummaryLoading ? (
                    <div className="processing-banner" role="status" aria-live="polite">
                      <div className="processing-info">
                        <div className="processing-title">Generating page summary</div>
                        <div className="processing-subtitle">
                          {aiEnabled ? "Waiting for Ollama response." : "Compiling summary."}
                        </div>
                      </div>
                      <div className="processing-bar" aria-hidden="true">
                        <div className="processing-bar-fill" />
                      </div>
                    </div>
                  ) : null}
                  {pageData && !pageData.review_complete ? (
                    <div className="summary-review-note">Complete this page review to generate its summary.</div>
                  ) : null}
                  <SummaryView
                    bulletSummary={activePageSummary?.bullet_summary ?? []}
                    structuredFields={activePageSummary?.structured_fields}
                  />
                </div>
              </div>

              {totalPages > 1 ? (
                <div className="card">
                  <div className="card-header">
                    <div className="card-title">Document summary</div>
                    <div className="card-header-actions">
                      {documentSummarySource ? (
                        <span className={`summary-badge summary-badge-${documentSummarySource}`}>
                          {documentSummarySource === "ai" ? "AI" : "Offline"}
                        </span>
                      ) : null}
                      {!documentSummary && documentData?.review_complete ? (
                        <button
                          type="button"
                          onClick={generateDocumentSummary}
                          disabled={interactionDisabled}
                          className="btn btn-secondary btn-sm"
                        >
                          Generate
                        </button>
                      ) : null}
                      {documentSummary ? (
                        <button
                          type="button"
                          onClick={refreshDocumentSummary}
                          disabled={interactionDisabled}
                          className="btn btn-secondary btn-sm"
                        >
                          Regenerate
                        </button>
                      ) : null}
                    </div>
                  </div>
                  <div className="card-body">
                    {documentSummaryLoading ? (
                      <div className="processing-banner" role="status" aria-live="polite">
                        <div className="processing-info">
                          <div className="processing-title">Generating document summary</div>
                          <div className="processing-subtitle">
                            {aiEnabled ? "Waiting for Ollama response." : "Compiling summary."}
                          </div>
                        </div>
                        <div className="processing-bar" aria-hidden="true">
                          <div className="processing-bar-fill" />
                        </div>
                      </div>
                    ) : null}
                    {documentData && !documentData.review_complete ? (
                      <div className="summary-review-note">Complete all pages to unlock the document summary.</div>
                    ) : null}
                    <SummaryView
                      bulletSummary={documentSummary?.bullet_summary ?? []}
                      structuredFields={documentSummary?.structured_fields}
                    />
                  </div>
                </div>
              ) : null}
            </div>

            <aside className="vera-stack review-column">
              <div className="review-stack">
                <div className="card review-card">
                  <div className="card-header">
                    <div className="card-title">Uncertain text</div>
                  </div>
                  <div className="card-body vera-stack review-card-body" aria-live="polite">
                    <div className="review-metrics">
                      <div className="form-hint">
                        {flaggedTokens.length} uncertain items · {reviewedCount} reviewed · {remainingCount} remaining
                      </div>
                      <button
                        type="button"
                        onClick={jumpToNextUnreviewed}
                        disabled={interactionDisabled || remainingCount === 0}
                        className="btn btn-secondary btn-sm"
                      >
                        Jump to next
                      </button>
                    </div>
                    <div className="progress-bar">
                      <div className="progress-fill" style={{ width: `${reviewProgress}%` }} />
                    </div>
                    <div className="form-hint">
                      Pages reviewed: {reviewedPages}/{documentData?.pages.length ?? 0} · {pageProgress}% complete
                    </div>
                    <div className="form-hint">
                      Uncertain text is flagged for low confidence or forced review.
                    </div>
                    <TokenList
                      tokens={flaggedTokens}
                      selectedTokenId={selectedTokenId}
                      onSelect={setSelectedTokenId}
                      reviewedTokenIds={activeReviewedTokenIds}
                      disabled={interactionDisabled}
                    />
                  </div>
                </div>

                <div className="card review-card">
                  <div className="card-header">
                    <div className="card-title">Edit</div>
                  </div>
                  <div className="card-body vera-stack review-card-body">
                    <CorrectionEditor
                      token={selectedToken}
                      value={correctionValue}
                      onChange={(value) => {
                        if (!selectedToken || !selectedPageId) return;
                        setCorrectionsByPage((prev) => ({
                          ...prev,
                          [selectedPageId]: {
                            ...(prev[selectedPageId] ?? {}),
                            [selectedToken.id]: value,
                          },
                        }));
                      }}
                      onMarkReviewed={handleMarkReviewed}
                      onUnmarkReviewed={handleUnmarkReviewed}
                      onRevert={handleRevert}
                      disabled={interactionDisabled}
                      isReviewed={selectedToken ? activeReviewedTokenIds.has(selectedToken.id) : false}
                    />
                    <button
                      type="button"
                      onClick={confirmReview}
                      disabled={!documentData || !pageData || interactionDisabled}
                      className="btn btn-primary"
                    >
                      Confirm page review & summary
                    </button>
                  </div>
                </div>
              </div>

              <div className="card">
                <div className="card-header">
                  <div className="card-title">Export</div>
                </div>
                <div className="card-body vera-stack">
                  <div className="summary-section">
                    <div className="summary-heading">Page export</div>
                    <button
                      type="button"
                      onClick={() => exportPage("json")}
                      disabled={!pageData?.review_complete || interactionDisabled}
                      className="btn btn-secondary"
                    >
                      Export page JSON
                    </button>
                    <button
                      type="button"
                      onClick={() => exportPage("csv")}
                      disabled={!pageData?.review_complete || interactionDisabled}
                      className="btn btn-secondary"
                    >
                      Export page CSV
                    </button>
                    <button
                      type="button"
                      onClick={() => exportPage("txt")}
                      disabled={!pageData?.review_complete || interactionDisabled}
                      className="btn btn-secondary"
                    >
                      Export page TXT
                    </button>
                  </div>
                  {totalPages > 1 ? (
                    <div className="summary-section">
                      <div className="summary-heading">Document export</div>
                      <button
                        type="button"
                        onClick={() => exportDocument("json")}
                        disabled={!documentData?.review_complete || interactionDisabled}
                        className="btn btn-secondary"
                      >
                        Export JSON
                      </button>
                      <button
                        type="button"
                        onClick={() => exportDocument("csv")}
                        disabled={!documentData?.review_complete || interactionDisabled}
                        className="btn btn-secondary"
                      >
                        Export CSV
                      </button>
                      <button
                        type="button"
                        onClick={() => exportDocument("txt")}
                        disabled={!documentData?.review_complete || interactionDisabled}
                        className="btn btn-secondary"
                      >
                        Export TXT
                      </button>
                    </div>
                  ) : null}
                </div>
              </div>
            </aside>
          </div>
        </section>
      </main>
    </>
  );
}
