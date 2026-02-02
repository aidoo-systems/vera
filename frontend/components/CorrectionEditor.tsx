import type { TokenBox } from "./ImageOverlay";

type CorrectionEditorProps = {
  token: TokenBox | null;
  value: string;
  onChange: (value: string) => void;
  onSave: (value: string) => void;
  onMarkReviewed: () => void;
  onRevert: () => void;
};

export function CorrectionEditor({
  token,
  value,
  onChange,
  onSave,
  onMarkReviewed,
  onRevert,
}: CorrectionEditorProps) {
  if (!token) {
    return <div className="form-hint">Select a flagged token to review</div>;
  }

  return (
    <div className="vera-stack">
      <div className="form-group">
        <span className="form-label">Original</span>
        <div>{token.text || "(empty)"}</div>
      </div>
      <label className="form-group">
        <span className="form-label">Correction</span>
        <input value={value} onChange={(event) => onChange(event.target.value)} className="form-input" />
      </label>
      <button type="button" onClick={() => onSave(value)} className="btn btn-primary">
        Save correction
      </button>
      <div className="form-row">
        <button type="button" onClick={onMarkReviewed} className="btn btn-secondary">
          Mark reviewed
        </button>
        <button type="button" onClick={onRevert} className="btn btn-secondary">
          Revert
        </button>
      </div>
    </div>
  );
}
