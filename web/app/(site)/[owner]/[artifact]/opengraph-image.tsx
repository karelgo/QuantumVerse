import { ImageResponse } from "next/og";
import { getArtifact } from "@/lib/registry";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "QuantumVerse artifact card";

const brass = "#e0ac45";
const ink = "#e8eaf3";
const muted = "#99a2bc";
const wire = "#4c5677";
const line = "#242b45";

function Chip({ children }: { children: string }) {
  return (
    <div
      style={{
        display: "flex",
        fontSize: 24,
        color: muted,
        border: `2px solid ${line}`,
        borderRadius: 10,
        padding: "8px 18px",
        background: "#121629",
      }}
    >
      {children}
    </div>
  );
}

// The bundled OG font lacks some technical glyphs — substitute rather than tofu.
function sanitize(s: string): string {
  return s
    .replace(/⟨/g, "(")
    .replace(/⟩/g, ")")
    .replace(/≈/g, "~")
    .replace(/₀/g, "0")
    .replace(/₁/g, "1")
    .replace(/₂/g, "2")
    .replace(/ᵏ/g, "k")
    .replace(/π/g, "pi");
}

export default async function Image({
  params,
}: {
  params: Promise<{ owner: string; artifact: string }>;
}) {
  const { owner, artifact } = await params;
  const name = decodeURIComponent(artifact).split("@")[0];
  const a = getArtifact(owner, name);

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: "#0b0e1a",
          padding: 72,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
          <div style={{ display: "flex", fontSize: 24, color: brass, letterSpacing: 5 }}>
            QUANTUMVERSE
          </div>
          {a && (
            <div
              style={{
                display: "flex",
                fontSize: 22,
                color: brass,
                border: `2px solid ${brass}`,
                borderRadius: 999,
                padding: "4px 18px",
              }}
            >
              {a.kind}
            </div>
          )}
        </div>

        <div style={{ display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", fontSize: 40, color: muted }}>{owner} /</div>
          <div
            style={{
              display: "flex",
              fontSize: 88,
              fontWeight: 700,
              color: ink,
              marginTop: 4,
            }}
          >
            {name}
          </div>
          {a && (
            <div
              style={{
                display: "flex",
                fontSize: 30,
                color: muted,
                marginTop: 20,
                lineHeight: 1.45,
                maxWidth: 1000,
              }}
            >
              {sanitize(
                a.description.length > 140
                  ? a.description.slice(0, 137) + "…"
                  : a.description,
              )}
            </div>
          )}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          {a ? (
            <>
              <Chip>{`${a.resources.qubits} qubits`}</Chip>
              <Chip>{`depth ${a.resources.depth}`}</Chip>
              <Chip>{`${a.resources.gateCount} gates`}</Chip>
              <Chip>{`T-count ${a.resources.tCount}`}</Chip>
            </>
          ) : (
            <Chip>artifact</Chip>
          )}
          <div style={{ display: "flex", flexGrow: 1, height: 3, background: wire }} />
          <div
            style={{
              display: "flex",
              width: 20,
              height: 20,
              borderRadius: 20,
              border: `4px solid ${brass}`,
            }}
          />
          <div style={{ display: "flex", width: 60, height: 3, background: wire }} />
          <div
            style={{
              display: "flex",
              width: 13,
              height: 13,
              borderRadius: 13,
              background: brass,
            }}
          />
        </div>
      </div>
    ),
    size,
  );
}
