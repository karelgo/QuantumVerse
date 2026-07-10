"use client";

// Copyable iframe snippet with the absolute URL, built client-side so the
// page itself stays statically cacheable.

import Link from "next/link";
import { useEffect, useState } from "react";
import CopyButton from "./CopyButton";

export default function EmbedSnippet({ refPath }: { refPath: string }) {
  const [origin, setOrigin] = useState<string | null>(null);
  useEffect(() => setOrigin(window.location.origin), []);

  const snippet = `<iframe src="${origin ?? ""}/embed/${refPath}" width="100%" height="420" style="border:1px solid #d9dce6;border-radius:12px" title="${refPath} — QuantumVerse" loading="lazy"></iframe>`;

  return (
    <section className="embed-snippet card panel">
      <p className="small" style={{ marginTop: 0 }}>
        <b>Embed this artifact</b> — a chromeless, runnable widget for papers,
        blogs, and courses. It posts <span className="mono">qv:embed-height</span>{" "}
        messages so the frame can auto-size.{" "}
        <Link href={`/embed/${refPath}`}>Preview →</Link>
      </p>
      <div className="embed-code">
        <code className="mono small">{origin ? snippet : "…"}</code>
        {origin && <CopyButton text={snippet} variant="surface" />}
      </div>
    </section>
  );
}
