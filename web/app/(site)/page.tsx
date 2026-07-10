import ArtifactCard from "@/components/ArtifactCard";
import SearchBar from "@/components/SearchBar";
import { listArtifacts } from "@/lib/api";

export const revalidate = 300;

export default async function Home() {
  const artifacts = await listArtifacts();
  const flagship = [
    ...artifacts.filter((a) => a.flagship),
    ...artifacts.filter((a) => !a.flagship),
  ];

  return (
    <>
      <section className="desk">
        <p className="kicker">Circuits · parameters · capsules</p>
        <h1>The home for quantum artifacts.</h1>
        <p className="sub">
          Shareable, runnable, verifiable quantum work. Every circuit runs in
          your browser; every claim can carry a signed, content-addressed
          experiment capsule.
        </p>
        <SearchBar />
      </section>

      <div className="section-head">
        <h2>Flagship artifacts</h2>
        <span className="count">{artifacts.length} published</span>
      </div>
      <div className="grid">
        {flagship.map((a) => (
          <ArtifactCard key={`${a.owner}/${a.name}`} a={a} />
        ))}
      </div>
    </>
  );
}
