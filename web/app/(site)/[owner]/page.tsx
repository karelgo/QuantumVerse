import { notFound } from "next/navigation";
import type { Metadata } from "next";
import ArtifactCard from "@/components/ArtifactCard";
import { getOwner, listArtifacts } from "@/lib/api";

export const revalidate = 300;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ owner: string }>;
}): Promise<Metadata> {
  const { owner } = await params;
  return { title: owner };
}

export default async function OwnerPage({
  params,
}: {
  params: Promise<{ owner: string }>;
}) {
  const { owner: handle } = await params;
  const owner = await getOwner(handle);
  if (!owner) notFound();
  const artifacts = (await listArtifacts()).filter((a) => a.owner === handle);

  return (
    <>
      <p className="crumbs">{owner.handle}</p>
      <div className="artifact-title">
        <h1>{owner.display}</h1>
        <span className="chip kind">{owner.kind}</span>
      </div>
      <p className="muted" style={{ maxWidth: "62ch" }}>
        {owner.bio}
      </p>
      {owner.signing_key && (
        <p className="small muted mono">
          signing key (Ed25519) · {owner.signing_key.slice(0, 24)}…
        </p>
      )}

      <div className="section-head">
        <h2>Artifacts</h2>
        <span className="count">{artifacts.length}</span>
      </div>
      <div className="grid">
        {artifacts.map((a) => (
          <ArtifactCard key={a.name} a={a} />
        ))}
      </div>
    </>
  );
}
