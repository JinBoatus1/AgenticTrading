export default function AssetClasses() {
  const assets = [
    { name: "Equities", markets: "NYSE, NASDAQ, LSE", volume: "$4.2T/mo", status: "ONLINE" },
    { name: "Crypto", markets: "Binance, Coinbase, Bybit", volume: "$1.8T/mo", status: "ONLINE" },
    { name: "FX", markets: "EBS, Reuters", volume: "$6.6T/day", status: "ONLINE" },
    { name: "Futures", markets: "CME, Eurex, ICE", volume: "12M contracts", status: "BETA" },
  ];

  return (
    <section className="py-24 border-b border-border bg-card/50">
      <div className="container mx-auto px-6">
        <div className="text-center mb-16">
          <h2 className="text-3xl font-bold mb-4">Multi-venue. Cross-asset.</h2>
          <p className="font-mono text-muted-foreground text-sm max-w-2xl mx-auto">
            Trade wherever alpha exists. A single unified API layer normalizes market data and order routing across fragmented global liquidity pools.
          </p>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
          {assets.map((asset) => (
            <div key={asset.name} className="border border-border bg-background p-6 hover:border-primary/50 transition-colors">
              <div className="flex justify-between items-start mb-8">
                <h3 className="text-xl font-bold">{asset.name}</h3>
                <div className={`text-[10px] font-mono px-2 py-0.5 border ${asset.status === 'ONLINE' ? 'text-primary border-primary/50 bg-primary/10' : 'text-secondary border-secondary/50 bg-secondary/10'}`}>
                  {asset.status}
                </div>
              </div>
              <div className="space-y-4 font-mono text-xs">
                <div>
                  <div className="text-muted-foreground mb-1">MARKETS</div>
                  <div>{asset.markets}</div>
                </div>
                <div>
                  <div className="text-muted-foreground mb-1">PROCESSED_VOL</div>
                  <div>{asset.volume}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}