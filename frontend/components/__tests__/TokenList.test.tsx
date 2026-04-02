import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { TokenList } from "../TokenList";
import type { TokenBox } from "../ImageOverlay";

function makeToken(overrides: Partial<TokenBox> = {}): TokenBox {
  return {
    id: "tok-1",
    text: "receipt",
    confidence: 0.42,
    bbox: [10, 20, 100, 30],
    confidenceLabel: "low",
    forcedReview: false,
    flags: ["low-confidence"],
    ...overrides,
  };
}

const defaultProps = {
  selectedTokenId: null,
  onSelect: vi.fn(),
  reviewedTokenIds: new Set<string>(),
};

describe("TokenList", () => {
  it("renders an empty list when no tokens are provided", () => {
    render(<TokenList {...defaultProps} tokens={[]} />);
    const list = screen.getByRole("list");
    expect(list).toBeInTheDocument();
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });

  it("renders one list item per token", () => {
    const tokens = [makeToken({ id: "tok-1" }), makeToken({ id: "tok-2", text: "amount" })];
    render(<TokenList {...defaultProps} tokens={tokens} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("displays token text for each token", () => {
    const tokens = [makeToken({ id: "tok-1", text: "Total" }), makeToken({ id: "tok-2", text: "$42.00" })];
    render(<TokenList {...defaultProps} tokens={tokens} />);
    expect(screen.getByText("Total")).toBeInTheDocument();
    expect(screen.getByText("$42.00")).toBeInTheDocument();
  });

  it("displays (empty) for tokens with empty text", () => {
    const tokens = [makeToken({ id: "tok-1", text: "" })];
    render(<TokenList {...defaultProps} tokens={tokens} />);
    expect(screen.getByText("(empty)")).toBeInTheDocument();
  });

  it("shows 'Reviewed' status for reviewed tokens", () => {
    const tokens = [makeToken({ id: "tok-1" })];
    const reviewedTokenIds = new Set(["tok-1"]);
    render(<TokenList {...defaultProps} tokens={tokens} reviewedTokenIds={reviewedTokenIds} />);
    expect(screen.getByText("Reviewed")).toBeInTheDocument();
  });

  it("shows 'Needs review' status for unreviewed tokens", () => {
    const tokens = [makeToken({ id: "tok-1" })];
    render(<TokenList {...defaultProps} tokens={tokens} reviewedTokenIds={new Set()} />);
    expect(screen.getByText("Needs review")).toBeInTheDocument();
  });

  it("applies correct CSS class for reviewed status", () => {
    const tokens = [makeToken({ id: "tok-1" }), makeToken({ id: "tok-2" })];
    const reviewedTokenIds = new Set(["tok-1"]);
    render(<TokenList {...defaultProps} tokens={tokens} reviewedTokenIds={reviewedTokenIds} />);

    const reviewed = screen.getByText("Reviewed");
    const pending = screen.getByText("Needs review");

    expect(reviewed.className).toContain("token-status-reviewed");
    expect(pending.className).toContain("token-status-pending");
  });

  it("displays confidence label and formatted confidence value", () => {
    const tokens = [makeToken({ id: "tok-1", confidenceLabel: "low", confidence: 0.42, flags: ["low-confidence"] })];
    render(<TokenList {...defaultProps} tokens={tokens} />);
    expect(screen.getByText(/low · 0\.42 · low-confidence/)).toBeInTheDocument();
  });

  it("displays 'no flags' when token has no flags", () => {
    const tokens = [makeToken({ id: "tok-1", flags: [] })];
    render(<TokenList {...defaultProps} tokens={tokens} />);
    expect(screen.getByText(/no flags/)).toBeInTheDocument();
  });

  it("displays multiple flags joined by comma", () => {
    const tokens = [makeToken({ id: "tok-1", flags: ["low-confidence", "numeric-mismatch"] })];
    render(<TokenList {...defaultProps} tokens={tokens} />);
    expect(screen.getByText(/low-confidence, numeric-mismatch/)).toBeInTheDocument();
  });

  it("applies is-selected class to the selected token button", () => {
    const tokens = [makeToken({ id: "tok-1" }), makeToken({ id: "tok-2", text: "other" })];
    render(<TokenList {...defaultProps} tokens={tokens} selectedTokenId="tok-1" />);

    const buttons = screen.getAllByRole("button");
    expect(buttons[0].className).toContain("is-selected");
    expect(buttons[1].className).not.toContain("is-selected");
  });

  it("calls onSelect with the token id when a token is clicked", () => {
    const onSelect = vi.fn();
    const tokens = [makeToken({ id: "tok-1" }), makeToken({ id: "tok-2", text: "other" })];
    render(<TokenList {...defaultProps} tokens={tokens} onSelect={onSelect} />);

    const buttons = screen.getAllByRole("button");
    fireEvent.click(buttons[1]);

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith("tok-2");
  });

  it("disables all token buttons when disabled prop is true", () => {
    const tokens = [makeToken({ id: "tok-1" }), makeToken({ id: "tok-2", text: "other" })];
    render(<TokenList {...defaultProps} tokens={tokens} disabled={true} />);

    const buttons = screen.getAllByRole("button");
    for (const button of buttons) {
      expect(button).toBeDisabled();
    }
  });

  it("does not call onSelect when a disabled token is clicked", () => {
    const onSelect = vi.fn();
    const tokens = [makeToken({ id: "tok-1" })];
    render(<TokenList {...defaultProps} tokens={tokens} onSelect={onSelect} disabled={true} />);

    fireEvent.click(screen.getByRole("button"));
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("enables all token buttons by default", () => {
    const tokens = [makeToken({ id: "tok-1" })];
    render(<TokenList {...defaultProps} tokens={tokens} />);
    expect(screen.getByRole("button")).toBeEnabled();
  });

  it("formats confidence to two decimal places", () => {
    const tokens = [makeToken({ id: "tok-1", confidence: 0.5 })];
    render(<TokenList {...defaultProps} tokens={tokens} />);
    expect(screen.getByText(/0\.50/)).toBeInTheDocument();
  });
});
