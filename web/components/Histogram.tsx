// Pure component (no hooks): renders server-side on capsule pages and
// client-side inside RunPanel. With `reference` counts it overlays a second
// distribution as outline bars so "consistent" is visible, not just a number.
// Values are duplicated in a visually hidden table for screen readers.

const MAX_BARS = 12;

export default function Histogram({
  counts,
  shots,
  reference,
  referenceLabel = "reference",
  label = "this run",
}: {
  counts: Record<string, number>;
  shots: number;
  reference?: Record<string, number>;
  referenceLabel?: string;
  label?: string;
}) {
  const refShots = reference
    ? Object.values(reference).reduce((a, b) => a + b, 0) || 1
    : 1;

  const keys = [
    ...new Set([...Object.keys(counts), ...Object.keys(reference ?? {})]),
  ].sort(
    (a, b) =>
      (reference?.[b] ?? 0) - (reference?.[a] ?? 0) ||
      (counts[b] ?? 0) - (counts[a] ?? 0),
  );
  const top = keys.slice(0, MAX_BARS);
  const rest = keys.slice(MAX_BARS).reduce((s, k) => s + (counts[k] ?? 0), 0);

  const frac = (k: string) => (counts[k] ?? 0) / shots;
  const refFrac = (k: string) =>
    reference ? (reference[k] ?? 0) / refShots : 0;
  const maxFrac = Math.max(...top.map((k) => Math.max(frac(k), refFrac(k))), 1e-9);

  return (
    <div>
      {reference && (
        <p className="hist-legend" aria-hidden="true">
          <span>
            <span className="swatch fill" /> {label}
          </span>
          <span>
            <span className="swatch ref" /> {referenceLabel}
          </span>
        </p>
      )}
      <div className="hist" aria-hidden="true">
        {top.map((bits) => {
          const v = counts[bits] ?? 0;
          return (
            <div key={bits} style={{ display: "contents" }}>
              <span className="bitstring">{bits}</span>
              <span className="track">
                <span
                  className="bar"
                  style={{ width: `${(frac(bits) / maxFrac) * 100}%` }}
                />
                {reference && (
                  <span
                    className="bar-ref"
                    style={{ width: `${(refFrac(bits) / maxFrac) * 100}%` }}
                  />
                )}
              </span>
              <span className="val">
                {v} · {((v / shots) * 100).toFixed(1)}%
              </span>
            </div>
          );
        })}
        {rest > 0 && (
          <div style={{ display: "contents" }}>
            <span className="bitstring muted">+{keys.length - MAX_BARS} more</span>
            <span className="track">
              <span
                className="bar"
                style={{ width: `${(rest / shots / maxFrac) * 100}%`, opacity: 0.4 }}
              />
            </span>
            <span className="val">{rest}</span>
          </div>
        )}
      </div>
      <table className="sr-only">
        <caption>
          Measurement counts over {shots} shots
          {reference ? ` compared against ${referenceLabel}` : ""}
        </caption>
        <thead>
          <tr>
            <th>Outcome</th>
            <th>Count</th>
            {reference && <th>Reference count</th>}
          </tr>
        </thead>
        <tbody>
          {keys.map((bits) => (
            <tr key={bits}>
              <td>{bits}</td>
              <td>{counts[bits] ?? 0}</td>
              {reference && <td>{reference[bits] ?? 0}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
