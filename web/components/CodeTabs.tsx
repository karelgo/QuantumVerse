"use client";

import { useState } from "react";
import CopyButton from "./CopyButton";

export interface CodeTab {
  label: string;
  code: string;
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
