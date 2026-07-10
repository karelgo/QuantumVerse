// Pure component (no hooks): renders server-side on capsule pages and
// client-side inside RunPanel. Values are duplicated in a visually hidden
// table for screen readers.

const MAX_BARS = 12;

export default function Histogram({
  counts,
  shots,
}: {
  counts: Record<string, number>;
  shots: number;
}) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const top = entries.slice(0, MAX_BARS);
  const rest = entries.slice(MAX_BARS).reduce((s, [, v]) => s + v, 0);
  const max = top.length ? top[0][1] : 1;

  return (
    <div>
      <div className="hist" aria-hidden="true">
        {top.map(([bits, v]) => (
          <div key={bits} style={{ display: "contents" }}>
            <span className="bitstring">{bits}</span>
            <span className="track">
              <span className="bar" style={{ width: `${(v / max) * 100}%` }} />
            </span>
            <span className="val">
              {v} · {((v / shots) * 100).toFixed(1)}%
            </span>
          </div>
        ))}
        {rest > 0 && (
          <div style={{ display: "contents" }}>
            <span className="bitstring muted">
              +{entries.length - MAX_BARS} more
            </span>
            <span className="track">
              <span
                className="bar"
                style={{ width: `${(rest / max) * 100}%`, opacity: 0.4 }}
              />
            </span>
            <span className="val">{rest}</span>
          </div>
        )}
      </div>
      <table className="sr-only">
        <caption>Measurement counts over {shots} shots</caption>
        <thead>
          <tr>
            <th>Outcome</th>
            <th>Count</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([bits, v]) => (
            <tr key={bits}>
              <td>{bits}</td>
              <td>{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
