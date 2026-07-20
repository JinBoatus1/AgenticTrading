import { Button } from "@/components/ui/button";
import { ArrowUpRight, ArrowDownRight, Clock } from "lucide-react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { STORY_DECISIONS, STORY_PROMPT, STORY_SPECS } from "./storyline";

/** Jagged path: start $10k, end +14.2%, dips toward ~-8.6% max DD. */
const equity = [
  { time: "May 4", value: 10000 },
  { time: "May 5", value: 10380 },
  { time: "May 6", value: 9780 },
  { time: "May 7", value: 10540 },
  { time: "May 8", value: 9140 },
  { time: "May 9", value: 10960 },
  { time: "May 12", value: 11420 },
];

export function Test() {
  return (
    <section id="test" className="py-24 relative scroll-mt-24">
      <div className="container mx-auto px-6">
        <div className="mb-8 max-w-2xl">
          <p className="text-base md:text-lg font-mono uppercase tracking-widest text-primary mb-3">02 — Test</p>
          <h2 className="text-3xl md:text-4xl font-bold mb-3">Test your trading idea</h2>
        </div>

        {/* Specs strip: prompt + window — ties to Talk */}
        <div className="mb-8 grid gap-3 sm:grid-cols-2 text-sm">
          <Spec label="Prompt" value={STORY_PROMPT} accent />
          <Spec label="Window" value={STORY_SPECS.window} />
        </div>

        <div className="bg-card border border-card-border rounded-xl shadow-2xl overflow-hidden p-6 md:p-8 mb-8">
          <div className="grid lg:grid-cols-4 gap-8">
            <div className="lg:col-span-3 h-[320px] md:h-[380px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={equity} margin={{ top: 10, right: 10, left: 8, bottom: 0 }}>
                  <defs>
                    <linearGradient id="testEquity" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                  <XAxis dataKey="time" stroke="hsl(var(--muted-foreground))" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis
                    stroke="hsl(var(--muted-foreground))"
                    fontSize={12}
                    tickLine={false}
                    axisLine={false}
                    domain={[8500, 12000]}
                    ticks={[9000, 10000, 11000, 12000]}
                    tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                  />
                  <Tooltip
                    contentStyle={{ backgroundColor: "hsl(var(--card))", borderColor: "hsl(var(--border))", borderRadius: "8px" }}
                    itemStyle={{ color: "hsl(var(--primary))" }}
                    formatter={(v: number) => [`$${v.toLocaleString()}`, "Equity"]}
                  />
                  <Area
                    type="linear"
                    dataKey="value"
                    name="Your agent"
                    stroke="hsl(var(--primary))"
                    strokeWidth={2}
                    fillOpacity={1}
                    fill="url(#testEquity)"
                    dot={{ r: 3, fill: "hsl(var(--primary))", strokeWidth: 0 }}
                    activeDot={{ r: 4 }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            <div className="lg:col-span-1 flex flex-col justify-center gap-4">
              <Metric label="Return" value={STORY_SPECS.returnPct} tone="positive" />
              <Metric label="Sharpe" value={STORY_SPECS.sharpe} />
              <Metric label="Max DD" value={STORY_SPECS.maxDd} tone="destructive" />
              <Metric label="vs Buy & Hold" value={STORY_SPECS.vsBuyHold} tone="positive" />
            </div>
          </div>
        </div>

        <div className="mb-10">
          <h3 className="text-sm font-mono uppercase tracking-widest text-muted-foreground mb-4">Decision log</h3>
          <div className="grid md:grid-cols-3 gap-3">
            {STORY_DECISIONS.map((d) => (
              <div key={`${d.action}-${d.detail}`} className="p-4 border border-card-border rounded-lg bg-card flex items-start gap-3">
                <div
                  className={
                    d.type === "positive"
                      ? "w-9 h-9 rounded-full flex items-center justify-center bg-emerald-500/10 text-emerald-400 shrink-0"
                      : d.type === "destructive"
                        ? "w-9 h-9 rounded-full flex items-center justify-center bg-red-500/10 text-red-400 shrink-0"
                        : "w-9 h-9 rounded-full flex items-center justify-center bg-slate-500/10 text-slate-400 shrink-0"
                  }
                >
                  {d.action === "BUY" ? <ArrowUpRight className="w-4 h-4" /> : d.action === "SELL" ? <ArrowDownRight className="w-4 h-4" /> : <Clock className="w-4 h-4" />}
                </div>
                <div className="min-w-0">
                  <div className="font-semibold text-sm">
                    <span className={d.type === "positive" ? "text-positive" : d.type === "destructive" ? "text-destructive" : "text-muted-foreground"}>
                      {d.action}
                    </span>{" "}
                    {d.symbol}
                  </div>
                  <div className="text-xs text-muted-foreground font-mono mt-1">{d.detail}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <Button size="lg" className="bg-primary text-primary-foreground glow-primary hover:bg-primary/90" asChild>
            <a href="#race">Race this agent ↓</a>
          </Button>
        </div>
      </div>
    </section>
  );
}

function Spec({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className={`rounded-lg border px-4 py-3 ${accent ? "border-primary/40 bg-primary/5" : "border-border bg-card"}`}>
      <div className="text-xs font-mono uppercase tracking-widest text-muted-foreground mb-1">{label}</div>
      <div className={`text-sm leading-snug ${accent ? "text-foreground font-medium" : "text-muted-foreground font-mono"}`}>
        {value}
      </div>
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: "positive" | "destructive" }) {
  const valueClass =
    tone === "positive" ? "text-positive" : tone === "destructive" ? "text-destructive" : "text-foreground";
  return (
    <div className="p-4 border border-border rounded-lg bg-background">
      <div className="text-sm text-muted-foreground mb-1">{label}</div>
      <div className={`text-2xl font-bold font-mono ${valueClass}`}>{value}</div>
    </div>
  );
}
