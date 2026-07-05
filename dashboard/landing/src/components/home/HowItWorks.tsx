import { motion } from "framer-motion";
import { MessageSquare, FlaskConical, Rocket } from "lucide-react";

export function HowItWorks() {
  const steps = [
    {
      icon: MessageSquare,
      title: "Talk",
      description: "Describe your trading idea in plain language. Your agent understands context, indicators, and market structures."
    },
    {
      icon: FlaskConical,
      title: "Test",
      description: "The agent translates your idea into logic and runs an instant backtest across historical data."
    },
    {
      icon: Rocket,
      title: "Trade",
      description: "Deploy your validated agent to live markets or paper trading with a single confirmation."
    }
  ];

  return (
    <section id="agents" className="py-24 relative">
      <div className="container mx-auto px-6">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-4xl font-bold mb-4">From Idea to Execution in Minutes</h2>
          <p className="text-muted-foreground max-w-2xl mx-auto">Stop writing boilerplate. Focus on the alpha.</p>
        </div>

        <div className="grid md:grid-cols-3 gap-8 relative">
          <div className="hidden md:block absolute top-12 left-[15%] right-[15%] h-[1px] bg-border border-dashed border-t-2" />
          
          {steps.map((step, i) => (
            <motion.div 
              key={i}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.2 }}
              className="relative z-10 bg-card border border-card-border p-8 rounded-xl text-center shadow-lg hover:border-primary/50 transition-colors"
            >
              <div className="w-16 h-16 mx-auto bg-muted rounded-full flex items-center justify-center text-primary mb-6 glow-primary">
                <step.icon className="w-8 h-8" />
              </div>
              <h3 className="text-xl font-bold mb-3">{step.title}</h3>
              <p className="text-muted-foreground text-sm leading-relaxed">{step.description}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}