import { Button } from "@/components/ui/button";
import { ArrowUpRight, ArrowDownRight, Clock, ChevronDown } from "lucide-react";
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

const CONFIG_ROWS: { label: string; value: string }[] = [
  { label: "Initial capital", value: STORY_SPECS.initialCapital },
  { label: "Time period", value: `${STORY_SPECS.timePeriodLabel} · ${STORY_SPECS.timePeriod}` },
  { label: "Universe", value: STORY_SPECS.universe },
  { label: "Baselines", value: STORY_SPECS.baselines.join(", ") },
  { label: "Model", value: STORY_SPECS.model },
  { label: "Est. token cost", value: `${STORY_SPECS.estTokenCost} · ${STORY_SPECS.estTokens}` },
  { label: "Trades", value: String(STORY_SPECS.trades) },
  { label: "Avg hold", value: `${STORY_SPECS.avgHoldDays} days` },
];

function money(v: number) {
  return `$${v.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

function confidencePct(c: number) {
  return `${Math.round(c * 100)}%`;
}

export function Test() {
  return (
    <section id="test" className="py-24 relative scroll-mt-40">
      <div className="container mx-auto px-6">
        {/* Section intro */}
        <div className="mb-14 max-w-3xl">
          <p className="text-base md:text-lg font-mono uppercase tracking-widest text-primary mb-3">02 — Test</p>
          <h2 className="text-3xl md:text-4xl font-bold mb-3">Test your trading idea</h2>
          <p className="text-muted-foreground text-lg">
            A full agent run with fixed experiment settings, baseline comparisons, and a step-level decision log.
          </p>
        </div>

        {/* 1. Run context */}
        <header className="mb-10">
          <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
            <div>
              <p className="text-xs font-mono uppercase tracking-widest text-muted-foreground mb-2">
                Agent run
              </p>
              <h3 className="text-2xl md:text-3xl font-bold tracking-tight">
                {STORY_AGENT_NAME}{" "}
                <span className="text-muted-foreground font-semibold">vs baselines</span>
              </h3>
            </div>
            <span className="text-xs font-mono text-muted-foreground/80 tracking-wide">
              ILLUSTRATIVE
            </span>
          </div>
          <p className="text-sm md:text-base font-mono text-muted-foreground leading-relaxed">
            {STORY_SPECS.universe}
            <MetaSep />
            {STORY_SPECS.timePeriod}
            <MetaSep />
            {STORY_SPECS.initialCapital}
            <MetaSep />
            {STORY_SPECS.model}
          </p>
        </header>

        {/* 2. Key performance results */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-6 mb-10 pb-10 border-b border-border/60">
          <KeyMetric label="Total Return" value={STORY_SPECS.returnPct} tone="positive" />
          <KeyMetric label="vs Buy & Hold" value={STORY_SPECS.vsBuyHold} tone="positive" />
          <KeyMetric label="Sharpe Ratio" value={STORY_SPECS.sharpe} />
          <KeyMetric label="Max Drawdown" value={STORY_SPECS.maxDd} tone="destructive" />
        </div>

        {/* 3. Equity curve — primary visual */}
        <div className="mb-6">
          <div className="flex items-baseline justify-between gap-3 mb-4">
            <h4 className="text-sm font-mono uppercase tracking-widest text-muted-foreground">
              Equity curve
            </h4>
            <span className="text-xs text-muted-foreground hidden sm:inline">
              Normalized to {STORY_SPECS.initialCapital} at period open
            </span>
          </div>
          <div className="h-[360px] md:h-[440px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={EQUITY} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
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
                  width={48}
                />
                <ReferenceLine
                  y={C0}
                  stroke="hsl(var(--muted-foreground))"
                  strokeDasharray="4 4"
                  strokeOpacity={0.4}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "hsl(var(--card))",
                    borderColor: "hsl(var(--border))",
                    borderRadius: "8px",
                    fontSize: "12px",
                  }}
                  formatter={(v: number, name: string) => [money(v), name]}
                  labelFormatter={(label) => String(label)}
                />
                <Legend wrapperStyle={{ fontSize: "12px", paddingTop: "12px" }} iconType="plainline" />
                <Line
                  type="monotone"
                  dataKey="agent"
                  name={STORY_AGENT_NAME}
                  stroke={LINE.agent}
                  strokeWidth={2.5}
                  dot={false}
                  activeDot={{ r: 4 }}
                />
                <Line
                  type="monotone"
                  dataKey="spy"
                  name="S&P 500"
                  stroke={LINE.spy}
                  strokeWidth={1.75}
                  strokeDasharray="6 4"
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="djia"
                  name="DJIA"
                  stroke={LINE.djia}
                  strokeWidth={1.75}
                  strokeDasharray="2 3"
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="buyHold"
                  name="Buy & Hold"
                  stroke={LINE.buyHold}
                  strokeWidth={1.75}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Secondary stats under chart */}
        <div className="flex flex-wrap gap-x-8 gap-y-2 mb-14 text-sm text-muted-foreground font-mono">
          <SecondaryStat label="Trades" value={String(STORY_SPECS.trades)} />
          <SecondaryStat label="Avg hold" value={`${STORY_SPECS.avgHoldDays} days`} />
          <SecondaryStat label="Est. token cost" value={STORY_SPECS.estTokenCost} />
        </div>

        {/* 4. Agent decisions */}
        <div className="mb-14">
          <div className="flex items-baseline justify-between gap-3 mb-5">
            <h4 className="text-sm font-mono uppercase tracking-widest text-muted-foreground">
              Agent decisions
            </h4>
            <span className="text-xs text-muted-foreground font-mono">
              3 of {STORY_SPECS.trades} trades
            </span>
          </div>
          <ul className="divide-y divide-border/70 border-y border-border/70">
            {STORY_DECISIONS.map((d) => (
              <li key={`${d.step}-${d.symbol}`} className="py-5 flex gap-4 md:gap-6">
                <div
                  className={
                    d.type === "positive"
                      ? "w-9 h-9 rounded-md flex items-center justify-center bg-emerald-500/10 text-emerald-400 shrink-0 mt-0.5"
                      : d.type === "destructive"
                        ? "w-9 h-9 rounded-md flex items-center justify-center bg-red-500/10 text-red-400 shrink-0 mt-0.5"
                        : "w-9 h-9 rounded-md flex items-center justify-center bg-slate-500/10 text-slate-400 shrink-0 mt-0.5"
                  }
                >
                  {d.action === "BUY" ? (
                    <ArrowUpRight className="w-4 h-4" />
                  ) : d.action === "SELL" ? (
                    <ArrowDownRight className="w-4 h-4" />
                  ) : (
                    <Clock className="w-4 h-4" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mb-1.5">
                    <span className="text-xs font-mono text-muted-foreground">{d.time}</span>
                    <span className="text-sm font-semibold">
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
                      <span className="text-foreground">{d.symbol}</span>
                    </span>
                    <span className="text-xs font-mono text-muted-foreground">
                      conf. {confidencePct(d.confidence)}
                    </span>
                  </div>
                  <p className="text-sm text-muted-foreground leading-relaxed">{d.detail}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        {/* 5. Detailed experiment configuration */}
        <details className="group mb-12 border-t border-border/60 pt-6">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 select-none [&::-webkit-details-marker]:hidden">
            <span className="text-sm font-mono uppercase tracking-widest text-muted-foreground group-open:text-foreground transition-colors">
              Run configuration
            </span>
            <ChevronDown className="w-4 h-4 text-muted-foreground transition-transform group-open:rotate-180" />
          </summary>
          <dl className="mt-5 grid sm:grid-cols-2 gap-x-10 gap-y-3 text-sm">
            {CONFIG_ROWS.map((row) => (
              <div key={row.label} className="flex justify-between gap-4 py-1.5 border-b border-border/40">
                <dt className="text-muted-foreground shrink-0">{row.label}</dt>
                <dd className="text-foreground font-mono text-right">{row.value}</dd>
              </div>
            ))}
          </dl>
        </details>

        <div>
          <Button size="lg" className="bg-primary text-primary-foreground glow-primary hover:bg-primary/90" asChild>
            <a href="#race">Race this agent ↓</a>
          </Button>
        </div>
      </div>
    </section>
  );
}

function MetaSep() {
  return <span className="mx-2 text-border" aria-hidden="true">·</span>;
}

function KeyMetric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "positive" | "destructive";
}) {
  const valueClass =
    tone === "positive" ? "text-positive" : tone === "destructive" ? "text-destructive" : "text-foreground";
  return (
    <div>
      <div className="text-xs font-mono uppercase tracking-wider text-muted-foreground mb-1.5">{label}</div>
      <div className={`text-2xl md:text-3xl font-bold font-mono tabular-nums tracking-tight ${valueClass}`}>
        {value}
      </div>
    </div>
  );
}

function SecondaryStat({ label, value }: { label: string; value: string }) {
  return (
    <span>
      <span className="text-muted-foreground/80">{label}</span>
      <span className="mx-2 text-border">·</span>
      <span className="text-foreground font-medium">{value}</span>
    </span>
  );
}
