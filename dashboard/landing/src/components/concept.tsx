import { motion } from "framer-motion";

const capabilities = [
  {
    id: "01",
    title: "Continuous Market Ingestion",
    desc: "Agents process L2 order book data, tick-level trades, and unstructured text in real-time across 50+ venues.",
  },
  {
    id: "02",
    title: "Neural Strategy Synthesis",
    desc: "Reinforcement learning models discover complex alpha signals that traditional statistical arbitrage misses.",
  },
  {
    id: "03",
    title: "Sub-millisecond Execution",
    desc: "Colocated servers in NY4 and LD4 execute strategies with deterministic latency profiles.",
  }
];

export default function Concept() {
  return (
    <section id="agents" className="py-24 border-b border-border bg-card/30">
      <div className="container mx-auto px-6">
        <div className="max-w-3xl mb-16">
          <h2 className="text-3xl md:text-5xl font-bold mb-6">
            Not a Copilot.<br/>
            An <span className="text-primary">Autonomous Operator.</span>
          </h2>
          <p className="font-mono text-muted-foreground leading-relaxed">
            While others build chat interfaces for data analysis, we build autonomous agents that pull the trigger. Once parameterized and deployed, an Agentic Lab instance requires zero human intervention to generate returns.
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-8">
          {capabilities.map((cap, i) => (
            <motion.div 
              key={cap.id}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: i * 0.1 }}
              className="border border-border p-6 bg-background relative group hover:border-primary/50 transition-colors"
            >
              <div className="text-5xl font-mono font-bold text-muted/30 absolute top-4 right-4 pointer-events-none group-hover:text-primary/10 transition-colors">
                {cap.id}
              </div>
              <h3 className="text-xl font-bold mb-4 font-sans mt-8">{cap.title}</h3>
              <p className="text-sm text-muted-foreground font-mono leading-relaxed">
                {cap.desc}
              </p>
              
              <div className="mt-8 h-1 w-0 bg-primary group-hover:w-full transition-all duration-500"></div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}