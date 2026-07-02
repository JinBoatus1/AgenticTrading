import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

const data = [
  { time: 'Jan', equity: 10000 },
  { time: 'Feb', equity: 10400 },
  { time: 'Mar', equity: 10250 },
  { time: 'Apr', equity: 11200 },
  { time: 'May', equity: 10900 },
  { time: 'Jun', equity: 12100 },
  { time: 'Jul', equity: 13500 },
  { time: 'Aug', equity: 13100 },
  { time: 'Sep', equity: 14800 },
  { time: 'Oct', equity: 15600 },
  { time: 'Nov', equity: 15100 },
  { time: 'Dec', equity: 17200 },
];

export function Backtesting() {
  return (
    <section id="backtesting" className="py-24 relative">
      <div className="container mx-auto px-6">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-4xl font-bold mb-4">Instant High-Fidelity Backtesting</h2>
          <p className="text-muted-foreground max-w-2xl mx-auto">Validate ideas against tick-level historical data in seconds, not hours.</p>
        </div>

        <div className="bg-card border border-card-border rounded-xl shadow-2xl overflow-hidden p-6 md:p-8">
          <div className="grid lg:grid-cols-4 gap-8">
            <div className="lg:col-span-3 h-[400px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorEquity" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                  <XAxis dataKey="time" stroke="hsl(var(--muted-foreground))" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis 
                    stroke="hsl(var(--muted-foreground))" 
                    fontSize={12} 
                    tickLine={false} 
                    axisLine={false} 
                    tickFormatter={(value) => `$${value/1000}k`}
                  />
                  <Tooltip 
                    contentStyle={{ backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))', borderRadius: '8px' }}
                    itemStyle={{ color: 'hsl(var(--primary))' }}
                  />
                  <Area type="monotone" dataKey="equity" stroke="hsl(var(--primary))" strokeWidth={3} fillOpacity={1} fill="url(#colorEquity)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            
            <div className="lg:col-span-1 flex flex-col justify-center gap-6">
              <div className="p-4 border border-border rounded-lg bg-background">
                <div className="text-sm text-muted-foreground mb-1">Total Return</div>
                <div className="text-3xl font-bold text-positive font-mono">+72.0%</div>
              </div>
              <div className="p-4 border border-border rounded-lg bg-background">
                <div className="text-sm text-muted-foreground mb-1">Sharpe Ratio</div>
                <div className="text-3xl font-bold text-foreground font-mono">2.14</div>
              </div>
              <div className="p-4 border border-border rounded-lg bg-background">
                <div className="text-sm text-muted-foreground mb-1">Max Drawdown</div>
                <div className="text-3xl font-bold text-destructive font-mono">-11.2%</div>
              </div>
              <div className="p-4 border border-border rounded-lg bg-background">
                <div className="text-sm text-muted-foreground mb-1">Win Rate</div>
                <div className="text-3xl font-bold text-foreground font-mono">58.4%</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}