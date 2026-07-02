import { motion } from "framer-motion";

export default function Backtesting() {
  return (
    <section id="backtesting" className="py-24 border-b border-border relative overflow-hidden bg-background">
      {/* Grid Pattern */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:64px_64px]"></div>

      <div className="container mx-auto px-6 relative z-10">
        <div className="grid lg:grid-cols-2 gap-16 items-center">
          
          <div className="order-2 lg:order-1 font-mono">
            <div className="bg-card border border-border p-1">
              <div className="flex bg-muted/30 border-b border-border p-2 gap-2">
                <div className="w-3 h-3 rounded-full bg-destructive"></div>
                <div className="w-3 h-3 rounded-full bg-secondary"></div>
                <div className="w-3 h-3 rounded-full bg-primary"></div>
              </div>
              <div className="p-4 text-xs md:text-sm overflow-x-auto text-muted-foreground">
                <div className="mb-2"><span className="text-secondary">import</span> <span className="text-foreground">agentic</span></div>
                <div className="mb-2"><span className="text-secondary">import</span> <span className="text-foreground">pandas</span> <span className="text-secondary">as</span> <span className="text-foreground">pd</span></div>
                <br/>
                <div className="mb-2"><span className="text-muted"># Initialize backtest engine with 5 years of tick data</span></div>
                <div className="mb-2">engine = agentic.<span className="text-primary">BacktestEngine</span>(</div>
                <div className="mb-2 pl-4">dataset=<span className="text-secondary">"BINANCE_TICK_2019_2024"</span>,</div>
                <div className="mb-2 pl-4">capital=<span className="text-primary">1000000</span>,</div>
                <div className="mb-2 pl-4">latency_ms=<span className="text-primary">5</span>,</div>
                <div className="mb-2 pl-4">fees=<span className="text-secondary">"TIER_1_VIP"</span></div>
                <div className="mb-2">)</div>
                <br/>
                <div className="mb-2">strategy = agentic.models.<span className="text-primary">TransformerAlpha</span>(layers=12)</div>
                <div className="mb-2">results = engine.<span className="text-primary">run</span>(strategy)</div>
                <br/>
                <div className="mb-2"><span className="text-primary animate-pulse">{'>'} COMPILING RESULTS...</span></div>
                <div className="mb-2 text-foreground">SHARPE: 3.12</div>
                <div className="mb-2 text-foreground">WIN_RATE: 68.4%</div>
                <div className="mb-2 text-foreground">PROFIT_FACTOR: 2.1</div>
              </div>
            </div>
          </div>

          <div className="order-1 lg:order-2">
            <div className="inline-block px-3 py-1 border border-primary/30 text-primary font-mono text-xs mb-6 bg-primary/5">
              PHASE_02 // VALIDATION
            </div>
            <h2 className="text-4xl font-bold mb-6">Simulation that matches reality.</h2>
            <p className="text-muted-foreground font-mono mb-8 leading-relaxed">
              Don't be fooled by in-sample over-fitting. Our backtesting engine accounts for slippage, order book depth, and network latency. If it works in the lab, it works in the dark pool.
            </p>

            <div className="space-y-6 font-mono text-sm">
              <div className="flex items-start gap-4">
                <div className="w-8 h-8 rounded-full border border-primary flex items-center justify-center text-primary shrink-0">1</div>
                <div>
                  <h4 className="font-bold text-foreground mb-1">Tick-level Accuracy</h4>
                  <p className="text-muted-foreground text-xs">Test against full L2 historical data, not just aggregated OHLCV candles.</p>
                </div>
              </div>
              <div className="flex items-start gap-4">
                <div className="w-8 h-8 rounded-full border border-border flex items-center justify-center text-muted-foreground shrink-0">2</div>
                <div>
                  <h4 className="font-bold text-foreground mb-1">Walk-forward Optimization</h4>
                  <p className="text-muted-foreground text-xs">Automatically validate parameters across rolling out-of-sample windows.</p>
                </div>
              </div>
              <div className="flex items-start gap-4">
                <div className="w-8 h-8 rounded-full border border-border flex items-center justify-center text-muted-foreground shrink-0">3</div>
                <div>
                  <h4 className="font-bold text-foreground mb-1">Monte Carlo Simulation</h4>
                  <p className="text-muted-foreground text-xs">Stress test strategies against 10,000 synthetic market regimes.</p>
                </div>
              </div>
            </div>
          </div>

        </div>
      </div>
    </section>
  );
}