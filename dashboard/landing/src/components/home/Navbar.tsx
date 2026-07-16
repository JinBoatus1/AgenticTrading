import { Link } from "wouter";
import atlLogo from "@assets/atltransparent.png";

const NAV_LINKS = [
  { href: "#agents", label: "Agents" },
  { href: "#backtesting", label: "Backtesting" },
  { href: "#community", label: "Community" },
] as const;

/** Same 3-column chrome as dashboard `.header` so the brand sits on the viewport center. */
export function Navbar() {
  return (
    <nav className="landing-header fixed top-0 left-0 right-0 z-50 border-b border-border bg-background/80 backdrop-blur-md">
      <div className="hidden md:flex items-center gap-3 text-[15px] font-semibold text-muted-foreground min-w-0">
        {NAV_LINKS.map((link) => (
          <a key={link.href} href={link.href} className="hover:text-foreground transition-colors whitespace-nowrap">
            {link.label}
          </a>
        ))}
      </div>
      <Link href="/" className="brand-lockup">
        <div className="brand-logo">
          <img src={atlLogo} alt="" />
        </div>
        <span className="brand-title">Agentic Trading Lab</span>
      </Link>
      <div className="flex items-center justify-end min-w-0">
        <a
          href="/app?view=home"
          className="inline-flex items-center justify-center rounded-md text-[15px] font-semibold h-10 px-5 bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          Get Started
        </a>
      </div>
    </nav>
  );
}
