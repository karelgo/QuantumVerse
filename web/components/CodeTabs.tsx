"use client";

import { useState } from "react";

export interface CodeTab {
  label: string;
  code: string;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className={`copy-btn${copied ? " copied" : ""}`}
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1600);
      }}
    >
      {copied ? "copied" : "copy"}
    </button>
  );
}

export default function CodeTabs({ tabs }: { tabs: CodeTab[] }) {
  const [active, setActive] = useState(0);
  return (
    <div className="code-tabs">
      <div className="tab-row" role="tablist">
        {tabs.map((t, i) => (
          <button
            key={t.label}
            className="tab"
            role="tab"
            aria-selected={i === active}
            onClick={() => setActive(i)}
          >
            {t.label}
          </button>
        ))}
        <CopyButton text={tabs[active].code} />
      </div>
      <pre className="codeblock" tabIndex={0}>
        {tabs[active].code}
      </pre>
    </div>
  );
}
