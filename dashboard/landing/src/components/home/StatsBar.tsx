import { useInView } from "framer-motion";
import { Users, BrainCircuit, Activity, LineChart } from "lucide-react";
import { useEffect, useRef, useState } from "react";

function Counter({ end, label, icon: Icon, prefix = "", suffix = "" }: { end: number, label: string, icon: any, prefix?: string, suffix?: string }) {
  const [count, setCount] = useState(0);
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true });

  useEffect(() => {
    if (!isInView) return;
    
    let start = 0;
    const duration = 2000;
    const increment = end / (duration / 16);
    const timer = setInterval(() => {
      start += increment;
      if (start >= end) {
        setCount(end);
        clearInterval(timer);
      } else {
        setCount(Math.floor(start));
      }
    }, 16);
    
    return () => clearInterval(timer);
  }, [isInView, end]);

  return (
    <div ref={ref} className="flex items-center gap-4 p-4 border border-card-border bg-card/50 rounded-xl backdrop-blur-sm">
      <div className="w-12 h-12 rounded-lg bg-muted flex items-center justify-center text-primary">
        <Icon className="w-6 h-6" />
      </div>
      <div>
        <div className="text-2xl font-bold font-mono text-foreground">
          {prefix}{count.toLocaleString()}{suffix}
        </div>
        <div className="text-sm text-muted-foreground">{label}</div>
      </div>
    </div>
  );
}

export function StatsBar() {
  return (
    <section id="landing-stats" className="py-12 border-y border-border bg-background/50 relative z-20 scroll-mt-24">
      <div className="container mx-auto px-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <Counter end={3421} label="Agents Online" icon={Users} />
          <Counter end={148902} label="Decisions Today" icon={BrainCircuit} />
          <Counter end={5230} label="Trades Executed" icon={Activity} />
          <Counter end={128} label="Backtests Running" icon={LineChart} suffix="+" />
        </div>
      </div>
    </section>
  );
}