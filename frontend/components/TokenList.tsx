import type { TokenBox } from "./ImageOverlay";

type TokenListProps = {
  tokens: TokenBox[];
  selectedTokenId: string | null;
  onSelect: (tokenId: string) => void;
  reviewedTokenIds: Set<string>;
};

export function TokenList({ tokens, selectedTokenId, onSelect, reviewedTokenIds }: TokenListProps) {
  return (
    <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 8 }}>
      {tokens.map((token) => (
        <li key={token.id}>
          <button
            type="button"
            onClick={() => onSelect(token.id)}
            style={{
              width: "100%",
              textAlign: "left",
              borderRadius: 12,
              padding: "10px 12px",
              border: token.id === selectedTokenId ? "2px solid #1f4b99" : "1px solid #d6c6a4",
              background: token.confidenceLabel === "low" || token.forcedReview ? "#fdeaea" : "#fff6da",
              fontFamily: "inherit",
            }}
          >
            <div style={{ fontWeight: 600, display: "flex", justifyContent: "space-between", gap: 8 }}>
              <span>{token.text || "(empty)"}</span>
              <span style={{ fontSize: 12, opacity: 0.7 }}>
                {reviewedTokenIds.has(token.id) ? "Reviewed" : "Needs review"}
              </span>
            </div>
            <div style={{ fontSize: 12, opacity: 0.75 }}>
              {token.confidenceLabel} · {token.confidence.toFixed(2)} · {token.flags.join(", ") || "no flags"}
            </div>
          </button>
        </li>
      ))}
    </ul>
  );
}
