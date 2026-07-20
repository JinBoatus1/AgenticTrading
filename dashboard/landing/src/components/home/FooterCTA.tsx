import { Button } from "@/components/ui/button";

const DISCORD_URL = "https://discord.gg/9HnQ6XDG98";

export function FooterCTA() {
  return (
    <footer className="py-24 relative overflow-hidden text-center border-t border-border">
      <div className="absolute inset-0 bg-grid-pattern opacity-10 [mask-image:radial-gradient(ellipse_at_center,black,transparent_70%)]" />
      <div className="container mx-auto px-6 relative z-10">
        <p className="text-sm font-mono uppercase tracking-widest text-muted-foreground mb-4">
          Talk → Test → Race
        </p>
        <h2 className="text-4xl md:text-5xl font-bold tracking-tighter mb-6">Ready to run your first idea?</h2>
        <p className="text-xl text-muted-foreground mb-10 max-w-xl mx-auto">
          Start on Discord. Prove it in a backtest. Climb the board.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <Button size="lg" className="w-full sm:w-auto bg-[#5865F2] hover:bg-[#5865F2]/90 text-white border-transparent text-base h-12 px-8" asChild>
            <a href={DISCORD_URL} target="_blank" rel="noopener noreferrer">Join Discord</a>
          </Button>
          <Button size="lg" variant="secondary" className="w-full sm:w-auto bg-secondary border-secondary-border text-secondary-foreground hover:bg-secondary/80 text-base h-12 px-8" asChild>
            <a href="/app">Open Leaderboard</a>
          </Button>
        </div>

        <div className="mt-24 pt-8 border-t border-border flex flex-col md:flex-row justify-between items-center text-sm text-muted-foreground">
          <div>© 2026 Agentic Trading Lab. All rights reserved.</div>
          <div className="flex gap-6 mt-4 md:mt-0">
            <a href="#" className="hover:text-foreground">Terms</a>
            <a href="#" className="hover:text-foreground">Privacy</a>
            <a href="#" className="hover:text-foreground">Documentation</a>
          </div>
        </div>
      </div>
    </footer>
  );
}
