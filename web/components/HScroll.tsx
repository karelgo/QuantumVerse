"use client";

// Horizontal scroll container with edge fades that signal off-screen content
// (wide circuits). Server-rendered children pass straight through.

import { useEffect, useRef, useState } from "react";

export default function HScroll({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [fade, setFade] = useState({ l: false, r: false });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () =>
      setFade({
        l: el.scrollLeft > 4,
        r: el.scrollLeft + el.clientWidth < el.scrollWidth - 4,
      });
    update();
    el.addEventListener("scroll", update, { passive: true });
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => {
      el.removeEventListener("scroll", update);
      ro.disconnect();
    };
  }, []);

  return (
    <div className="hscroll" data-l={fade.l} data-r={fade.r}>
      <div ref={ref} className="circuit-scroll">
        {children}
      </div>
    </div>
  );
}
