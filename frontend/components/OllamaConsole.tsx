import { useEffect, useState } from "react";

type OllamaConsoleProps = {
  apiBase: string;
  selectedModel: string;
  onSelectModel: (value: string) => void;
  onToast: (message: string, variant?: "error" | "info") => void;
  disabled?: boolean;
};

export function OllamaConsole({ apiBase, selectedModel, onSelectModel, onToast, disabled = false }: OllamaConsoleProps) {
  const [models, setModels] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [pulling, setPulling] = useState(false);
  const [pullName, setPullName] = useState("");
  const [pullProgress, setPullProgress] = useState<number | null>(null);
  const [pullStatus, setPullStatus] = useState<string | null>(null);
  const [pullingModel, setPullingModel] = useState<string | null>(null);
  const [pullController, setPullController] = useState<AbortController | null>(null);

  const parseErrorMessage = async (response: Response, fallback: string) => {
    try {
      const text = await response.text();
      if (!text) return fallback;
      try {
        const data = JSON.parse(text) as { detail?: string; error?: string };
        if (data.detail) return data.detail;
        if (data.error) return data.error;
      } catch {
        return text;
      }
    } catch {
      return fallback;
    }
    return fallback;
  };

  const loadModels = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${apiBase}/llm/models`, { credentials: "include" });
      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || "Failed to load models");
      }
      const data = (await response.json()) as { models: string[] };
      setModels(data.models ?? []);
      if (data.models?.length && !data.models.includes(selectedModel)) {
        onSelectModel(data.models[0]);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load models";
      onToast(message, "error");
    } finally {
      setLoading(false);
    }
  };

  const pullModel = async () => {
    const model = pullName.trim();
    if (!model) return;
    setPulling(true);
    setPullProgress(0);
    setPullStatus("Starting download...");
    setPullingModel(model);
    const controller = new AbortController();
    setPullController(controller);
    try {
      const response = await fetch(`${apiBase}/llm/models/pull/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ model }),
        signal: controller.signal,
      });
      if (!response.ok) {
        const message = await parseErrorMessage(response, "Failed to pull model");
        throw new Error(message);
      }
      if (!response.body) {
        throw new Error("No download stream available");
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let completed = false;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;
          try {
            const event = JSON.parse(trimmed) as {
              status?: string;
              total?: number;
              completed?: number;
              error?: string;
            };
            if (event.error) {
              throw new Error(event.error);
            }
            if (typeof event.total === "number" && typeof event.completed === "number" && event.total > 0) {
              const percent = Math.min(100, Math.round((event.completed / event.total) * 100));
              setPullProgress(percent);
            }
            if (event.status) {
              setPullStatus(event.status);
              if (event.status.toLowerCase() === "success") {
                completed = true;
              }
            }
          } catch (err) {
            if (err instanceof Error) {
              throw err;
            }
          }
        }
      }

      if (completed) {
        onToast(`Model download completed: ${model}`, "info");
        setPullName("");
        await loadModels();
      } else {
        onToast(`Model download finished: ${model}`, "info");
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        onToast(`Model download canceled: ${model}`, "info");
      } else {
        const message = err instanceof Error ? err.message : "Failed to pull model";
        onToast(message, "error");
      }
    } finally {
      setPulling(false);
      setPullController(null);
      setPullStatus(null);
      setPullProgress(null);
      setPullingModel(null);
    }
  };

  const cancelPull = () => {
    if (!pullController) return;
    setPullStatus("Canceling...");
    pullController.abort();
  };

  useEffect(() => {
    loadModels();
  }, []);

  useEffect(() => {
    return () => {
      pullController?.abort();
    };
  }, [pullController]);

  return (
    <div className="ollama-console">
      <div className="ollama-header">
        <div>
          <div className="ollama-title">LLM models</div>
          <div className="form-hint">Connects to Ollama for optional summaries.</div>
        </div>
        <button type="button" className="btn btn-secondary btn-sm" onClick={loadModels} disabled={disabled || loading}>
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>
      <div className="ollama-row">
        <label className="form-group">
          <span className="form-label">Available models</span>
          <select
            className="summary-select"
            value={selectedModel}
            onChange={(event) => onSelectModel(event.target.value)}
            disabled={disabled || models.length === 0}
          >
            {models.length === 0 ? <option value="">No models found</option> : null}
            {models.map((model) => (
              <option key={model} value={model}>
                {model}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="ollama-row">
        <label className="form-group">
          <span className="form-label">Download model</span>
          <input
            className="form-input"
            value={pullName}
            onChange={(event) => setPullName(event.target.value)}
            placeholder="e.g. llama3.1"
            disabled={disabled || pulling}
          />
        </label>
        <button type="button" className="btn btn-secondary" onClick={pullModel} disabled={disabled || pulling}>
          {pulling ? "Downloading..." : "Download"}
        </button>
      </div>
      {pulling ? (
        <div className="ollama-progress" role="status" aria-live="polite">
          <div className="ollama-progress-meta">
            <span>{pullStatus ?? "Downloading model..."}</span>
            <span>{pullProgress !== null ? `${pullProgress}%` : ""}</span>
          </div>
          <div className="progress-bar" aria-hidden="true">
            <div
              className={`progress-fill${pullProgress === null ? " is-indeterminate" : ""}`}
              style={pullProgress !== null ? { width: `${pullProgress}%` } : undefined}
            />
          </div>
          <div className="ollama-progress-actions">
            <span className="form-hint">Downloading {pullingModel ?? "model"} from Ollama.</span>
            <button type="button" className="btn btn-secondary btn-sm" onClick={cancelPull} disabled={disabled}>
              Cancel download
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
