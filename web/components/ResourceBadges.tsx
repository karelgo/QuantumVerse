import type { CircuitResources } from "@/lib/circuit";

export default function ResourceBadges({
  r,
  compact = false,
}: {
  r: CircuitResources;
  compact?: boolean;
}) {
  const items: [string, number][] = compact
    ? [
        ["qubits", r.qubits],
        ["depth", r.depth],
        ["gates", r.gateCount],
      ]
    : [
        ["qubits", r.qubits],
        ["depth", r.depth],
        ["gates", r.gateCount],
        ["2q gates", r.twoQubitCount],
        ["T-count", r.tCount],
      ];
  return (
    <span className="badges">
      {items.map(([label, value]) => (
        <span className="rbadge" key={label}>
          <b>{value}</b> {label}
        </span>
      ))}
    </span>
  );
}
