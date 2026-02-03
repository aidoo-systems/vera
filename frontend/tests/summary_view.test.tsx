import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { SummaryView } from "../components/SummaryView";

describe("SummaryView", () => {
  it("renders summary points and detected patterns", () => {
    render(
      <SummaryView
        bulletSummary={["Summary points: Vendor: Acme"]}
        structuredFields={{
          line_count: "3",
          word_count: "12",
          summary_points: "Vendor: Acme | Total: $12.00",
          dates: "2026-02-01",
          amounts: "$12.00",
          invoice_numbers: "INV-1001",
          emails: "billing@example.com",
          phones: "+1 (415) 555-0100",
          tax_ids: "GB123456789",
          document_type: "Invoice/Receipt",
          document_type_confidence: "low",
          keywords: "acme, invoice",
        }}
      />
    );

    expect(screen.getByText(/Summary points/i)).toBeInTheDocument();
    expect(screen.getByText(/Invoice\/Order IDs/i)).toBeInTheDocument();
    expect(screen.getByText(/INV-1001/i)).toBeInTheDocument();
    expect(screen.getByText(/billing@example.com/i)).toBeInTheDocument();
  });
});
