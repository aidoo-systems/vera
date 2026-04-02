import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { CorrectionEditor } from "../CorrectionEditor";
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
  value: "receipt",
  onChange: vi.fn(),
  onMarkReviewed: vi.fn(),
  onUnmarkReviewed: vi.fn(),
  onRevert: vi.fn(),
};

describe("CorrectionEditor", () => {
  it("shows hint message when no token is selected", () => {
    render(<CorrectionEditor {...defaultProps} token={null} />);
    expect(screen.getByText("Select a flagged token to review")).toBeInTheDocument();
  });

  it("does not render input or buttons when no token is selected", () => {
    render(<CorrectionEditor {...defaultProps} token={null} />);
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("displays original token text", () => {
    const token = makeToken({ text: "Total: $42.00" });
    render(<CorrectionEditor {...defaultProps} token={token} />);
    expect(screen.getByText("Total: $42.00")).toBeInTheDocument();
  });

  it("displays (empty) for tokens with empty text", () => {
    const token = makeToken({ text: "" });
    render(<CorrectionEditor {...defaultProps} token={token} />);
    expect(screen.getByText("(empty)")).toBeInTheDocument();
  });

  it("renders correction input with current value", () => {
    const token = makeToken();
    render(<CorrectionEditor {...defaultProps} token={token} value="corrected" />);
    const input = screen.getByRole("textbox");
    expect(input).toHaveValue("corrected");
  });

  it("calls onChange when user types in the input", () => {
    const onChange = vi.fn();
    const token = makeToken();
    render(<CorrectionEditor {...defaultProps} token={token} onChange={onChange} value="" />);

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "fixed" } });
    expect(onChange).toHaveBeenCalledWith("fixed");
  });

  it("shows 'Mark reviewed' button when not reviewed", () => {
    const token = makeToken();
    render(<CorrectionEditor {...defaultProps} token={token} isReviewed={false} />);
    expect(screen.getByText("Mark reviewed")).toBeInTheDocument();
    expect(screen.queryByText("Mark unreviewed")).toBeNull();
  });

  it("shows 'Mark unreviewed' button when reviewed", () => {
    const token = makeToken();
    render(<CorrectionEditor {...defaultProps} token={token} isReviewed={true} />);
    expect(screen.getByText("Mark unreviewed")).toBeInTheDocument();
    expect(screen.queryByText("Mark reviewed")).toBeNull();
  });

  it("calls onMarkReviewed when 'Mark reviewed' is clicked", () => {
    const onMarkReviewed = vi.fn();
    const token = makeToken();
    render(<CorrectionEditor {...defaultProps} token={token} onMarkReviewed={onMarkReviewed} isReviewed={false} />);

    fireEvent.click(screen.getByText("Mark reviewed"));
    expect(onMarkReviewed).toHaveBeenCalledTimes(1);
  });

  it("calls onUnmarkReviewed when 'Mark unreviewed' is clicked", () => {
    const onUnmarkReviewed = vi.fn();
    const token = makeToken();
    render(
      <CorrectionEditor {...defaultProps} token={token} onUnmarkReviewed={onUnmarkReviewed} isReviewed={true} />,
    );

    fireEvent.click(screen.getByText("Mark unreviewed"));
    expect(onUnmarkReviewed).toHaveBeenCalledTimes(1);
  });

  it("calls onRevert when 'Revert' is clicked", () => {
    const onRevert = vi.fn();
    const token = makeToken();
    render(<CorrectionEditor {...defaultProps} token={token} onRevert={onRevert} />);

    fireEvent.click(screen.getByText("Revert"));
    expect(onRevert).toHaveBeenCalledTimes(1);
  });

  it("disables all interactive elements when disabled prop is true", () => {
    const token = makeToken();
    render(<CorrectionEditor {...defaultProps} token={token} disabled={true} />);

    expect(screen.getByRole("textbox")).toBeDisabled();
    const buttons = screen.getAllByRole("button");
    for (const button of buttons) {
      expect(button).toBeDisabled();
    }
  });

  it("enables all interactive elements by default", () => {
    const token = makeToken();
    render(<CorrectionEditor {...defaultProps} token={token} />);

    expect(screen.getByRole("textbox")).toBeEnabled();
    const buttons = screen.getAllByRole("button");
    for (const button of buttons) {
      expect(button).toBeEnabled();
    }
  });

  it("always renders the Revert button regardless of review state", () => {
    const token = makeToken();

    const { rerender } = render(<CorrectionEditor {...defaultProps} token={token} isReviewed={false} />);
    expect(screen.getByText("Revert")).toBeInTheDocument();

    rerender(<CorrectionEditor {...defaultProps} token={token} isReviewed={true} />);
    expect(screen.getByText("Revert")).toBeInTheDocument();
  });
});
