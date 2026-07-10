import Link from "next/link";
import ThemeToggle from "./ThemeToggle";

const REPO = "https://github.com/karelgo/QuantumVerse";

export default function SiteHeader() {
  return (
    <header className="site-header">
      <div className="container">
        <Link href="/" className="wordmark">
          QuantumVerse <span className="tag">beta</span>
        </Link>
        <nav className="site-nav" aria-label="Site">
          <Link href="/search">Explore</Link>
          <a href={`${REPO}/blob/main/rfcs/rfc-0001-experiment-capsule.md`}>
            Spec
          </a>
          <a href={REPO}>GitHub</a>
          <ThemeToggle />
        </nav>
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="container">
        <span>QuantumVerse — open core, open spec, open data.</span>
        <a href={`${REPO}/blob/main/VISION.md`}>Vision</a>
        <a href={`${REPO}/blob/main/rfcs/rfc-0001-experiment-capsule.md`}>
          RFC-0001
        </a>
        <a href="https://karelgo.github.io/QuantumVerse/">Pitch site</a>
        <a href={REPO}>Apache-2.0</a>
      </div>
    </footer>
  );
}
