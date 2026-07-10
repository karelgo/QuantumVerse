import Link from "next/link";

export default function NotFound() {
  return (
    <div className="desk">
      <p className="kicker">404</p>
      <h1>No such artifact.</h1>
      <p className="sub">
        Nothing lives at this address. It may have been renamed — content
        addresses, unlike names, never break.
      </p>
      <p>
        <Link href="/search">Explore the registry →</Link>
      </p>
    </div>
  );
}
