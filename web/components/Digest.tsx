// Truncated content-address with a copy button — full hashes wrap across
// three lines on mobile and help nobody by being read.

import CopyButton from "./CopyButton";

export default function Digest({ value }: { value: string }) {
  const hex = value.replace(/^sha256:/, "");
  const short =
    hex.length > 20 ? `sha256:${hex.slice(0, 8)}…${hex.slice(-6)}` : value;
  return (
    <span className="digest">
      <span className="mono" title={value}>
        {short}
      </span>
      <CopyButton text={value} variant="surface" />
    </span>
  );
}
