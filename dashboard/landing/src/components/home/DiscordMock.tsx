import type { ReactNode } from "react";
import { STORY_PROMPT, STORY_SPECS } from "./storyline";

const DISCORD_URL = "https://discord.gg/9HnQ6XDG98";

type Msg = {
  id: string;
  author: "you" | "agent";
  name: string;
  time: string;
  body: ReactNode;
};

const MESSAGES: Msg[] = [
  {
    id: "1",
    author: "you",
    name: "you",
    time: "Today at 2:14 PM",
    body: STORY_PROMPT,
  },
  {
    id: "2",
    author: "agent",
    name: "ATL Agent",
    time: "Today at 2:14 PM",
    body: "Got it — when Berkshire files a change, copy those buys and sells?",
  },
  {
    id: "3",
    author: "you",
    name: "you",
    time: "Today at 2:15 PM",
    body: "Yes. Use the last two years.",
  },
  {
    id: "4",
    author: "agent",
    name: "ATL Agent",
    time: "Today at 2:15 PM",
    body: (
      <>
        Copy-trade rules set · 6 tickers from recent 13Fs.
        <br />
        Want me to backtest that first?
      </>
    ),
  },
  {
    id: "5",
    author: "you",
    name: "you",
    time: "Today at 2:15 PM",
    body: "Yeah, run it.",
  },
  {
    id: "6",
    author: "agent",
    name: "ATL Agent",
    time: "Today at 2:16 PM",
    body: (
      <>
        <div>Running backtest…</div>
        <div className="discord-embed">
          <div className="discord-embed-bar" />
          <div className="discord-embed-body">
            <div className="discord-embed-title">Backtest complete</div>
            <div className="discord-embed-fields">
              <span>
                Return <strong className="text-positive">{STORY_SPECS.returnPct}</strong>
              </span>
              <span>
                Sharpe <strong>{STORY_SPECS.sharpe}</strong>
              </span>
            </div>
            <a href="#test" className="discord-embed-link">
              See full result ↓
            </a>
          </div>
        </div>
      </>
    ),
  },
];

function Avatar({ author }: { author: "you" | "agent" }) {
  if (author === "agent") {
    return (
      <div className="discord-avatar discord-avatar--agent" aria-hidden="true">
        A
      </div>
    );
  }
  return (
    <div className="discord-avatar discord-avatar--you" aria-hidden="true">
      Y
    </div>
  );
}

/** Marketing mock of the Discord channel where users talk to the agent. */
export function DiscordMock() {
  return (
    <div className="discord-mock" aria-label="Discord demo: talking to the agent">
      {/* Server rail */}
      <aside className="discord-servers" aria-hidden="true">
        <div className="discord-server-icon discord-server-icon--home">ATL</div>
        <div className="discord-server-divider" />
        <div className="discord-server-icon discord-server-icon--active">$</div>
        <div className="discord-server-icon">+</div>
      </aside>

      {/* Channel list */}
      <aside className="discord-channels" aria-hidden="true">
        <div className="discord-channels-header">Agentic Trading Lab</div>
        <div className="discord-channel-group">Text Channels</div>
        <div className="discord-channel-item">
          <span className="discord-hash">#</span> general
        </div>
        <div className="discord-channel-item discord-channel-item--active">
          <span className="discord-hash">#</span> agent-trading-lab
        </div>
        <div className="discord-channel-item">
          <span className="discord-hash">#</span> announcements
        </div>
      </aside>

      {/* Chat */}
      <div className="discord-main">
        <header className="discord-chat-header">
          <span className="discord-hash discord-hash--lg">#</span>
          <span className="discord-channel-name">agent-trading-lab</span>
          <span className="discord-chat-header-sep" />
          <span className="discord-chat-header-topic">Talk to agents · backtest ideas</span>
        </header>

        <div className="discord-messages">
          {MESSAGES.map((msg) => (
            <div key={msg.id} className="discord-msg">
              <Avatar author={msg.author} />
              <div className="discord-msg-body">
                <div className="discord-msg-meta">
                  <span
                    className={
                      msg.author === "agent" ? "discord-username discord-username--agent" : "discord-username"
                    }
                  >
                    {msg.name}
                  </span>
                  {msg.author === "agent" ? (
                    <span className="discord-bot-badge" title="Agent">
                      APP
                    </span>
                  ) : null}
                  <span className="discord-timestamp">{msg.time}</span>
                </div>
                <div className="discord-msg-text">{msg.body}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="discord-composer" aria-hidden="true">
          <div className="discord-composer-box">
            Message <span className="discord-composer-channel">#agent-trading-lab</span>
          </div>
        </div>

        <a
          href={DISCORD_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="discord-mock-cta"
        >
          Open in Discord →
        </a>
      </div>
    </div>
  );
}
