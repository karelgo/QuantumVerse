import Link from "next/link";
import ResourceBadges from "./ResourceBadges";
import type { ArtifactSummary } from "@/lib/types";

export default function ArtifactCard({ a }: { a: ArtifactSummary }) {
  return (
    <Link href={`/${a.owner}/${a.name}`} className="card artifact-card">
      <span className="ref">
        <span className="owner">{a.owner} /</span> {a.name}
      </span>
      <span className="desc">{a.description}</span>
      <span className="card-foot">
        <span className="chip kind">{a.kind}</span>
        <ResourceBadges r={a.resources} compact />
        {a.capsuleCount > 0 && (
          <span className={`chip${(a.maxTrustLevel ?? 0) > 0 ? " good" : ""}`}>
            {(a.maxTrustLevel ?? 0) > 0 ? "✓ " : ""}
            {a.capsuleCount} capsule{a.capsuleCount > 1 ? "s" : ""}
          </span>
        )}
      </span>
    </Link>
  );
}
