import { motion } from "framer-motion";
import { useEffect, useState } from "react";

export default function Hero() {
  const [dataStream, setDataStream] = useState<string[]>([]);

  useEffect(() => {
    const symbols = ["BTC", "ETH", "SOL", "AAPL", "TSLA", "NVDA", "EURUSD", "GC"];
    const interval = setInterval(() => {
      const sym = symbols[Math.floor(Math.random() * symbols.length)];
      const price = (Math.random() * 1000).toFixed(2);
      const diff = (Math.random() * 5 - 2.5).toFixed(2);
      const sign = Number(diff) >= 0 ? "+" : "";
      setDataStream(prev => [`[${new Date().toISOString().split("T")[1].slice(0,-1)}] ${sym} EXEC ${price} (${sign}${diff}%)`, ...prev].slice(0, 5));
    }, 400);

    return () => clearInterval(interval);
  }, []);

  return (
    <section className="relative min-h-[90vh] flex flex-col justify-center border-b border-border pt-16">
      {/* Background Grid */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px]"></div>
      
      {/* Glow effect */}
      <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[400px] bg-primary/5 blur-[120px] rounded-full pointer-events-none"></div>

      <div className="container mx-auto px-6 relative z-10 grid lg:grid-cols-2 gap-12 items-center">
        <div className="max-w-2xl">
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="flex items-center gap-2 mb-6"
          >
            <div className="h-px w-8 bg-primary"></div>
            <span className="font-mono text-xs text-primary tracking-widest uppercase">Autonomous Alpha Generation</span>
          </motion.div>
          
          <motion.h1 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="text-5xl md:text-7xl font-bold tracking-tight mb-6 leading-[1.1]"
          >
            Machines that <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary to-emerald-700">never sleep.</span><br />
            Alpha that never stops.
          </motion.h1>

          <motion.p 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.2 }}
            className="text-lg text-muted-foreground mb-8 max-w-xl font-mono text-sm leading-relaxed"
          >
            Deploy autonomous agents that ingest live market data, discover latent patterns, and execute high-frequency strategies. Zero human emotion. 100% deterministic precision.
          </motion.p>

          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.3 }}
            className="flex flex-wrap gap-4"
          >
            <button className="bg-primary text-primary-foreground px-8 py-4 font-mono text-sm font-bold hover:bg-primary/90 transition-colors flex items-center gap-2">
              DEPLOY_AGENT
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M1 11L11 1M11 1H3.5M11 1V8.5" stroke="currentColor" strokeWidth="2"/>
              </svg>
            </button>
            <button className="border border-border bg-background/50 backdrop-blur px-8 py-4 font-mono text-sm text-foreground hover:border-primary/50 transition-colors">
              READ_DOCS
            </button>
          </motion.div>
        </div>

        {/* Terminal/Stream visual */}
        <motion.div 
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.7, delay: 0.4 }}
          className="relative h-[400px] border border-border bg-card p-4 flex flex-col font-mono text-xs overflow-hidden group"
        >
          <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-primary/50 via-primary to-primary/50 opacity-50"></div>
          <div className="flex justify-between items-center mb-4 border-b border-border pb-2">
            <div className="flex gap-2">
              <div className="w-3 h-3 bg-muted rounded-full"></div>
              <div className="w-3 h-3 bg-muted rounded-full"></div>
              <div className="w-3 h-3 bg-muted rounded-full"></div>
            </div>
            <span className="text-muted-foreground">TTY1: EXECUTION_ENGINE</span>
          </div>
          
          <div className="flex-1 flex flex-col justify-end gap-2 text-muted-foreground overflow-hidden">
            {dataStream.map((line, i) => (
              <div key={i} className={`whitespace-nowrap transition-all duration-300 ${i === 0 ? 'text-primary' : ''}`}>
                {line}
              </div>
            ))}
            <div className="flex items-center gap-2 mt-2 text-primary">
              <span>root@agentic-lab:~#</span>
              <span className="w-2 h-4 bg-primary animate-pulse"></span>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}