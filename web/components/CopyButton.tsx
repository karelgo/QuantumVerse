"use client";

import { useState } from "react";

export default function CopyButton({
  text,
  variant = "code",
}: {
  text: string;
  variant?: "code" | "surface";
}) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className={`copy-btn${variant === "surface" ? " on-surface" : ""}${copied ? " copied" : ""}`}
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1600);
      }}
      aria-label={copied ? "Copied" : "Copy to clipboard"}
    >
      {copied ? "copied" : "copy"}
    </button>
  );
}
