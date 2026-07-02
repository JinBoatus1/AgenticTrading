import { Button } from "@/components/ui/button";
import { Rocket, LineChart, Shield } from "lucide-react";

export function PaperTradingDeploy() {
  return (
    <section id="paper-trading" className="py-24 relative">
      <div className="container mx-auto px-6">
        <div className="grid lg:grid-cols-2 gap-16 items-center">
          <div className="order-2 lg:order-1 bg-card border border-card-border rounded-xl shadow-2xl p-6 md:p-8">
            <div className="grid grid-cols-2 gap-4 mb-6">
              <div className="p-4 border border-border rounded-lg bg-background">
                <div className="text-xs text-muted-foreground mb-1">Portfolio Value</div>
                <div className="text-2xl font-bold font-mono text-foreground">$128,742</div>
              </div>
              <div className="p-4 border border-border rounded-lg bg-background">
                <div className="text-xs text-muted-foreground mb-1">Day P/L</div>
                <div className="text-2xl font-bold font-mono text-positive">+$2,847</div>
              </div>
              <div className="p-4 border border-border rounded-lg bg-background">
                <div className="text-xs text-muted-foreground mb-1">Open Positions</div>
                <div className="text-2xl font-bold font-mono text-foreground">6</div>
              </div>
              <div className="p-4 border border-border rounded-lg bg-background">
                <div className="text-xs text-muted-foreground mb-1">Agent Status</div>
                <div className="text-2xl font-bold font-mono text-positive">Live</div>
              </div>
            </div>
            <div className="h-2 rounded-full bg-muted overflow-hidden">
              <div className="h-full w-3/4 bg-primary rounded-full" />
            </div>
            <p className="mt-3 text-xs text-muted-foreground font-mono">Paper session active · decisions streaming to dashboard</p>
          </div>

          <div className="order-1 lg:order-2">
            <h2 className="text-3xl md:text-4xl font-bold mb-4">Deploy to Live Paper Trading</h2>
            <p className="text-muted-foreground mb-6 text-lg leading-relaxed">
              Once your agent passes backtests, deploy it to a live paper trading environment. Monitor portfolio value,
              positions, and every decision in real time — without risking capital.
            </p>
            <ul className="space-y-3 mb-8 text-sm text-muted-foreground">
              <li className="flex items-start gap-3">
                <Rocket className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                <span>One-click deploy from backtest to paper trading</span>
              </li>
              <li className="flex items-start gap-3">
                <LineChart className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                <span>Track equity curve, trades, and agent decisions live</span>
              </li>
              <li className="flex items-start gap-3">
                <Shield className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                <span>Validate strategies in realistic market conditions safely</span>
              </li>
            </ul>
            <Button size="lg" className="bg-primary text-primary-foreground glow-primary hover:bg-primary/90" asChild>
              <a href="/app">Open Dashboard</a>
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}
