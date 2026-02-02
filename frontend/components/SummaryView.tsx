type SummaryViewProps = {
  bulletSummary: string[];
  structuredFields: Record<string, string>;
};

export function SummaryView({ bulletSummary, structuredFields }: SummaryViewProps) {
  return (
    <div>
      <h2>Summary</h2>
      <ul>
        {bulletSummary.map((item, index) => (
          <li key={index}>{item}</li>
        ))}
      </ul>
      <h3>Structured Fields</h3>
      <pre>{JSON.stringify(structuredFields, null, 2)}</pre>
    </div>
  );
}
