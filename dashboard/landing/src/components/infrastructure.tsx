export default function Infrastructure() {
  return (
    <section id="infrastructure" className="py-24 border-b border-border bg-card/20">
      <div className="container mx-auto px-6">
        <div className="text-center mb-16">
          <h2 className="text-3xl font-bold mb-4">Institutional Grade. Metal to Market.</h2>
          <p className="font-mono text-muted-foreground text-sm max-w-2xl mx-auto">
            Speed is a feature. Our execution engines run on bare metal, written in Rust, optimized for microsecond latency. We handle the infrastructure, you focus on the alpha.
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-1">
          <div className="border border-border bg-background p-8">
            <div className="text-4xl font-mono text-primary mb-4">&lt;1ms</div>
            <h3 className="font-bold mb-2">Internal Latency</h3>
            <p className="text-sm text-muted-foreground font-mono">From signal generation to order transmission.</p>
          </div>
          <div className="border border-border bg-background p-8">
            <div className="text-4xl font-mono text-foreground mb-4">99.999%</div>
            <h3 className="font-bold mb-2">Uptime SLA</h3>
            <p className="text-sm text-muted-foreground font-mono">Distributed across multi-region availability zones.</p>
          </div>
          <div className="border border-border bg-background p-8">
            <div className="text-4xl font-mono text-foreground mb-4">1M+</div>
            <h3 className="font-bold mb-2">Events / Sec</h3>
            <p className="text-sm text-muted-foreground font-mono">Real-time market data ingestion capability per instance.</p>
          </div>
        </div>

        <div className="mt-16 border border-border bg-card p-6">
          <h4 className="font-mono text-xs text-muted-foreground mb-6">DEPLOYMENT_TOPOLOGY</h4>
          <div className="flex flex-col md:flex-row justify-between items-center gap-4 text-center font-mono text-sm">
            <div className="w-full border border-border p-4">
              <div>Exchanges (Binance, CME)</div>
            </div>
            <div className="hidden md:block text-muted-foreground">====&gt;</div>
            <div className="md:hidden text-muted-foreground">||</div>
            <div className="w-full border border-primary text-primary p-4 bg-primary/5">
              <div>Colocated Execution Nodes</div>
            </div>
            <div className="hidden md:block text-muted-foreground">&lt;====</div>
            <div className="md:hidden text-muted-foreground">||</div>
            <div className="w-full border border-border p-4">
              <div>Central Inference Cluster</div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}