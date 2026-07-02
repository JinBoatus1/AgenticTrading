import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Terminal, LineChart, MessageSquare } from "lucide-react";
import { useState, useEffect } from "react";

export function Hero() {
  return (
    <section className="relative pt-32 pb-20 md:pt-40 md:pb-32 overflow-hidden min-h-[90vh] flex items-center">
      <div className="absolute inset-0 bg-grid-pattern opacity-30 [mask-image:radial-gradient(ellipse_at_center,black,transparent_80%)]" />
      
      <div className="container mx-auto px-6 relative z-10 flex flex-col lg:flex-row items-center gap-16">
        <div className="flex-1 text-center lg:text-left">
          <motion.h1 
            className="text-5xl md:text-7xl font-bold tracking-tighter leading-[1.1] mb-6"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
          >
            Talk to agents<br />
            Test trading ideas
          </motion.h1>
          <motion.p 
            className="text-lg md:text-xl text-muted-foreground mb-8 max-w-xl mx-auto lg:mx-0 leading-relaxed"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
          >
            Connect your financial agent, interact through Discord, and review its decisions, trades, and performance in the lab.
          </motion.p>
          <motion.div 
            className="flex flex-col sm:flex-row items-center justify-center lg:justify-start gap-4"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.2 }}
          >
            <Button size="lg" className="w-full sm:w-auto bg-primary text-primary-foreground glow-primary hover:bg-primary/90 text-base h-12 px-8" asChild>
              <a href="/app">Get Started</a>
            </Button>
            <Button size="lg" variant="secondary" className="w-full sm:w-auto bg-secondary border-secondary-border text-secondary-foreground hover:bg-secondary/80 text-base h-12 px-8" asChild>
              <a href="https://discord.gg/9HnQ6XDG98" target="_blank" rel="noopener noreferrer">Join Discord Community</a>
            </Button>
          </motion.div>
        </div>
        
        <motion.div 
          className="flex-1 w-full max-w-2xl"
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.7, delay: 0.3 }}
        >
          <div className="bg-card border border-card-border rounded-xl shadow-2xl overflow-hidden flex flex-col h-[400px]">
            <div className="h-10 bg-muted/50 border-b border-border flex items-center px-4 gap-2">
              <div className="w-3 h-3 rounded-full bg-destructive/80" />
              <div className="w-3 h-3 rounded-full bg-secondary-border" />
              <div className="w-3 h-3 rounded-full bg-positive/80" />
              <div className="ml-4 text-xs font-mono text-muted-foreground flex items-center gap-2">
                <Terminal className="w-3 h-3" />
                agent-playground.exe
              </div>
            </div>
            <div className="flex-1 p-4 font-mono text-sm overflow-hidden flex flex-col gap-4">
              <ChatSimulation />
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

function ChatSimulation() {
  const [step, setStep] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setStep((s) => (s < 5 ? s + 1 : 0));
    }, 2500);
    return () => clearInterval(timer);
  }, []);

  return (
    <>
      <div className="flex gap-3">
        <div className="w-6 h-6 rounded bg-primary/20 text-primary flex items-center justify-center shrink-0">
          <MessageSquare className="w-3 h-3" />
        </div>
        <div className="bg-muted p-3 rounded-r-lg rounded-bl-lg text-foreground max-w-[80%]">
          Let's test a mean-reversion strategy on TSLA. If RSI drops below 30, buy. Sell at RSI 70.
        </div>
      </div>
      
      {step >= 1 && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3 flex-row-reverse">
          <div className="w-6 h-6 rounded bg-secondary-border flex items-center justify-center shrink-0">
            <Terminal className="w-3 h-3 text-muted-foreground" />
          </div>
          <div className="bg-card border border-card-border p-3 rounded-l-lg rounded-br-lg text-muted-foreground max-w-[80%]">
            <span className="text-primary">Running backtest...</span><br/>
            Symbol: TSLA<br/>
            Timeframe: 1H<br/>
            Period: YTD
          </div>
        </motion.div>
      )}

      {step >= 2 && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3 flex-row-reverse">
          <div className="w-6 h-6 rounded bg-secondary-border flex items-center justify-center shrink-0">
            <Terminal className="w-3 h-3 text-muted-foreground" />
          </div>
          <div className="bg-card border border-card-border p-3 rounded-l-lg rounded-br-lg text-foreground max-w-[80%]">
            <div className="flex items-center gap-2 mb-2 text-positive">
              <LineChart className="w-4 h-4" />
              <span className="font-bold">Backtest Complete</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div>Win Rate: <span className="text-foreground">62.4%</span></div>
              <div>Sharpe: <span className="text-foreground">1.84</span></div>
              <div>Return: <span className="text-positive">+14.2%</span></div>
              <div>Max DD: <span className="text-destructive">-8.1%</span></div>
            </div>
          </div>
        </motion.div>
      )}
      
      {step >= 3 && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3 flex-row-reverse">
          <div className="w-6 h-6 rounded bg-secondary-border flex items-center justify-center shrink-0">
            <Terminal className="w-3 h-3 text-muted-foreground" />
          </div>
          <div className="bg-card border border-card-border p-3 rounded-l-lg rounded-br-lg text-foreground max-w-[80%]">
            Shall I deploy this strategy to the paper trading lab?
          </div>
        </motion.div>
      )}
      
      {step >= 4 && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3">
          <div className="w-6 h-6 rounded bg-primary/20 text-primary flex items-center justify-center shrink-0">
            <MessageSquare className="w-3 h-3" />
          </div>
          <div className="bg-muted p-3 rounded-r-lg rounded-bl-lg text-foreground max-w-[80%]">
            Yes, deploy with $10,000 capital.
          </div>
        </motion.div>
      )}
    </>
  );
}