import type { Metadata } from "next";
import ArtifactCard from "@/components/ArtifactCard";
import SearchBar from "@/components/SearchBar";
import { searchArtifacts } from "@/lib/api";

export const metadata: Metadata = { title: "Explore" };

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q = "" } = await searchParams;
  const results = await searchArtifacts(q);

  return (
    <>
      <div style={{ maxWidth: 680 }}>
        <SearchBar defaultValue={q} autoFocus />
      </div>
      <div className="section-head">
        <h2>{q ? `Results for “${q}”` : "All artifacts"}</h2>
        <span className="count">
          {results.length} artifact{results.length === 1 ? "" : "s"}
        </span>
      </div>
      {results.length ? (
        <div className="grid">
          {results.map((a) => (
            <ArtifactCard key={`${a.owner}/${a.name}`} a={a} />
          ))}
        </div>
      ) : (
        <p className="muted">
          Nothing matches. Try a gate name, a tag like “vqe”, or an owner.
        </p>
      )}
    </>
  );
}
