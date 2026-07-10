"use client";

// Raw vs mitigated counts on capsule pages. The mitigated view overlays the
// raw distribution as outline bars, so the correction is visible rather than
// a sentence pointing at execution.json.

import { useState } from "react";
import Histogram from "./Histogram";

export default function ExecutionCounts({
  countsRaw,
  countsMitigated,
  shots,
}: {
  countsRaw: Record<string, number>;
  countsMitigated?: Record<string, number>;
  shots: number;
}) {
  const [view, setView] = useState<"raw" | "mitigated">("raw");

  if (!countsMitigated) return <Histogram counts={countsRaw} shots={shots} />;

  const mitigatedShots =
    Object.values(countsMitigated).reduce((a, b) => a + b, 0) || shots;

  return (
    <div>
      <div className="result-tabs" role="tablist" style={{ marginBottom: 14 }}>
        <button
          className="tab"
          role="tab"
          aria-selected={view === "raw"}
          onClick={() => setView("raw")}
        >
          Raw
        </button>
        <button
          className="tab"
          role="tab"
          aria-selected={view === "mitigated"}
          onClick={() => setView("mitigated")}
        >
          Mitigated
        </button>
      </div>
      {view === "raw" ? (
        <Histogram counts={countsRaw} shots={shots} />
      ) : (
        <Histogram
          counts={countsMitigated}
          shots={mitigatedShots}
          reference={countsRaw}
          referenceLabel="raw counts"
          label="mitigated"
        />
      )}
    </div>
  );
}
