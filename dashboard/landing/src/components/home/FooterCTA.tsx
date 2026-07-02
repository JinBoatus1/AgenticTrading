import { Button } from "@/components/ui/button";

export function FooterCTA() {
  return (
    <footer className="py-24 relative overflow-hidden text-center border-t border-border">
      <div className="absolute inset-0 bg-grid-pattern opacity-10 [mask-image:radial-gradient(ellipse_at_center,black,transparent_70%)]" />
      <div className="container mx-auto px-6 relative z-10">
        <h2 className="text-4xl md:text-5xl font-bold tracking-tighter mb-6">Ready to deploy your first agent?</h2>
        <p className="text-xl text-muted-foreground mb-10 max-w-xl mx-auto">
          Start building and backtesting for free.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <Button size="lg" className="w-full sm:w-auto bg-primary text-primary-foreground glow-primary hover:bg-primary/90 text-base h-12 px-8" asChild>
            <a href="/app">Get Started</a>
          </Button>
          <Button size="lg" variant="secondary" className="w-full sm:w-auto bg-secondary border-secondary-border text-secondary-foreground hover:bg-secondary/80 text-base h-12 px-8" asChild>
            <a href="https://discord.gg/9HnQ6XDG98" target="_blank" rel="noopener noreferrer">Join Discord Community</a>
          </Button>
        </div>
        
        <div className="mt-24 pt-8 border-t border-border flex flex-col md:flex-row justify-between items-center text-sm text-muted-foreground">
          <div>© 2024 Agentic Trading Lab. All rights reserved.</div>
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