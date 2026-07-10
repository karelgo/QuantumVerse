import { ImageResponse } from "next/og";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "QuantumVerse — the home for quantum artifacts";

const brass = "#e0ac45";
const ink = "#e8eaf3";
const muted = "#99a2bc";
const wire = "#4c5677";

export default function Image() {
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
          padding: 80,
        }}
      >
        <div
          style={{
            display: "flex",
            fontSize: 26,
            color: brass,
            letterSpacing: 6,
          }}
        >
          CIRCUITS · PARAMETERS · CAPSULES
        </div>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", fontSize: 84, fontWeight: 700, color: ink }}>
            The home for
          </div>
          <div style={{ display: "flex", fontSize: 84, fontWeight: 700, color: ink }}>
            quantum artifacts.
          </div>
          <div style={{ display: "flex", fontSize: 32, color: muted, marginTop: 24 }}>
            Shareable, runnable, verifiable quantum work.
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <div style={{ display: "flex", fontSize: 34, fontWeight: 700, color: ink }}>
            QuantumVerse
          </div>
          <div style={{ display: "flex", flexGrow: 1, height: 3, background: wire }} />
          <div
            style={{
              display: "flex",
              width: 22,
              height: 22,
              borderRadius: 22,
              border: `4px solid ${brass}`,
            }}
          />
          <div style={{ display: "flex", width: 80, height: 3, background: wire }} />
          <div
            style={{
              display: "flex",
              width: 14,
              height: 14,
              borderRadius: 14,
              background: brass,
            }}
          />
        </div>
      </div>
    ),
    size,
  );
}
