import { Link } from "wouter";
import atlLogo from "@assets/atl-logo.png";
import { Button } from "@/components/ui/button";

export function Navbar() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-border bg-background/80 backdrop-blur-md">
      <div className="container mx-auto px-6 h-16 flex items-center justify-between">
        <div className="flex items-center gap-8">
          <Link href="/" className="flex items-center gap-2">
            <img src={atlLogo} alt="ATL Logo" className="w-6 h-6 object-contain" />
            <span className="font-bold tracking-tight text-foreground">Agentic Trading Lab</span>
          </Link>
          <div className="hidden md:flex items-center gap-6 text-sm text-muted-foreground">
            <a href="#agents" className="hover:text-foreground transition-colors">Agents</a>
            <a href="#backtesting" className="hover:text-foreground transition-colors">Backtesting</a>
            <a href="#community" className="hover:text-foreground transition-colors">Community</a>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <Button className="bg-primary text-primary-foreground glow-primary hover:bg-primary/90 transition-all" asChild>
            <a href="/app">Open Dashboard</a>
          </Button>
        </div>
      </div>
    </nav>
  );
}
