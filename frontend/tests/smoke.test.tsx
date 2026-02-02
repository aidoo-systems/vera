import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import HomePage from "../app/page";

describe("HomePage", () => {
  it("renders the header copy", () => {
    render(<HomePage />);
    expect(screen.getByText(/Validated Extraction/i)).toBeInTheDocument();
  });

  it("shows the summary placeholder before review", () => {
    render(<HomePage />);
    expect(screen.getByText(/Summary will appear after review is confirmed/i)).toBeInTheDocument();
  });

  it("disables OCR action until a file is selected", () => {
    render(<HomePage />);
    expect(screen.getByRole("button", { name: /Run OCR/i })).toBeDisabled();
  });
});
