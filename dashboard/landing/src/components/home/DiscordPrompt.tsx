import { Button } from "@/components/ui/button";
import { MessageSquare, Hash, Bot } from "lucide-react";

export function DiscordPrompt() {
  return (
    <section id="discord-prompt" className="py-24 bg-muted/20 border-y border-border">
      <div className="container mx-auto px-6">
        <div className="grid lg:grid-cols-2 gap-16 items-center">
          <div>
            <h2 className="text-3xl md:text-4xl font-bold mb-4">Prompt Your Agent Through Discord</h2>
            <p className="text-muted-foreground mb-6 text-lg leading-relaxed">
              Talk to your trading agent where your team already collaborates. Send strategy ideas, ask for backtests,
              review decisions, and iterate in plain language — no dashboard required.
            </p>
            <ul className="space-y-3 mb-8 text-sm text-muted-foreground">
              <li className="flex items-start gap-3">
                <MessageSquare className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                <span>Describe setups, risk rules, and entry/exit logic conversationally</span>
              </li>
              <li className="flex items-start gap-3">
                <Bot className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                <span>Your agent translates prompts into executable trading logic</span>
              </li>
              <li className="flex items-start gap-3">
                <Hash className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                <span>Stay in sync with your lab community on Discord</span>
              </li>
            </ul>
            <Button size="lg" className="bg-[#5865F2] hover:bg-[#5865F2]/90 text-white border-transparent" asChild>
              <a href="https://discord.gg/9HnQ6XDG98" target="_blank" rel="noopener noreferrer">Join Discord Community</a>
            </Button>
          </div>

          <div className="bg-card border border-card-border rounded-xl shadow-2xl overflow-hidden">
            <div className="h-10 bg-muted/50 border-b border-border flex items-center px-4 gap-2">
              <div className="w-3 h-3 rounded-full bg-destructive/80" />
              <div className="w-3 h-3 rounded-full bg-secondary-border" />
              <div className="w-3 h-3 rounded-full bg-positive/80" />
              <span className="ml-3 text-xs font-mono text-muted-foreground">#agent-trading-lab</span>
            </div>
            <div className="p-5 space-y-4 font-mono text-sm">
              <div className="flex gap-3">
                <div className="w-8 h-8 rounded-full bg-primary/20 text-primary flex items-center justify-center shrink-0 text-xs font-bold">You</div>
                <div className="bg-muted p-3 rounded-r-lg rounded-bl-lg text-foreground max-w-[85%]">
                  Backtest a momentum strategy on NVDA. Buy when RSI crosses above 55, sell below 45.
                </div>
              </div>
              <div className="flex gap-3 flex-row-reverse">
                <div className="w-8 h-8 rounded-full bg-secondary-border flex items-center justify-center shrink-0 text-xs">ATL</div>
                <div className="bg-card border border-card-border p-3 rounded-l-lg rounded-br-lg text-muted-foreground max-w-[85%]">
                  Running backtest on NVDA (1H, YTD)…<br />
                  <span className="text-positive font-semibold">Done:</span> +14.2% return, Sharpe 1.84
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
