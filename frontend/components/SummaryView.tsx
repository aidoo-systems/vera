type SummaryViewProps = {
  bulletSummary: string[];
};

export function SummaryView({ bulletSummary }: SummaryViewProps) {
  return (
    <div className="vera-stack">
      {bulletSummary.length === 0 ? (
        <div className="form-hint">Summary will appear after review is confirmed.</div>
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
