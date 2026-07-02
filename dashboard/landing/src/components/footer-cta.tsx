export default function FooterCTA() {
  return (
    <footer className="relative bg-background border-t border-border overflow-hidden">
      {/* Background glow */}
      <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-full h-[500px] bg-primary/5 blur-[150px] pointer-events-none"></div>
      
      <div className="container mx-auto px-6 py-24 text-center relative z-10">
        <h2 className="text-5xl font-bold mb-6">Ready to deploy?</h2>
        <p className="font-mono text-muted-foreground max-w-xl mx-auto mb-10">
          Agentic Trading Lab is currently in private beta for select institutional partners and quantitative researchers. Request access to evaluate the platform.
        </p>
        
        <div className="flex flex-col sm:flex-row justify-center gap-4">
          <button className="bg-primary text-primary-foreground px-8 py-4 font-mono font-bold hover:bg-primary/90 transition-colors">
            REQUEST_BETA_ACCESS
          </button>
          <button className="border border-border bg-background px-8 py-4 font-mono text-foreground hover:border-muted-foreground transition-colors">
            VIEW_DOCUMENTATION
          </button>
        </div>
      </div>

      <div className="border-t border-border bg-card/50">
        <div className="container mx-auto px-6 py-8 flex flex-col md:flex-row justify-between items-center gap-4 font-mono text-xs text-muted-foreground">
          <div>
            &copy; {new Date().getFullYear()} AGENTIC TRADING LAB. ALL RIGHTS RESERVED.
          </div>
          <div className="flex gap-6">
            <a href="#" className="hover:text-primary transition-colors">TERMS_OF_SERVICE</a>
            <a href="#" className="hover:text-primary transition-colors">PRIVACY_POLICY</a>
            <a href="#" className="hover:text-primary transition-colors">SYSTEM_STATUS</a>
          </div>
        </div>
      </div>
    </footer>
  );
}