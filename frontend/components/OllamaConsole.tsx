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

  const loadModels = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${apiBase}/llm/models`);
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
    try {
      const response = await fetch(`${apiBase}/llm/models/pull`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model }),
      });
      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || "Failed to pull model");
      }
      onToast(`Model download started: ${model}`, "info");
      setPullName("");
      await loadModels();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to pull model";
      onToast(message, "error");
    } finally {
      setPulling(false);
    }
  };

  useEffect(() => {
    loadModels();
  }, []);

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
            disabled={disabled}
          />
        </label>
        <button type="button" className="btn btn-secondary" onClick={pullModel} disabled={disabled || pulling}>
          {pulling ? "Downloading..." : "Download"}
        </button>
      </div>
    </div>
  );
}
