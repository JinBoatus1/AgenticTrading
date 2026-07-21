import { Button } from "@/components/ui/button";
import { ArrowUpRight, ArrowDownRight, Clock } from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
  ReferenceLine,
} from "recharts";
import { STORY_AGENT_NAME, STORY_DECISIONS, STORY_SPECS } from "./storyline";

const C0 = STORY_SPECS.initialCapitalNum;

/**
 * Illustrative 1-month equity paths (hourly-sampled days).
 * Agent ends +14.2%; baselines trail with distinct paths.
 */
const EQUITY = [
  { t: "Apr 15", agent: C0, djia: C0, spy: C0, buyHold: C0 },
  { t: "Apr 18", agent: 10180, djia: 10040, spy: 10090, buyHold: 10060 },
  { t: "Apr 22", agent: 10460, djia: 9980, spy: 10140, buyHold: 10120 },
  { t: "Apr 25", agent: 10210, djia: 10090, spy: 10050, buyHold: 10040 },
  { t: "Apr 29", agent: 10740, djia: 10160, spy: 10280, buyHold: 10210 },
  { t: "May 2", agent: 10520, djia: 10080, spy: 10190, buyHold: 10150 },
  { t: "May 6", agent: 11180, djia: 10240, spy: 10360, buyHold: 10340 },
  { t: "May 9", agent: 10860, djia: 10190, spy: 10310, buyHold: 10280 },
  { t: "May 12", agent: 11340, djia: 10280, spy: 10420, buyHold: 10390 },
  { t: "May 15", agent: 11420, djia: 10310, spy: 10480, buyHold: 10490 },
];

const LINE = {
  agent: "#22d3ee",
  djia: "#94a3b8",
  spy: "#64748b",
  buyHold: "#a78bfa",
} as const;

const SETTINGS: { label: string; value: string; wide?: boolean }[] = [
  { label: "Initial capital", value: STORY_SPECS.initialCapital },
  { label: "Time period", value: `${STORY_SPECS.timePeriodLabel} · ${STORY_SPECS.timePeriod}` },
  { label: "Universe", value: STORY_SPECS.universe },
  { label: "Baselines", value: STORY_SPECS.baselines.join(" · "), wide: true },
  { label: "Model", value: STORY_SPECS.model },
  { label: "Est. token cost", value: `${STORY_SPECS.estTokenCost} · ${STORY_SPECS.estTokens}` },
];

function money(v: number) {
  return `$${v.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

export function Test() {
  return (
    <section id="test" className="py-24 relative scroll-mt-40">
      <div className="container mx-auto px-6">
        <div className="mb-10 max-w-3xl">
          <p className="text-base md:text-lg font-mono uppercase tracking-widest text-primary mb-3">02 — Test</p>
          <h2 className="text-3xl md:text-4xl font-bold mb-3">Test your trading idea</h2>
          <p className="text-muted-foreground text-lg">
            A full agent run with fixed experiment settings, baseline comparisons, and a step-level decision log.
          </p>
        </div>

        <figure className="bg-card border border-card-border rounded-xl shadow-2xl overflow-hidden mb-10">
          <figcaption className="flex flex-wrap items-start justify-between gap-3 px-6 md:px-8 pt-6 md:pt-8 pb-4 border-b border-border">
            <div className="min-w-0">
              <p className="text-xs font-mono uppercase tracking-widest text-muted-foreground mb-1">
                Figure · Agent run
              </p>
              <h3 className="text-lg md:text-xl font-bold text-foreground">
                {STORY_AGENT_NAME} vs baselines — equity curve
              </h3>
              <p className="text-sm text-muted-foreground mt-1 font-mono">
                {STORY_SPECS.universe} · {STORY_SPECS.timePeriod} · {STORY_SPECS.initialCapital} start
              </p>
            </div>
            <span className="text-xs font-mono text-muted-foreground bg-muted px-2.5 py-1 rounded shrink-0">
              ILLUSTRATIVE
            </span>
          </figcaption>

          <div className="p-6 md:p-8">
            {/* Experiment settings — above the chart */}
            <div className="mb-8">
              <div className="flex items-baseline justify-between gap-3 mb-4">
                <h4 className="text-xs font-mono uppercase tracking-widest text-muted-foreground">
                  Experiment settings
                </h4>
                <span className="text-xs text-muted-foreground font-mono">Fixed for this run</span>
              </div>
              <dl className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {SETTINGS.map((s) => (
                  <div
                    key={s.label}
                    className={`rounded-lg border border-border bg-background/80 px-4 py-3 ${
                      s.wide ? "sm:col-span-2 lg:col-span-1" : ""
                    }`}
                  >
                    <dt className="text-[11px] font-mono uppercase tracking-wider text-muted-foreground mb-1">
                      {s.label}
                    </dt>
                    <dd className="text-sm font-medium text-foreground leading-snug">{s.value}</dd>
                  </div>
                ))}
              </dl>
            </div>

            {/* Full-width chart — linear (no smooth) */}
            <div className="h-[340px] md:h-[420px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={EQUITY} margin={{ top: 12, right: 16, left: 4, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                  <XAxis
                    dataKey="t"
                    stroke="hsl(var(--muted-foreground))"
                    fontSize={11}
                    tickLine={false}
                    axisLine={false}
                  />
                  <YAxis
                    stroke="hsl(var(--muted-foreground))"
                    fontSize={11}
                    tickLine={false}
                    axisLine={false}
                    domain={[9600, 11600]}
                    ticks={[10000, 10500, 11000, 11500]}
                    tickFormatter={(v) => `$${(v / 1000).toFixed(1)}k`}
                    width={52}
                  />
                  <ReferenceLine
                    y={C0}
                    stroke="hsl(var(--muted-foreground))"
                    strokeDasharray="4 4"
                    strokeOpacity={0.45}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "hsl(var(--card))",
                      borderColor: "hsl(var(--border))",
                      borderRadius: "8px",
                      fontSize: "12px",
                    }}
                    formatter={(v: number, name: string) => [money(v), name]}
                    labelFormatter={(label) => `Date · ${label}`}
                  />
                  <Legend
                    wrapperStyle={{ fontSize: "12px", paddingTop: "8px" }}
                    iconType="plainline"
                  />
                  <Line
                    type="linear"
                    dataKey="agent"
                    name={STORY_AGENT_NAME}
                    stroke={LINE.agent}
                    strokeWidth={2.5}
                    dot={false}
                    activeDot={{ r: 4 }}
                  />
                  <Line
                    type="linear"
                    dataKey="spy"
                    name="S&P 500"
                    stroke={LINE.spy}
                    strokeWidth={1.75}
                    strokeDasharray="6 4"
                    dot={false}
                  />
                  <Line
                    type="linear"
                    dataKey="djia"
                    name="DJIA"
                    stroke={LINE.djia}
                    strokeWidth={1.75}
                    strokeDasharray="2 3"
                    dot={false}
                  />
                  <Line
                    type="linear"
                    dataKey="buyHold"
                    name="Buy & Hold"
                    stroke={LINE.buyHold}
                    strokeWidth={1.75}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <p className="text-xs text-muted-foreground mt-3 leading-relaxed">
              Equity normalized to {STORY_SPECS.initialCapital} on period open. Baselines: price return of
              DJIA and S&P 500, plus equal-weight buy-and-hold on the same universe. Dashed gray line marks
              initial capital.
            </p>

            {/* Metrics — below the chart */}
            <div className="mt-8 pt-6 border-t border-border">
              <p className="text-xs font-mono uppercase tracking-widest text-muted-foreground mb-4">
                Run metrics
              </p>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
                <Metric label="Total return" value={STORY_SPECS.returnPct} tone="positive" />
                <Metric label="Sharpe ratio" value={STORY_SPECS.sharpe} />
                <Metric label="Max drawdown" value={STORY_SPECS.maxDd} tone="destructive" />
                <Metric label="vs Buy & Hold" value={STORY_SPECS.vsBuyHold} tone="positive" />
              </div>
              <div className="grid grid-cols-2 gap-3 max-w-sm">
                <MiniStat label="Trades" value={String(STORY_SPECS.trades)} />
                <MiniStat label="Avg hold" value={`${STORY_SPECS.avgHoldDays}d`} />
              </div>
            </div>
          </div>
        </figure>

        <div className="mb-10">
          <div className="flex items-baseline justify-between gap-3 mb-4">
            <h3 className="text-sm font-mono uppercase tracking-widest text-muted-foreground">
              Decision log · selected steps
            </h3>
            <span className="text-xs text-muted-foreground font-mono">
              {STORY_SPECS.trades} trades total
            </span>
          </div>
          <div className="border border-card-border rounded-xl overflow-hidden bg-card">
            <div className="hidden md:grid grid-cols-12 gap-2 px-4 py-2.5 text-[11px] font-mono uppercase tracking-wider text-muted-foreground border-b border-border bg-muted/30">
              <div className="col-span-2">Step / time</div>
              <div className="col-span-2">Action</div>
              <div className="col-span-2">Size</div>
              <div className="col-span-6">Rationale</div>
            </div>
            {STORY_DECISIONS.map((d) => (
              <div
                key={`${d.step}-${d.symbol}`}
                className="grid md:grid-cols-12 gap-2 px-4 py-3.5 border-b border-border last:border-b-0 items-start"
              >
                <div className="md:col-span-2 font-mono text-xs text-muted-foreground">
                  <div className="text-foreground font-semibold">#{d.step}</div>
                  <div>{d.time}</div>
                </div>
                <div className="md:col-span-2 flex items-center gap-2">
                  <span
                    className={
                      d.type === "positive"
                        ? "w-7 h-7 rounded-md flex items-center justify-center bg-emerald-500/10 text-emerald-400 shrink-0"
                        : d.type === "destructive"
                          ? "w-7 h-7 rounded-md flex items-center justify-center bg-red-500/10 text-red-400 shrink-0"
                          : "w-7 h-7 rounded-md flex items-center justify-center bg-slate-500/10 text-slate-400 shrink-0"
                    }
                  >
                    {d.action === "BUY" ? (
                      <ArrowUpRight className="w-3.5 h-3.5" />
                    ) : d.action === "SELL" ? (
                      <ArrowDownRight className="w-3.5 h-3.5" />
                    ) : (
                      <Clock className="w-3.5 h-3.5" />
                    )}
                  </span>
                  <div className="text-sm font-semibold">
                    <span
                      className={
                        d.type === "positive"
                          ? "text-positive"
                          : d.type === "destructive"
                            ? "text-destructive"
                            : "text-muted-foreground"
                      }
                    >
                      {d.action}
                    </span>{" "}
                    {d.symbol}
                  </div>
                </div>
                <div className="md:col-span-2 font-mono text-xs text-muted-foreground">
                  {d.shares} sh @ {d.price}
                </div>
                <div className="md:col-span-6 text-sm text-muted-foreground leading-snug">{d.detail}</div>
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

function Metric({ label, value, tone }: { label: string; value: string; tone?: "positive" | "destructive" }) {
  const valueClass =
    tone === "positive" ? "text-positive" : tone === "destructive" ? "text-destructive" : "text-foreground";
  return (
    <div className="p-3.5 border border-border rounded-lg bg-background">
      <div className="text-xs text-muted-foreground mb-1">{label}</div>
      <div className={`text-xl font-bold font-mono tabular-nums ${valueClass}`}>{value}</div>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="p-3 border border-border rounded-lg bg-background">
      <div className="text-[11px] text-muted-foreground mb-0.5">{label}</div>
      <div className="text-sm font-bold font-mono text-foreground">{value}</div>
    </div>
  );
}
