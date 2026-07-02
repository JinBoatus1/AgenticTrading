import { Link } from "wouter";
import atlLogo from "@assets/atl-logo.png";
import { Button } from "@/components/ui/button";

const NAV_LINKS = [
  { href: "#agents", label: "Agents" },
  { href: "#backtesting", label: "Backtesting" },
  { href: "#community", label: "Community" },
] as const;

export function Navbar() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-border bg-background/80 backdrop-blur-md">
      <div className="container mx-auto px-6 h-16 grid grid-cols-[1fr_auto_1fr] items-center">
        <div className="hidden md:flex items-center gap-6 text-sm text-muted-foreground">
          {NAV_LINKS.map((link) => (
            <a key={link.href} href={link.href} className="hover:text-foreground transition-colors">
              {link.label}
            </a>
          ))}
        </div>
        <Link href="/" className="col-start-2 flex items-center justify-center gap-2.5">
          <img src={atlLogo} alt="ATL Logo" className="w-8 h-8 object-contain" />
          <span className="text-lg font-bold tracking-tight text-foreground">Agentic Trading Lab</span>
        </Link>
        <div className="col-start-3 flex items-center justify-end gap-4">
          <Button className="bg-primary text-primary-foreground glow-primary hover:bg-primary/90 transition-all" asChild>
            <a href="/app">Open Dashboard</a>
          </Button>
        </div>
      </div>
    </nav>
  );
}
