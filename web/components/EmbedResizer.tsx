"use client";

// Inside an iframe, report our content height to the parent page so blogs
// and course pages can size the embed without scrollbars:
//   window.addEventListener("message", (e) => {
//     if (e.data?.type === "qv:embed-height") iframe.style.height = e.data.height + "px";
//   });

import { useEffect } from "react";

export default function EmbedResizer() {
  useEffect(() => {
    if (window.parent === window) return;
    const post = () =>
      window.parent.postMessage(
        { type: "qv:embed-height", height: document.documentElement.scrollHeight },
        "*",
      );
    post();
    const ro = new ResizeObserver(post);
    ro.observe(document.body);
    return () => ro.disconnect();
  }, []);
  return null;
}
