import { MarketingNav } from "@/components/marketing/nav";
import LandingPage from "@/components/marketing/landing-page";

export default function MarketingHomePage() {
  return (
    <>
      <MarketingNav />
      <LandingPage />
      <footer className="border-t border-border py-8 text-center text-sm text-text-muted">
        <p>Tool Hub — Revenue Intelligence Engine</p>
        <p className="mt-2">
          <a href="/methodology" className="hover:text-text-primary">Methodology</a>
          {" · "}
          <a href="/login" className="hover:text-text-primary">Sign in</a>
        </p>
      </footer>
    </>
  );
}
