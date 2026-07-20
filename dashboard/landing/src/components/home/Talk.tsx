import { Button } from "@/components/ui/button";
import { MessageSquare, Bot, Hash, User } from "lucide-react";
import { STORY_PROMPT, STORY_SPECS } from "./storyline";

const DISCORD_URL = "https://discord.gg/9HnQ6XDG98";

function YouBubble({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-3 flex-row-reverse">
      <div className="w-6 h-6 rounded bg-primary/20 text-primary flex items-center justify-center shrink-0">
        <User className="w-3 h-3" />
      </div>
      <div className="bg-muted p-3 rounded-l-lg rounded-br-lg text-foreground max-w-[85%]">{children}</div>
    </div>
  );
}

function BotBubble({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <div className="w-6 h-6 rounded bg-secondary-border flex items-center justify-center shrink-0">
        <Bot className="w-3 h-3 text-muted-foreground" />
      </div>
      <div className="bg-card border border-card-border p-3 rounded-r-lg rounded-bl-lg text-muted-foreground max-w-[85%] space-y-2">
        {children}
      </div>
    </div>
  );
}

export function Talk() {
  return (
    <section id="talk" className="py-24 bg-muted/20 border-y border-border scroll-mt-24">
      {/* Hero scroll target — do not remove; Hero.tsx still anchors here */}
      <div id="landing-stats" className="h-0 w-0 overflow-hidden" aria-hidden="true" />

      <div className="container mx-auto px-6">
        <div className="grid lg:grid-cols-2 gap-16 items-center">
          <div>
            <p className="text-base md:text-lg font-mono uppercase tracking-widest text-primary mb-3">01 — Talk</p>
            <h2 className="text-3xl md:text-4xl font-bold mb-3">Talk to agents on Discord</h2>
            <p className="text-muted-foreground mb-8 text-lg">
              Describe your trading idea. The bot runs it.
            </p>
            <ol className="space-y-3 mb-8 text-sm text-muted-foreground">
              <li className="flex items-start gap-3">
                <Hash className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                <span><span className="text-foreground font-medium">1</span> Join the server</span>
              </li>
              <li className="flex items-start gap-3">
                <MessageSquare className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                <span><span className="text-foreground font-medium">2</span> Talk to the bot</span>
              </li>
              <li className="flex items-start gap-3">
                <Bot className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                <span><span className="text-foreground font-medium">3</span> Get your backtest result</span>
              </li>
            </ol>
            <Button size="lg" className="bg-[#5865F2] hover:bg-[#5865F2]/90 text-white border-transparent" asChild>
              <a href={DISCORD_URL} target="_blank" rel="noopener noreferrer">Join Discord</a>
            </Button>
          </div>

          <div className="bg-card border border-card-border rounded-xl shadow-2xl overflow-hidden">
            <div className="h-10 bg-muted/50 border-b border-border flex items-center px-4 gap-2">
              <div className="w-3 h-3 rounded-full bg-destructive/80" />
              <div className="w-3 h-3 rounded-full bg-secondary-border" />
              <div className="w-3 h-3 rounded-full bg-positive/80" />
              <span className="ml-3 text-xs font-mono text-muted-foreground">#agent-trading-lab</span>
            </div>
            <div className="p-5 space-y-3 font-mono text-sm max-h-[420px] overflow-y-auto">
              <YouBubble>{STORY_PROMPT}</YouBubble>

              <BotBubble>
                <p className="text-foreground">
                  Got it — when Berkshire files a change, copy those buys and sells?
                </p>
              </BotBubble>

              <YouBubble>Yes. Use the last two years.</YouBubble>

              <BotBubble>
                <p className="text-foreground">Copy-trade rules set · 6 tickers from recent 13Fs.</p>
                <p>Want me to backtest that first?</p>
              </BotBubble>

              <YouBubble>Yeah, run it.</YouBubble>

              <BotBubble>
                <div>Running backtest…</div>
                <div>
                  <span className="text-positive font-semibold">{STORY_SPECS.returnPct}</span>
                  {" · "}
                  Sharpe {STORY_SPECS.sharpe}
                  {" · "}
                  <a href="#test" className="text-primary hover:underline">See full result ↓</a>
                </div>
              </BotBubble>
            </div>
            <p className="px-5 pb-4 text-xs font-mono text-muted-foreground">Demo replay · continues below</p>
          </div>
        </div>
      </div>
    </section>
  );
}
