import { Link } from "wouter";

export default function Navbar() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-40 border-b border-border/50 bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
        <div className="flex items-center gap-8">
          <Link href="/" className="group flex items-center gap-2">
            <div className="h-4 w-4 bg-primary group-hover:shadow-[0_0_10px_rgba(0,255,102,0.8)] transition-shadow"></div>
            <span className="font-mono text-sm font-bold tracking-wider text-primary">
              AGENTIC<span className="text-foreground">LAB</span>
            </span>
          </Link>

          <div className="hidden md:flex items-center gap-6 font-mono text-xs text-muted-foreground">
            <a href="#agents" className="hover:text-primary transition-colors">AGENTS</a>
            <a href="#backtesting" className="hover:text-primary transition-colors">BACKTESTING</a>
            <a href="#infrastructure" className="hover:text-primary transition-colors">INFRASTRUCTURE</a>
            <a href="#risk" className="hover:text-primary transition-colors">RISK</a>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="hidden sm:flex items-center gap-2 font-mono text-xs">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-primary"></span>
            </span>
            <span className="text-primary">SYSTEM ONLINE</span>
          </div>
          <button className="border border-primary bg-primary/10 px-4 py-2 font-mono text-xs font-bold text-primary transition-colors hover:bg-primary hover:text-primary-foreground">
            INIT_SESSION
          </button>
        </div>
      </div>
    </nav>
  );
}
