import SiteHeader, { SiteFooter } from "@/components/SiteHeader";

export default function SiteLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <SiteHeader />
      <main className="container page">{children}</main>
      <SiteFooter />
    </>
  );
}
