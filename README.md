
<div align="center">
  <img src="./dashboard/frontend/images/agentic_trading_lab_white.png" alt="Agentic Trading Lab" width="400">
</div>

<p align="center">
  <a href="https://agentic-trading-lab.vercel.app/">
    <img src="https://img.shields.io/badge/Live%20Demo-Visit%20App-0ea5e9?style=for-the-badge&logo=vercel&logoColor=white" alt="Live Demo">
  </a>
  <a href="https://discord.gg/9HnQ6XDG98">
    <img src="https://img.shields.io/badge/Discord-Join%20Community-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord">
  </a>
  <a href="https://finagent-orchestration.readthedocs.io/en/latest/">
    <img src="https://img.shields.io/badge/Docs-Read%20the%20Docs-22c55e?style=for-the-badge&logo=readthedocs&logoColor=white" alt="Docs">
  </a>
  <a href="#securefinai-contest-2026">
    <img src="https://img.shields.io/badge/Contest-2026-f97316?style=for-the-badge&logo=trophy&logoColor=white" alt="Contest 2026">
  </a>
</p>


**[Agentic Trading Lab](https://agentic-trading-lab.vercel.app/) is an open-source experimental playground for LLM-powered trading agents.**  
Turn trading ideas into traceable experiments: prototype agents, run backtests and paper-trading simulations, inspect reasoning and decision logs, benchmark against market baselines, and study how agents behave under realistic financial constraints.

<div align="center">
  <img src="./dashboard/frontend/images/snapshot_updated.png" alt="Website Snapshot" width="720">
</div>

## Outline

- [Overview](#overview)
- [Key Features](#key-features)
- [File Structure](#file-structure)
- [Architecture](#architecture)
- [Future Roadmap](#future-roadmap)
- [Citation](#citation)
- [License](#license)
- [Contributing](#contributing)

## Overview

Agentic Trading Lab is an interactive research and educational platform for exploring trading systems powered by large language models. Developed alongside a systematic survey of agentic trading research, it helps students, researchers, and developers explore how agents reason, trade, and perform in realistic market environments. Move beyond backtest returns by customizing agents, inspecting their decisions, evaluating risk, progressing from historical simulation to live-market paper trading, and comparing performance on standardized leaderboards.

## Key Features

- **Build and customize LLM-powered trading agents**  
 Prototype trading agents with configurable models, prompts, asset universes, and decision logic.
- **Interactive backtests**  
Test performance on historical market data and compare results against baselines.
- **Live-market paper trading**  
Test agents beyond historical replay by deploying to paper trading accounts that interact with real-time market data.
- **Inspect decision logs and reasoning traces**  
Review each BUY, SELL, and HOLD decision with timestamps, prices, portfolio state, and reasoning.
- **Evaluate risk and performance**  
Analyze cumulative return, Sharpe ratio, volatility, maximum drawdown, win/loss behavior, and benchmark comparisons.
- **Compete on agent leaderboards**  
Join agentic trading competitions where teams and users compete against others in a live-market paper trading setting.

## File Structure

The main folders are **backend**, **frontend**, and **orchestration**. The lab uses a **backtest → API → dashboard** pipeline.

```
AgenticTrading/
├── backend/              # FastAPI app, SQLite layer, paper trading, LLM validator
├── frontend/             # Dashboard (served by backend at http://localhost:8000)
├── scripts/              # CLI backtest (backtest_hourly_agent.py, etc.)
├── config/               # Default run IDs and date range (defaults.json)
├── data/                 # SQLite backtest results (backtest.db)
├── credentials/          # Local only — not in git (see alpaca.json.example)
├── backups/              # Database backups
├── docs/                 # Sphinx docs (see docs/README.md for local preview)
├── readthedocs.yml       # Read the Docs build config
└── orchestration/        # FinAgent multi-agent framework (separate subsystem)
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Backtest Engine (scripts/backtest_hourly_agent.py)          │
│ ├─ Fetch Alpaca hourly bars                                 │
│ ├─ Run agent + baseline logic                               │
│ ├─ Write 3 runs (agent, buy-and-hold, DJIA)                 │
│ └─ Store in data/backtest.db (SQLite)                        │
└────────────────┬────────────────────────────────────────────┘
                 │
┌────────────────▼─────────────────────────────────────────────┐
│ REST API (backend/app.py)                                    │
│ ├─ GET  /health                                              │
│ ├─ GET  /runs, /runs/{id}/equity, /compare                   │
│ ├─ POST /backtest/run, GET /backtest/status                  │
│ ├─ GET  /ticker                                              │
│ ├─ GET  /paper/account, /paper/positions, …                  │
│ └─ GET  /config/defaults                                     │
│     (LLM example: backend/llm_integration_example.py only)   │
└────────────────┬────────────────────────────────────────────┘
                 │
┌────────────────▼─────────────────────────────────────────────┐
│ Web Dashboard (frontend/)                                    │
│ ├─ index.html, app.js, styles.css                            │
│ └─ images/                                                   │
└──────────────────────────────────────────────────────────────┘
```

## Future Roadmap

- Leaderboard backed by real multi-agent runs (replace mock data)
- Sentiment analysis (Reddit, news APIs)
- Monte Carlo simulation baselines
- Production-ready Docker image (frontend + data included)

## Citation

This repository includes the FinAgent Orchestration Framework under `orchestration/`, originally developed by Jifeng Li et al. at Open Finance Lab as part of the work on financial agent orchestration. The orchestration framework provides multi-agent architecture, memory systems, and DAG-based planning components. See `orchestration/README.md` for details.

If you use the orchestration framework in research, please cite:

```bibtex
@inproceedings{orchestration_finagents_2025,
   title     = {Orchestration Framework for Financial Agents: From Algorithmic Trading to Agentic Trading},
   author    = {Jifeng Li and Arnav Grover and Abraham Alpuerto and Yupeng Cao and Xiao-Yang Liu},
   booktitle = {NeurIPS 2025 Workshop on Generative AI in Finance},
   year      = {2025},
}

```

Plain-text citation:

Jifeng Li, Arnav Grover, Abraham Alpuerto, Yupeng Cao, and Xiao-Yang Liu. *Orchestration Framework for Financial Agents: From Algorithmic Trading to Agentic Trading*. NeurIPS 2025 Workshop on Generative AI in Finance, 2025.

Documentation: [finagent-orchestration.readthedocs.io](https://finagent-orchestration.readthedocs.io) (Agentic Trading Lab + Orchestration Framework). Local preview: `docs/README.md`

## License

OpenMDW-1.0 — See [LICENSE](LICENSE) (Copyright Jifeng Li @ SecureFinAI Lab)

## Contributing

Pull requests and issues welcome!

---

Built with Alpaca API, FastAPI, Chart.js, and SQLite