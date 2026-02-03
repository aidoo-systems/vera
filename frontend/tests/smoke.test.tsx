import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import HomePage from "../app/page";

describe("HomePage", () => {
  it("renders the header copy", () => {
    render(<HomePage />);
    expect(screen.getByText(/Verification-first OCR/i)).toBeInTheDocument();
  });

  it("shows the summary placeholder before review", () => {
    render(<HomePage />);
    const placeholders = screen.getAllByText(/Summary will appear after review is confirmed/i);
    expect(placeholders.length).toBeGreaterThan(0);
  });

  it("disables OCR action until a file is selected", () => {
    render(<HomePage />);
    const buttons = screen.getAllByRole("button", { name: /Run OCR/i });
    buttons.forEach((button) => expect(button).toBeDisabled());
  });
});
