import type { TokenBox } from "./ImageOverlay";

type TokenListProps = {
  tokens: TokenBox[];
  selectedTokenId: string | null;
  onSelect: (tokenId: string) => void;
  reviewedTokenIds: Set<string>;
};

export function TokenList({ tokens, selectedTokenId, onSelect, reviewedTokenIds }: TokenListProps) {
  return (
    <ul className="token-list">
      {tokens.map((token) => (
        <li key={token.id}>
          <button
            type="button"
            onClick={() => onSelect(token.id)}
            className={`token-button${token.id === selectedTokenId ? " is-selected" : ""}`}
          >
            <div className="token-title">
              <span>{token.text || "(empty)"}</span>
              <span className="token-meta">
                {reviewedTokenIds.has(token.id) ? "Reviewed" : "Needs review"}
              </span>
            </div>
            <div className="token-meta">
              {token.confidenceLabel} · {token.confidence.toFixed(2)} · {token.flags.join(", ") || "no flags"}
            </div>
          </button>
        </li>
      ))}
    </ul>
  );
}
