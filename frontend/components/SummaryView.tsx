type SummaryViewProps = {
  bulletSummary: string[];
  structuredFields?: Record<string, string>;
};

function isNotDetected(value: string | undefined) {
  return !value || value.toLowerCase().includes("not detected");
}

export function SummaryView({
  bulletSummary,
  structuredFields,
}: SummaryViewProps) {
  const hasStructuredFields = structuredFields && Object.keys(structuredFields).length > 0;
  const keywords = structuredFields?.keywords ?? "Not detected";
  const keywordList = keywords === "Not detected" ? [] : keywords.split(", ");
  const summaryPoints = structuredFields?.summary_points ?? "Not detected";
  const summaryPointList = summaryPoints === "Not detected" ? [] : summaryPoints.split(" | ");
  const documentType = structuredFields?.document_type ?? "Unknown";
  const typeConfidence = structuredFields?.document_type_confidence ?? "low";
  const reviewNote = bulletSummary.find((item) => item.toLowerCase().includes("reviewed"));

  return (
    <div className="vera-stack">
      {bulletSummary.length === 0 ? (
        <div className="form-hint">Summary will appear after review is confirmed.</div>
      ) : hasStructuredFields ? (
        <div className="summary-grid">
          <div className="summary-section">
            <div className="summary-heading">Overview</div>
            <div className="summary-metrics">
              <div className="summary-metric">
                <div className="summary-value">{structuredFields?.line_count ?? "0"}</div>
                <div className="summary-label">Lines</div>
              </div>
              <div className="summary-metric">
                <div className="summary-value">{structuredFields?.word_count ?? "0"}</div>
                <div className="summary-label">Words</div>
              </div>
              <div className="summary-metric">
                <div className="summary-value">{documentType}</div>
                <div className="summary-label">Type · {typeConfidence}</div>
              </div>
            </div>
          </div>

          <div className="summary-section">
            <div className="summary-heading">Summary points</div>
            {summaryPointList.length === 0 ? (
              <div className="form-hint">Not detected</div>
            ) : (
              <ul className="summary-points">
                {summaryPointList.map((point) => (
                  <li key={point} className="summary-point">
                    {point}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="summary-section">
            <div className="summary-heading">Detected patterns</div>
            <div className="summary-row">
              <div>
                <div className="summary-row-label">Dates</div>
                <div className="summary-row-value">{structuredFields?.dates ?? "Not detected"}</div>
              </div>
              <span className={`badge ${isNotDetected(structuredFields?.dates) ? "badge-warning" : "badge-success"}`}>
                {isNotDetected(structuredFields?.dates) ? "Needs input" : "Verified"}
              </span>
            </div>
            <div className="summary-row">
              <div>
                <div className="summary-row-label">Amounts</div>
                <div className="summary-row-value">{structuredFields?.amounts ?? "Not detected"}</div>
              </div>
              <span className={`badge ${isNotDetected(structuredFields?.amounts) ? "badge-warning" : "badge-success"}`}>
                {isNotDetected(structuredFields?.amounts) ? "Needs input" : "Verified"}
              </span>
            </div>
            <div className="summary-row">
              <div>
                <div className="summary-row-label">Invoice/Order IDs</div>
                <div className="summary-row-value">{structuredFields?.invoice_numbers ?? "Not detected"}</div>
              </div>
              <span
                className={`badge ${isNotDetected(structuredFields?.invoice_numbers) ? "badge-warning" : "badge-success"}`}
              >
                {isNotDetected(structuredFields?.invoice_numbers) ? "Needs input" : "Verified"}
              </span>
            </div>
            <div className="summary-row">
              <div>
                <div className="summary-row-label">Emails</div>
                <div className="summary-row-value">{structuredFields?.emails ?? "Not detected"}</div>
              </div>
              <span className={`badge ${isNotDetected(structuredFields?.emails) ? "badge-warning" : "badge-success"}`}>
                {isNotDetected(structuredFields?.emails) ? "Needs input" : "Verified"}
              </span>
            </div>
            <div className="summary-row">
              <div>
                <div className="summary-row-label">Phones</div>
                <div className="summary-row-value">{structuredFields?.phones ?? "Not detected"}</div>
              </div>
              <span className={`badge ${isNotDetected(structuredFields?.phones) ? "badge-warning" : "badge-success"}`}>
                {isNotDetected(structuredFields?.phones) ? "Needs input" : "Verified"}
              </span>
            </div>
            <div className="summary-row">
              <div>
                <div className="summary-row-label">Tax/VAT IDs</div>
                <div className="summary-row-value">{structuredFields?.tax_ids ?? "Not detected"}</div>
              </div>
              <span className={`badge ${isNotDetected(structuredFields?.tax_ids) ? "badge-warning" : "badge-success"}`}>
                {isNotDetected(structuredFields?.tax_ids) ? "Needs input" : "Verified"}
              </span>
            </div>
          </div>

          <div className="summary-section">
            <div className="summary-heading">Keywords</div>
            {keywordList.length === 0 ? (
              <div className="form-hint">Not detected</div>
            ) : (
              <div className="summary-chips">
                {keywordList.map((keyword) => (
                  <span key={keyword} className="summary-chip">
                    {keyword}
                  </span>
                ))}
              </div>
            )}
          </div>

          {reviewNote ? <div className="summary-review-note">{reviewNote}</div> : null}
        </div>
      ) : (
        <ul className="summary-list">
          {bulletSummary.map((item, index) => {
            const needsInput = item.toLowerCase().includes("not detected");
            return (
              <li key={index} className="summary-item">
                <span className="summary-text">{item}</span>
                <span className={`badge ${needsInput ? "badge-warning" : "badge-success"}`}>
                  {needsInput ? "Needs input" : "Verified"}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
