import SiteHeader, { SiteFooter } from "@/components/SiteHeader";

export default function SiteLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <SiteHeader />
      <main id="main" className="container page">
        {children}
      </main>
      <SiteFooter />
    </>
  );
}
