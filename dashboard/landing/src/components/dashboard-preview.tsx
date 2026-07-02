import { motion } from "framer-motion";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const data = Array.from({ length: 50 }, (_, i) => ({
  time: i,
  pnl: 10000 + Math.sin(i / 5) * 2000 + (i * 100) + (Math.random() * 500 - 250),
  drawdown: Math.max(0, -Math.sin(i / 5) * 500 + Math.random() * 200)
}));

export default function DashboardPreview() {
  return (
    <section className="py-24 border-b border-border overflow-hidden">
      <div className="container mx-auto px-6">
        <div className="mb-12 flex justify-between items-end">
          <div>
            <div className="font-mono text-xs text-primary mb-2">LIVE_TELEMETRY</div>
            <h2 className="text-3xl font-bold">Fleet Command</h2>
          </div>
          <div className="font-mono text-sm text-muted-foreground hidden sm:block">
            ACTIVE_AGENTS: 42 | TOTAL_AUM: $12.4M
          </div>
        </div>

        <div className="border border-border bg-card p-6 rounded-sm relative shadow-2xl shadow-primary/5">
          {/* Decorative corners */}
          <div className="absolute top-0 left-0 w-2 h-2 border-t border-l border-primary"></div>
          <div className="absolute top-0 right-0 w-2 h-2 border-t border-r border-primary"></div>
          <div className="absolute bottom-0 left-0 w-2 h-2 border-b border-l border-primary"></div>
          <div className="absolute bottom-0 right-0 w-2 h-2 border-b border-r border-primary"></div>

          <div className="grid lg:grid-cols-4 gap-6">
            <div className="lg:col-span-1 flex flex-col gap-4">
              <div className="p-4 border border-border bg-background">
                <div className="text-xs font-mono text-muted-foreground mb-1">AGGREGATE_PNL</div>
                <div className="text-2xl font-mono text-primary">+$42,105.50</div>
                <div className="text-xs font-mono text-primary mt-1">+4.2% TODAY</div>
              </div>
              <div className="p-4 border border-border bg-background">
                <div className="text-xs font-mono text-muted-foreground mb-1">MAX_DRAWDOWN</div>
                <div className="text-xl font-mono text-destructive">-1.8%</div>
              </div>
              <div className="p-4 border border-border bg-background">
                <div className="text-xs font-mono text-muted-foreground mb-1">SHARPE_RATIO</div>
                <div className="text-xl font-mono">2.84</div>
              </div>
              
              <div className="flex-1 border border-border bg-background p-4 overflow-hidden">
                <div className="text-xs font-mono text-muted-foreground mb-4">ACTIVE_STRATEGIES</div>
                <div className="flex flex-col gap-3">
                  {['ETH_ARB_01', 'BTC_MOMENTUM', 'SOL_LIQUIDATION'].map((strat, i) => (
                    <div key={strat} className="flex justify-between items-center text-xs font-mono border-b border-border/50 pb-2">
                      <div className="flex items-center gap-2">
                        <div className={`w-1.5 h-1.5 rounded-full ${i === 0 ? 'bg-primary' : 'bg-muted-foreground'}`}></div>
                        <span>{strat}</span>
                      </div>
                      <span className={i === 0 ? 'text-primary' : ''}>ACTIVE</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="lg:col-span-3 border border-border bg-background p-4 h-[400px] lg:h-[500px]">
              <div className="flex justify-between items-center mb-6">
                <div className="text-xs font-mono">CUMULATIVE_RETURN_CURVE</div>
                <div className="flex gap-2">
                  {['1H', '1D', '1W', '1M'].map((t) => (
                    <button key={t} className={`text-xs font-mono px-2 py-1 ${t === '1D' ? 'bg-primary/20 text-primary border border-primary/50' : 'text-muted-foreground border border-transparent hover:border-border'}`}>
                      {t}
                    </button>
                  ))}
                </div>
              </div>
              
              <div className="h-[calc(100%-3rem)] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={data} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorPnl" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="time" hide />
                    <YAxis hide domain={['dataMin - 1000', 'dataMax + 1000']} />
                    <Tooltip 
                      contentStyle={{ backgroundColor: 'hsl(var(--background))', borderColor: 'hsl(var(--border))', borderRadius: 0, fontFamily: 'monospace', fontSize: '12px' }}
                      itemStyle={{ color: 'hsl(var(--primary))' }}
                      labelStyle={{ display: 'none' }}
                    />
                    <Area 
                      type="monotone" 
                      dataKey="pnl" 
                      stroke="hsl(var(--primary))" 
                      fillOpacity={1} 
                      fill="url(#colorPnl)" 
                      strokeWidth={2}
                      isAnimationActive={true}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}