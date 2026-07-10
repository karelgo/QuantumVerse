import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import CircuitSVG from "@/components/CircuitSVG";
import CodeTabs from "@/components/CodeTabs";
import ResourceBadges from "@/components/ResourceBadges";
import RunPanel from "@/components/RunPanel";
import TrustBadge from "@/components/TrustBadge";
import { getArtifact } from "@/lib/api";
import { toQiskit, loadSnippet } from "@/lib/codegen";
import { parseQasm } from "@/lib/qasm";
import { formatDate, formatRadians } from "@/lib/format";

function parseSlug(slug: string): { name: string; version: string | null } {
  const [name, version] = decodeURIComponent(slug).split("@");
  return { name, version: version ?? null };
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ owner: string; artifact: string }>;
}): Promise<Metadata> {
  const { owner, artifact } = await params;
  const { name } = parseSlug(artifact);
  const a = await getArtifact(owner, name);
  return {
    title: a ? `${owner}/${name}` : "Not found",
    description: a?.description,
  };
}

export default async function ArtifactPage({
  params,
}: {
  params: Promise<{ owner: string; artifact: string }>;
}) {
  const { owner, artifact } = await params;
  const { name, version } = parseSlug(artifact);
  const a = await getArtifact(owner, name);
  if (!a) notFound();

  const ref = `${owner}/${name}`;
  const pinned = version ?? a.version;

  return (
    <>
      <p className="crumbs">
        <Link href={`/${owner}`}>{owner}</Link>
        <span className="sep">/</span>
        <span>{name}</span>
      </p>
      <div className="artifact-title">
        <h1>{name}</h1>
        <span className="chip kind">{a.kind}</span>
        <span className="chip">v{pinned}</span>
        {a.maxTrustLevel !== null && <TrustBadge level={a.maxTrustLevel} />}
      </div>
      <p style={{ maxWidth: "68ch" }}>{a.description}</p>

      {/* Circuit Card — resources auto-populated from the artifact bytes */}
      <section className="card panel" style={{ marginTop: 20 }}>
        <ResourceBadges r={a.resources} />
        <table className="meta-table" style={{ marginTop: 14 }}>
          <tbody>
            <tr>
              <th scope="row">Format</th>
              <td>OpenQASM 3 (framework-agnostic; exports via adapters)</td>
            </tr>
            <tr>
              <th scope="row">Gate mix</th>
              <td className="mono">
                {Object.entries(a.resources.gates)
                  .sort((x, y) => y[1] - x[1])
                  .map(([g, c]) => `${g}×${c}`)
                  .join("  ")}
              </td>
            </tr>
            <tr>
              <th scope="row">License</th>
              <td>{a.license}</td>
            </tr>
            <tr>
              <th scope="row">Published</th>
              <td>{formatDate(a.created)}</td>
            </tr>
            <tr>
              <th scope="row">Tags</th>
              <td>
                <span className="badges">
                  {a.tags.map((t) => (
                    <Link
                      key={t}
                      href={`/search?q=${encodeURIComponent(t)}`}
                      className="chip"
                    >
                      {t}
                    </Link>
                  ))}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <h2>Circuit</h2>
      <div className="card">
        <CircuitSVG qasm={a.qasm} />
      </div>

      {a.parameters && (
        <>
          <h2>Trained parameters</h2>
          <section className="card panel">
            <table className="meta-table">
              <tbody>
                {a.parameters.observable && (
                  <tr>
                    <th scope="row">Observable</th>
                    <td className="mono">{a.parameters.observable}</td>
                  </tr>
                )}
                {a.parameters.energy !== undefined && (
                  <tr>
                    <th scope="row">Converged value</th>
                    <td className="mono">
                      {a.parameters.energy} {a.parameters.units ?? ""}
                    </td>
                  </tr>
                )}
                {a.parameters.optimizer && (
                  <tr>
                    <th scope="row">Optimizer</th>
                    <td>
                      {a.parameters.optimizer}
                      {a.parameters.iterations
                        ? ` · ${a.parameters.iterations} iterations`
                        : ""}
                    </td>
                  </tr>
                )}
                <tr>
                  <th scope="row">Values</th>
                  <td className="mono">
                    {a.parameters.names
                      .map(
                        (n, i) =>
                          `${n} = ${formatRadians(a.parameters!.values[i])}`,
                      )
                      .join(",  ")}
                  </td>
                </tr>
              </tbody>
            </table>
          </section>
        </>
      )}

      <h2>Use it</h2>
      <CodeTabs
        tabs={[
          { label: "qv.load", code: loadSnippet(ref, a.kind) },
          { label: "OpenQASM 3", code: a.qasm.trim() },
          { label: "Qiskit", code: toQiskit(parseQasm(a.qasm), ref) },
        ]}
      />

      <h2>Run</h2>
      <section className="card panel">
        <RunPanel qasm={a.qasm} numQubits={a.resources.qubits} />
      </section>

      {a.capsules.length > 0 && (
        <>
          <h2>Experiment capsules</h2>
          <section className="card">
            <table className="meta-table" style={{ margin: 0 }}>
              <tbody>
                {a.capsules.map((c) => (
                  <tr key={c.id}>
                    <th scope="row" style={{ padding: "12px 18px" }}>
                      <Link href={`/capsule/${c.shortId}`} className="mono">
                        capsule/{c.shortId}…
                      </Link>
                    </th>
                    <td style={{ padding: "12px 0" }}>
                      {c.title}
                      <span className="small muted">
                        {" "}
                        — {c.backend} · {c.shots.toLocaleString()} shots ·{" "}
                        {formatDate(c.created)}{" "}
                      </span>
                      <TrustBadge level={c.trustLevel} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}

      <p className="small muted" style={{ marginTop: 40 }}>
        Embed this artifact:{" "}
        <span className="mono">
          &lt;iframe src=&quot;/embed/{ref}&quot;&gt;
        </span>{" "}
        · <Link href={`/embed/${ref}`}>preview</Link>
      </p>
    </>
  );
}
