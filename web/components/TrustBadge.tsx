import type { TrustLevel } from "@/lib/types";

// Absence is the signal: unsigned capsules get no badge in lists, and an
// honest dashed chip where the trust level must be stated (capsule pages).

export default function TrustBadge({
  level,
  verbose = false,
}: {
  level: TrustLevel;
  verbose?: boolean;
}) {
  if (level === 2) return <span className="chip good">✓ provider-verified</span>;
  if (level === 1) return <span className="chip good">✓ author-signed</span>;
  if (verbose) return <span className="chip dashed">unsigned</span>;
  return null;
}
