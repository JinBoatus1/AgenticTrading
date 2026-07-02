import { motion } from "framer-motion";
import { ArrowUpRight, ArrowDownRight, Clock } from "lucide-react";
import { useEffect, useState } from "react";

const typeStyles = {
  positive: "w-10 h-10 rounded-full flex items-center justify-center bg-emerald-500/10 text-emerald-400",
  destructive: "w-10 h-10 rounded-full flex items-center justify-center bg-red-500/10 text-red-400",
  muted: "w-10 h-10 rounded-full flex items-center justify-center bg-slate-500/10 text-slate-400",
};

const events = [
  { action: "BUY", symbol: "NVDA", price: "$921.40", reason: "MACD divergence + volume spike", time: "Just now", type: "positive" },
  { action: "SELL", symbol: "TSLA", price: "$182.10", reason: "Resistance hit, RSI > 80", time: "2m ago", type: "destructive" },
  { action: "BUY", symbol: "BTC", price: "$67,240.00", reason: "Breakout confirmed on 1H", time: "5m ago", type: "positive" },
  { action: "HOLD", symbol: "AAPL", price: "$171.20", reason: "Awaiting earnings data", time: "12m ago", type: "muted" },
  { action: "SELL", symbol: "AMD", price: "$840.50", reason: "Trailing stop activated", time: "15m ago", type: "destructive" },
];

export function ActivityFeed() {
  const [items, setItems] = useState(events.slice(0, 4));

  useEffect(() => {
    const interval = setInterval(() => {
      setItems(prev => {
        const next = [...prev];
        const last = next.pop()!;
        next.unshift(last);
        return next;
      });
    }, 4000);
    return () => clearInterval(interval);
  }, []);

  return (
    <section className="py-24 bg-muted/20 border-y border-border relative overflow-hidden">
      <div className="container mx-auto px-6">
        <div className="flex flex-col lg:flex-row gap-12 items-center">
          <div className="lg:w-1/3">
            <h2 className="text-3xl md:text-4xl font-bold mb-4">Observe Agents Live</h2>
            <p className="text-muted-foreground mb-8">
              Watch autonomous agents make real-time decisions. Every trade comes with transparent reasoning, so you never have to guess why a position was taken.
            </p>
          </div>
          
          <div className="lg:w-2/3 w-full">
            <div className="bg-card border border-card-border rounded-xl shadow-xl p-6 flex flex-col gap-4 relative">
              <div className="absolute top-0 right-0 p-4">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-positive animate-pulse" />
                  <span className="text-xs font-mono text-muted-foreground uppercase tracking-widest">Live Network</span>
                </div>
              </div>
              
              <div className="flex flex-col gap-3 mt-4">
                {items.map((item, i) => (
                  <motion.div 
                    key={`${item.symbol}-${item.time}-${i}`}
                    layout
                    initial={{ opacity: 0, y: -20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.9 }}
                    className="p-4 border border-card-border rounded-lg bg-background flex items-center justify-between gap-4"
                  >
                    <div className="flex items-center gap-4">
                      <div className={typeStyles[item.type as keyof typeof typeStyles] ?? typeStyles.muted}>
                        {item.action === "BUY" ? <ArrowUpRight className="w-5 h-5" /> : 
                         item.action === "SELL" ? <ArrowDownRight className="w-5 h-5" /> : 
                         <Clock className="w-5 h-5 text-muted-foreground" />}
                      </div>
                      <div>
                        <div className="font-bold text-foreground flex items-center gap-2">
                          <span className={item.action === "BUY" ? "text-positive" : item.action === "SELL" ? "text-destructive" : "text-muted-foreground"}>
                            {item.action}
                          </span>
                          {item.symbol} <span className="text-muted-foreground font-normal">at</span> {item.price}
                        </div>
                        <div className="text-xs text-muted-foreground font-mono mt-1">
                          Reasoning: {item.reason}
                        </div>
                      </div>
                    </div>
                    <div className="text-xs text-muted-foreground font-mono whitespace-nowrap hidden sm:block">
                      {item.time}
                    </div>
                  </motion.div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}