import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import CircuitSVG from "@/components/CircuitSVG";
import CodeTabs from "@/components/CodeTabs";
import Digest from "@/components/Digest";
import ExecutionCounts from "@/components/ExecutionCounts";
import RunPanel from "@/components/RunPanel";
import TrustBadge from "@/components/TrustBadge";
import { getCapsule } from "@/lib/api";
import { parseQasm } from "@/lib/qasm";
import { computeResources } from "@/lib/circuit";
import { formatDate } from "@/lib/format";

// Capsules are immutable (any edit is a new capsule) — cache aggressively.
export const revalidate = 3600;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ digest: string }>;
}): Promise<Metadata> {
  const { digest } = await params;
  const c = await getCapsule(digest);
  return { title: c ? `capsule/${c.shortId}` : "Not found" };
}

function bibtex(c: NonNullable<Awaited<ReturnType<typeof getCapsule>>>): string {
  const year = new Date(c.created).getUTCFullYear();
  const lines = [
    `@misc{qv_${c.shortId},`,
    `  title        = {${c.title}},`,
    `  author       = {${c.manifest.authors.map((a) => a.name).join(" and ")}},`,
    `  year         = {${year}},`,
  ];
  if (c.manifest.doi) lines.push(`  doi          = {${c.manifest.doi}},`);
  lines.push(
    `  howpublished = {QuantumVerse capsule/${c.shortId}},`,
    `  note         = {${["unsigned", "author-signed", "provider-verified"][c.trustLevel]} execution record},`,
    `}`,
  );
  return lines.join("\n");
}

export default async function CapsulePage({
  params,
}: {
  params: Promise<{ digest: string }>;
}) {
  const { digest } = await params;
  const c = await getCapsule(digest);
  if (!c) notFound();

  const numQubits = computeResources(parseQasm(c.qasm)).qubits;

  return (
    <>
      <p className="crumbs">
        <span>capsule</span>
        <span className="sep">/</span>
        <span>{c.shortId}…</span>
      </p>
      <div className="artifact-title">
        <h1>{c.title}</h1>
        <TrustBadge level={c.trustLevel} verbose />
      </div>
      <p className="muted">
        {c.manifest.authors.map((a) =>
          a.profile ? (
            <Link key={a.name} href={`/${a.profile.replace(/^qv:users\//, "")}`}>
              {a.name}
            </Link>
          ) : (
            <span key={a.name}>{a.name}</span>
          ),
        )}{" "}
        · {formatDate(c.created)} · {c.manifest.license}
        {c.manifest.doi && (
          <>
            {" · "}
            <span className="mono">doi:{c.manifest.doi}</span>
          </>
        )}
      </p>

      <h2>Integrity</h2>
      <section className="card panel">
        <p className={c.integrity.idVerified ? "digest-ok" : "digest-bad"}>
          {c.integrity.idVerified
            ? "✓ Capsule ID recomputed from canonical manifest — matches."
            : "✗ Capsule ID does not match its contents — treat as tampered."}
        </p>
        {c.integrity.signatureValid !== null && (
          <p className={c.integrity.signatureValid ? "digest-ok" : "digest-bad"}>
            {c.integrity.signatureValid
              ? `✓ Ed25519 author signature verifies against ${c.integrity.signer}'s published key.`
              : `✗ Author signature does not verify against ${c.integrity.signer}'s published key.`}
          </p>
        )}
        <table className="meta-table">
          <tbody>
            <tr>
              <th scope="row">Capsule ID</th>
              <td>
                <Digest value={c.id} />
              </td>
            </tr>
            {c.integrity.files.map((f) => (
              <tr key={f.name}>
                <th scope="row" className="mono">
                  {f.name}
                </th>
                <td>
                  <span className={f.verified ? "digest-ok" : "digest-bad"}>
                    {f.verified ? "✓" : "✗"}
                  </span>{" "}
                  <Digest value={f.digest} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <h2>Device</h2>
      <section className="card panel">
        <table className="meta-table">
          <tbody>
            <tr>
              <th scope="row">Backend</th>
              <td>
                {c.device.backend.provider}/{c.device.backend.name} · v
                {c.device.backend.version}
              </td>
            </tr>
            <tr>
              <th scope="row">Snapshot</th>
              <td>{formatDate(c.device.captured)}</td>
            </tr>
            {c.device.simulator ? (
              <tr>
                <th scope="row">Simulator</th>
                <td className="mono">
                  {c.device.simulator.engine} · {c.device.simulator.method}
                  {c.device.simulator.noise_model
                    ? ` · noise: ${JSON.stringify(c.device.simulator.noise_model)}`
                    : " · noiseless"}
                </td>
              </tr>
            ) : (
              <tr>
                <th scope="row">Topology</th>
                <td>{c.device.topology?.num_qubits} physical qubits</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      <h2>Circuit</h2>
      <div className="card">
        <CircuitSVG qasm={c.qasm} />
      </div>

      <h2>Execution</h2>
      <section className="card panel">
        <p className="small muted" style={{ marginTop: 0 }}>
          {c.execution.shots.toLocaleString()} shots · job{" "}
          <span className="mono">{c.execution.job_ids.join(", ")}</span> ·
          submitted {formatDate(c.execution.submitted)}
        </p>
        <ExecutionCounts
          countsRaw={c.execution.counts_raw}
          countsMitigated={c.execution.counts_mitigated}
          shots={c.execution.shots}
        />
        {c.mitigation && (
          <p className="small muted" style={{ marginBottom: 0 }}>
            Mitigation pipeline:{" "}
            {c.mitigation.pipeline
              .map((s) => `${s.step} (${s.method})`)
              .join(" → ")}
            .
          </p>
        )}
      </section>

      <h2>Replay</h2>
      <section className="card panel">
        <p className="small muted" style={{ marginTop: 0 }}>
          L1 replay per RFC-0001: re-simulate <span className="mono">circuit.qasm</span>{" "}
          and compare against the recorded raw counts. This runs noiseless (the
          device noise model isn&rsquo;t applied yet), so expect distance ≈ the
          device&rsquo;s noise floor.
        </p>
        <RunPanel
          qasm={c.qasm}
          numQubits={numQubits}
          reference={{
            counts: c.execution.counts_raw,
            label: `the recorded counts from ${c.backend}`,
          }}
        />
      </section>

      <h2>Cite</h2>
      <CodeTabs tabs={[{ label: "BibTeX", code: bibtex(c) }]} />

      {Object.keys(c.manifest.artifacts ?? {}).length > 0 && (
        <p className="small muted" style={{ marginTop: 28 }}>
          Instantiates:{" "}
          {Object.entries(c.manifest.artifacts).map(([role, uri], i) => {
            const ref = uri.replace(/^qv:/, "").split("@")[0];
            return (
              <span key={role}>
                {i > 0 && " · "}
                <Link href={`/${ref}`} className="mono">
                  {uri}
                </Link>{" "}
                ({role})
              </span>
            );
          })}
        </p>
      )}
    </>
  );
}
