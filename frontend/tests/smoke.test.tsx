import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import HomePage from "../app/page";

describe("HomePage", () => {
  it("renders the header copy", () => {
    render(<HomePage />);
    expect(screen.getByText(/Validated Extraction/i)).toBeInTheDocument();
  });
});
