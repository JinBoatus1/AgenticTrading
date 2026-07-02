export default function RiskManagement() {
  return (
    <section id="risk" className="py-24 border-b border-border bg-background">
      <div className="container mx-auto px-6">
        <div className="flex flex-col lg:flex-row gap-16 items-center">
          
          <div className="lg:w-1/2">
            <h2 className="text-4xl font-bold mb-6">Paranoia as a Service.</h2>
            <p className="font-mono text-muted-foreground mb-8">
              Alpha generation means nothing if you blow up the account. Agentic Lab employs an independent hierarchy of risk agents that monitor, throttle, and kill execution agents if they breach defined parameters.
            </p>

            <div className="grid sm:grid-cols-2 gap-4 font-mono text-sm">
              <div className="border border-destructive/30 bg-destructive/5 p-4">
                <div className="text-destructive mb-2">MAX_DRAWDOWN_KILL</div>
                <p className="text-muted-foreground text-xs">Instantly liquidates positions and halts trading if daily drawdown exceeds threshold.</p>
              </div>
              <div className="border border-border p-4 bg-card">
                <div className="text-foreground mb-2">FAT_FINGER_PREVENTION</div>
                <p className="text-muted-foreground text-xs">Order size and frequency limits enforced at the infrastructure level.</p>
              </div>
              <div className="border border-border p-4 bg-card">
                <div className="text-foreground mb-2">CORRELATION_CAPS</div>
                <p className="text-muted-foreground text-xs">Prevents over-exposure to highly correlated assets across different strategies.</p>
              </div>
              <div className="border border-border p-4 bg-card">
                <div className="text-foreground mb-2">EXCHANGE_REDUNDANCY</div>
                <p className="text-muted-foreground text-xs">Automatic failover if an exchange API becomes unresponsive.</p>
              </div>
            </div>
          </div>

          <div className="lg:w-1/2 w-full h-[400px] border border-border bg-card p-6 flex flex-col items-center justify-center relative overflow-hidden">
            <div className="absolute inset-0 flex items-center justify-center opacity-5">
              <svg width="400" height="400" viewBox="0 0 100 100" className="animate-spin-slow">
                <circle cx="50" cy="50" r="48" fill="none" stroke="currentColor" strokeWidth="1" strokeDasharray="5 5"/>
                <circle cx="50" cy="50" r="30" fill="none" stroke="currentColor" strokeWidth="1" strokeDasharray="2 8"/>
              </svg>
            </div>
            
            <div className="z-10 w-full max-w-sm space-y-4">
              <div className="flex justify-between items-center text-xs font-mono border-b border-border pb-2">
                <span className="text-muted-foreground">STRATEGY_01</span>
                <span className="text-primary">OK</span>
              </div>
              <div className="flex justify-between items-center text-xs font-mono border-b border-border pb-2">
                <span className="text-muted-foreground">STRATEGY_02</span>
                <span className="text-primary">OK</span>
              </div>
              <div className="flex justify-between items-center text-xs font-mono border-b border-border pb-2 bg-destructive/10 p-2 -mx-2">
                <span className="text-destructive font-bold">STRATEGY_03</span>
                <span className="text-destructive animate-pulse">HALTED - VOLATILITY_SPIKE</span>
              </div>
              <div className="flex justify-between items-center text-xs font-mono border-b border-border pb-2">
                <span className="text-muted-foreground">STRATEGY_04</span>
                <span className="text-primary">OK</span>
              </div>
            </div>

            <div className="absolute bottom-6 left-6 font-mono text-[10px] text-muted-foreground">
              GLOBAL_RISK_ENGINE: ACTIVE<br/>
              PING: 1.2ms
            </div>
          </div>

        </div>
      </div>
    </section>
  );
}