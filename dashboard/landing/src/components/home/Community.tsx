import { Medal } from "lucide-react";
import { Button } from "@/components/ui/button";

const leaderboard = [
  { rank: 1, user: "QuantKing", agent: "VolBreakout_v3", return: "+142.5%" },
  { rank: 2, user: "AlgoTrader99", agent: "MeanRev_TSLA", return: "+118.2%" },
  { rank: 3, user: "DeepAlpha", agent: "Sentiment_Arb", return: "+94.1%" },
  { rank: 4, user: "RiskManager", agent: "Pairs_ETH_BTC", return: "+87.0%" },
];

export function Community() {
  return (
    <section id="community" className="py-24 bg-muted/20 border-y border-border">
      <div className="container mx-auto px-6">
        <div className="grid lg:grid-cols-2 gap-16 items-center">
          <div>
            <h2 className="text-3xl md:text-4xl font-bold mb-4">Compete in Seasonal Labs</h2>
            <p className="text-muted-foreground mb-8 text-lg">
              Join developers and traders. Deploy your agents in seasonal paper trading competitions and climb the leaderboard.
            </p>
            <Button size="lg" variant="secondary" className="w-full sm:w-auto bg-[#5865F2] hover:bg-[#5865F2]/90 text-white border-transparent" asChild>
              <a href="https://discord.gg/9HnQ6XDG98" target="_blank" rel="noopener noreferrer">Join Discord Community</a>
            </Button>
          </div>

          <div className="bg-card border border-card-border rounded-xl shadow-xl p-6">
            <div className="flex items-center justify-between mb-6 border-b border-border pb-4">
              <h3 className="text-xl font-bold flex items-center gap-2">
                <Medal className="w-5 h-5 text-primary" />
                Season 4 Leaderboard
              </h3>
              <span className="text-xs font-mono text-positive bg-positive/10 px-2 py-1 rounded">LIVE</span>
            </div>
            
            <div className="space-y-2">
              <div className="grid grid-cols-12 text-xs font-mono text-muted-foreground pb-2 px-2">
                <div className="col-span-2">RANK</div>
                <div className="col-span-4">USER</div>
                <div className="col-span-4">AGENT</div>
                <div className="col-span-2 text-right">RETURN</div>
              </div>
              {leaderboard.map((item) => (
                <div key={item.rank} className="grid grid-cols-12 items-center p-3 bg-background border border-border rounded-lg hover:border-primary/50 transition-colors">
                  <div className="col-span-2 font-mono font-bold text-muted-foreground">
                    #{item.rank}
                  </div>
                  <div className="col-span-4 font-medium text-foreground">
                    {item.user}
                  </div>
                  <div className="col-span-4 text-sm text-muted-foreground truncate pr-4">
                    {item.agent}
                  </div>
                  <div className="col-span-2 text-right font-mono font-bold text-positive">
                    {item.return}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}