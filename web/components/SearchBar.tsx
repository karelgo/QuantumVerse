"use client";

// Server-rendered results do the real work (/search); this adds the "/"
// keyboard shortcut on pages that show a search box.

import { useEffect, useRef } from "react";

export default function SearchBar({
  defaultValue = "",
  autoFocus = false,
}: {
  defaultValue?: string;
  autoFocus?: boolean;
}) {
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (
        e.key === "/" &&
        !(e.target instanceof HTMLInputElement) &&
        !(e.target instanceof HTMLTextAreaElement)
      ) {
        e.preventDefault();
        ref.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <form action="/search" role="search">
      <input
        ref={ref}
        className="search-input"
        type="search"
        name="q"
        placeholder="Search circuits, parameters, instances…  ( / )"
        defaultValue={defaultValue}
        autoFocus={autoFocus}
        aria-label="Search artifacts"
      />
    </form>
  );
}
