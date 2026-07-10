import { notFound } from "next/navigation";
import type { Metadata } from "next";
import CircuitSVG from "@/components/CircuitSVG";
import EmbedResizer from "@/components/EmbedResizer";
import RunPanel from "@/components/RunPanel";
import { getArtifact } from "@/lib/api";

export const metadata: Metadata = { robots: { index: false } };
export const revalidate = 3600;

// Chromeless runnable widget for papers, blogs, and courses.
export default async function EmbedPage({
  params,
}: {
  params: Promise<{ owner: string; artifact: string }>;
}) {
  const { owner, artifact } = await params;
  const name = decodeURIComponent(artifact).split("@")[0];
  const a = await getArtifact(owner, name);
  if (!a) notFound();

  return (
    <div style={{ padding: 16 }}>
      <EmbedResizer />
      <p className="small" style={{ margin: "0 0 4px" }}>
        <a
          href={`/${owner}/${name}`}
          target="_blank"
          rel="noopener"
          className="mono"
        >
          {owner}/{name}
        </a>{" "}
        <span className="muted">· QuantumVerse</span>
      </p>
      <CircuitSVG qasm={a.qasm} />
      <RunPanel qasm={a.qasm} numQubits={a.resources.qubits} />
    </div>
  );
}
