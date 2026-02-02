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
    return <div style={{ opacity: 0.7 }}>Select a flagged token to review</div>;
  }

  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div style={{ fontSize: 12, letterSpacing: "0.06em", textTransform: "uppercase", color: "#7a5c22" }}>
        Review
      </div>
      <div>
        <div style={{ fontSize: 12, opacity: 0.7 }}>Original</div>
        <div style={{ fontWeight: 600 }}>{token.text || "(empty)"}</div>
      </div>
      <label style={{ display: "grid", gap: 6 }}>
        <span style={{ fontSize: 12, opacity: 0.7 }}>Correction</span>
        <input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          style={{
            padding: "10px 12px",
            borderRadius: 10,
            border: "1px solid #d6c6a4",
            fontFamily: "inherit",
          }}
        />
      </label>
      <button
        type="button"
        onClick={() => onSave(value)}
        style={{
          padding: "10px 12px",
          borderRadius: 10,
          border: "none",
          background: "#1f4b99",
          color: "#fff",
          fontWeight: 600,
          cursor: "pointer",
        }}
      >
        Save correction
      </button>
      <div style={{ display: "flex", gap: 8 }}>
        <button
          type="button"
          onClick={onMarkReviewed}
          style={{
            flex: 1,
            padding: "10px 12px",
            borderRadius: 10,
            border: "1px solid #d6c6a4",
            background: "#fff",
            cursor: "pointer",
          }}
        >
          Mark reviewed
        </button>
        <button
          type="button"
          onClick={onRevert}
          style={{
            flex: 1,
            padding: "10px 12px",
            borderRadius: 10,
            border: "1px solid #d6c6a4",
            background: "#fff",
            cursor: "pointer",
          }}
        >
          Revert
        </button>
      </div>
    </div>
  );
}
