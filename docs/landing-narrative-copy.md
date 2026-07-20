# Landing narrative — copy + build checklist

Story arc: **Talk (Discord) → Test (backtest) → Race (contest)**  
Tone: short lines, one job per section. No feature dumps.

---

## Copy deck

### Nav
| Slot | Copy |
|------|------|
| Links | Talk · Test · Race |
| CTA | Get Started → Discord (same as Hero primary) |

### Hero
**Frozen — do not change.** Keep current `Talk to Agents` / `Test Trading Ideas`, CTAs, and visual.
Scroll target `#landing-stats` is preserved as a hidden anchor inside Talk.

### 01 — Talk
| Slot | Copy |
|------|------|
| Label | 01 — Talk |
| H2 | Talk to agents on Discord |
| Body (1 line) | Describe a strategy. The bot runs it. |
| Steps | 1 Join the server · 2 Message the bot · 3 Get a backtest back |
| Primary CTA | Join Discord |
| Secondary | Bot commands → docs |
| Mock footer | Demo replay · real flow |

**Mock dialogue (keep short)**
- You: `Momentum on NVDA — buy RSI>55, sell <45`
- Bot: `Running backtest…`
- Bot: `+14.2% · Sharpe 1.84 → Open in Lab`

### 02 — Test
| Slot | Copy |
|------|------|
| Label | 02 — Test |
| H2 | Test your trading idea |
| Body (1 line) | Same prompt → historical run → metrics + decisions. |
| Proof strip | Window + universe from real run (e.g. defaults) |
| Metrics | Return · Sharpe · Max DD · vs Buy & Hold |
| Log label | Decision log |
| Primary CTA | Open run in Lab |
| Footnote (1 line) | Next: deploy to paper in the Lab |

### 03 — Race
| Slot | Copy |
|------|------|
| Label | 03 — Race |
| H2 | Race your agent in community contests |
| Body (1 line) | Same window. Same rules. Ranked vs baselines. |
| Rules (3 bullets max) | Fixed contest window · Shared market context · Published only if the model drove the run |
| Board meta | Contest: {start} → {end} |
| Primary CTA | View live leaderboard |
| Secondary CTA | Enter via Discord |

### Footer
| Slot | Copy |
|------|------|
| Line | Talk → Test → Race |
| CTAs | Join Discord · Open Leaderboard |

### Kill / avoid
- Fake stats (“Agents Online”, etc.)
- “From Idea to Execution” / Talk·Test·**Trade**
- “Live Network”, “tick-level”, “Season 4” fake names
- Long paragraphs under any H2

---

## Component checklist

### Phase A — IA + copy (structure)
| Action | File |
|--------|------|
| Reorder: Hero → Talk → Test → Race → Footer | `landing-page.tsx` |
| Nav anchors → Talk / Test / Race | `Navbar.tsx` |
| Hero: subline + chips; CTAs; scroll → `#talk` | `Hero.tsx` |
| Promote Discord section → `#talk` | rename/reuse `DiscordPrompt.tsx` → `Talk.tsx` |
| Merge backtest + short decision strip → `#test` | `Backtesting.tsx` → `Test.tsx` |
| Contest section → `#race`; kill fake rows | `Community.tsx` → `Race.tsx` |
| Footer: 3-beat line + CTAs | `FooterCTA.tsx` |
| **Delete** | `StatsBar.tsx`, `HowItWorks.tsx` |
| **Delete or fold** | `ActivityFeed.tsx` → 3–5 rows inside Test |
| **Demote** | `PaperTradingDeploy.tsx` → one footnote under Test |

### Phase B — proof (data)
| Action | Source |
|--------|--------|
| Race board | `GET /api/v1/leaderboard?period=contest` |
| Contest dates | response + `config/leaderboard.json` |
| Test equity/metrics | `defaults.json` run IDs / seed DB export → fixture |
| Test decision log | same run’s decisions (API or static fixture) |
| API fail | skeleton + “Unavailable” — never fake ranks |

### Phase C — Talk polish
| Action | Source |
|--------|--------|
| Hero visual → Discord-shaped | real bot transcript or labeled demo |
| Talk mock = same script as Hero (or shorter) | Discord export, scrubbed |
| Commands link | Discord bot docs / README |

### Phase D — tracking
| Event | Where |
|-------|-------|
| `hero_cta_discord_click` / `hero_cta_leaderboard_click` | Hero |
| `hero_chip_click` `{beat}` | Hero chips |
| `section_talk_view` / `section_test_view` / `section_race_view` | IO ≥50% |
| `talk_cta_discord_click` | Talk |
| `test_open_run_click` | Test |
| `race_leaderboard_loaded` / `race_leaderboard_error` | Race |
| `race_row_click` `{id}` | Race |
| `race_cta_lab_click` / `race_cta_discord_click` | Race |

### Done when
- [ ] Page order matches Talk → Test → Race
- [ ] No fake stats / fake leaderboard
- [ ] Each section ≤ 1 H2 + 1 line body + 1 visual + 1–2 CTAs
- [ ] Race loads real API (or honest empty state)
- [ ] Events wired on all CTAs + section views
