/** Render a radian value as a tidy multiple of π where possible. */
export function formatRadians(x: number): string {
  if (x === 0) return "0";
  const sign = x < 0 ? "−" : "";
  const a = Math.abs(x);
  for (const d of [1, 2, 3, 4, 6, 8, 16, 32]) {
    const k = (a * d) / Math.PI;
    if (Math.abs(k - Math.round(k)) < 1e-9 && Math.round(k) !== 0) {
      const n = Math.round(k);
      const num = n === 1 ? "π" : `${n}π`;
      return sign + (d === 1 ? num : `${num}/${d}`);
    }
  }
  return sign + a.toFixed(2);
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function shortDigest(id: string): string {
  return id.replace(/^sha256:/, "").slice(0, 6);
}
