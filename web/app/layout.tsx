import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_SITE_URL ??
      "https://quantumverse-web-karelgo-dev.apps.rm1.0a51.p1.openshiftapps.com",
  ),
  title: {
    default: "QuantumVerse — the home for quantum artifacts",
    template: "%s · QuantumVerse",
  },
  description:
    "Publish, discover, run, and verify quantum circuits, trained parameters, and experiment capsules.",
};

// Apply a saved manual theme before first paint (no flash); otherwise the
// prefers-color-scheme tokens apply on their own.
const themeScript = `try{var t=localStorage.getItem("qv-theme");if(t)document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
