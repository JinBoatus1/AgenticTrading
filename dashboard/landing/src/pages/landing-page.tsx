import { Navbar } from "../components/home/Navbar";
import { Hero } from "../components/home/Hero";
import { StatsBar } from "../components/home/StatsBar";
import { HowItWorks } from "../components/home/HowItWorks";
import { ActivityFeed } from "../components/home/ActivityFeed";
import { Backtesting } from "../components/home/Backtesting";
import { DiscordPrompt } from "../components/home/DiscordPrompt";
import { PaperTradingDeploy } from "../components/home/PaperTradingDeploy";
import { Community } from "../components/home/Community";
import { FooterCTA } from "../components/home/FooterCTA";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background text-foreground font-sans">
      <Navbar />
      <main>
        <Hero />
        <StatsBar />
        <HowItWorks />
        <ActivityFeed />
        <Backtesting />
        <DiscordPrompt />
        <PaperTradingDeploy />
        <Community />
      </main>
      <FooterCTA />
    </div>
  );
}