/**
 * Agentic Trading Lab Frontend
 * Supports: Backtest | Paper | Contest modes
 */

// Auto-detect API base URL (localhost for dev, production URL for deployed)
const API_BASE = window.location.hostname === 'localhost' 
  ? 'http://localhost:8000'
  : 'https://agentictrading.onrender.com';  // Render backend URL

let chartInstance = null;
let currentMode = "backtest";

// Contest data structure (you'll populate this from your data)
const contestData = {
    teams: [
        {
            teamId: "team_001",
            teamName: "DeepSeek Team",
            market: "stock",
            cr: 8.45,
            sr: 1.23,
            md: -12.34,
            dv: 1.85,
            av: 14.23,
            finalEquity: 108450,
            equityCurve: []
        },
        {
            teamId: "team_002",
            teamName: "Claude Team",
            market: "stock",
            cr: 6.32,
            sr: 0.98,
            md: -15.67,
            dv: 2.12,
            av: 16.45,
            finalEquity: 106320,
            equityCurve: []
        },
        {
            teamId: "team_003",
            teamName: "Anthropic Trading",
            market: "crypto",
            cr: 12.78,
            sr: 1.45,
            md: -10.23,
            dv: 2.34,
            av: 18.12,
            finalEquity: 112780,
            equityCurve: []
        }
    ]
};

/**
 * Initialize on page load
 */
document.addEventListener('DOMContentLoaded', async () => {
    console.log('Dashboard initializing...');
    
    // Initialize theme from localStorage
    initializeTheme();
    
    // Setup theme toggle
    const themeToggle = document.getElementById('themeToggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', toggleTheme);
    }
    
    // Setup mode toggle
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            switchMode(e.target.dataset.mode);
        });
    });
    
    // Setup backtest run button
    const runBacktestBtn = document.getElementById('runBacktestBtn');
    if (runBacktestBtn) {
        runBacktestBtn.addEventListener('click', async () => {
            await triggerBacktest();
        });
    }

    // Load market ticker data
    await loadTickerData();

    // Load initial data
    await loadData();
    
    // Refresh ticker every 30 seconds
    setInterval(loadTickerData, 30000);
});

/**
 * Initialize theme from localStorage or default to light
 */
function initializeTheme() {
    const savedTheme = localStorage.getItem('theme') || 'light';
    applyTheme(savedTheme);
}

/**
 * Toggle between light and dark themes
 */
function toggleTheme() {
    const currentTheme = document.body.classList.contains('dark-theme') ? 'dark' : 'light';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    applyTheme(newTheme);
}

/**
 * Apply theme to document
 */
function applyTheme(theme) {
    if (theme === 'dark') {
        document.body.classList.add('dark-theme');
        const icon = document.querySelector('.theme-icon');
        if (icon) icon.textContent = '🌙';
    } else {
        document.body.classList.remove('dark-theme');
        const icon = document.querySelector('.theme-icon');
        if (icon) icon.textContent = '☀️';
    }
    localStorage.setItem('theme', theme);
    console.log(`Theme switched to: ${theme}`);
}

/**
 * Load live market ticker data from API
 */
async function loadTickerData() {
    try {
        console.log('📊 Fetching live ticker data...');
        
        const response = await fetch(`${API_BASE}/ticker?symbols=AAPL,NVDA,MSFT,BTC`);
        if (!response.ok) {
            console.error('❌ Failed to fetch ticker:', response.status);
            return;
        }
        
        const data = await response.json();
        
        if (data.success && data.quotes && data.quotes.length > 0) {
            console.log('✅ Ticker data received:', data.quotes.length, 'symbols');
            renderTicker(data.quotes);
        } else {
            console.warn('⚠️ No quote data returned:', data);
            // Show fallback message if no data
            const tickerBar = document.getElementById('tickerBar');
            if (tickerBar && tickerBar.innerHTML.includes('Loading')) {
                tickerBar.innerHTML = '<div class="ticker-placeholder">Market data unavailable</div>';
            }
        }
    } catch (error) {
        console.error('❌ Error loading ticker:', error);
        const tickerBar = document.getElementById('tickerBar');
        if (tickerBar) {
            tickerBar.innerHTML = '<div class="ticker-placeholder">Error loading market data</div>';
        }
    }
}

/**
 * Render ticker items
 */
function renderTicker(quotes) {
    const tickerBar = document.getElementById('tickerBar');
    
    if (!tickerBar) return;
    
    // Sort quotes to match order: AAPL, NVDA, MSFT, BTC
    const order = ['AAPL', 'NVDA', 'MSFT', 'BTC'];
    quotes.sort((a, b) => order.indexOf(a.symbol) - order.indexOf(b.symbol));
    
    // Generate ticker items HTML
    const html = quotes.map(quote => {
        const changePercent = quote.changePercent || 0;
        const changeClass = changePercent >= 0 ? 'positive' : 'negative';
        const changeSign = changePercent >= 0 ? '+' : '';
        
        return `
            <div class="ticker-item">
                <span class="symbol">${quote.symbol}</span>
                <span class="price">${quote.price}</span>
                <span class="change ${changeClass}">${changeSign}${changePercent}%</span>
            </div>
        `;
    }).join('');
    
    tickerBar.innerHTML = html;
    console.log('Ticker rendered:', quotes.length, 'symbols');
}

/**
 * Switch between modes
 */
function switchMode(mode) {
    console.log('Switching to mode:', mode);
    currentMode = mode;
    
    // Update active button
    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
    document.querySelector(`[data-mode="${mode}"]`).classList.add('active');
    
    // Update UI based on mode
    updateUI();
    
    // Load mode-specific data
    if (mode === "backtest") {
        loadData();
    } else if (mode === "paper") {
        loadPaperTradingData();
    } else if (mode === "contest") {
        loadContestData();
    }
}

/**
 * Update UI elements based on current mode
 */
function updateUI() {
    const equityTitle = document.getElementById('equityTitle');
    const equitySubtitle = document.getElementById('equitySubtitle');
    const chartSubtitle = document.getElementById('chartSubtitle');
    const decisionsTitle = document.getElementById('decisionsTitle');
    const leaderboardTitle = document.getElementById('leaderboardTitle');
    const sortOptions = document.getElementById('sortOptions');
    const contestMetricsTable = document.getElementById('contestMetricsTable');
    const decisionsGrid = document.getElementById('decisionsGrid');
    const timeframeToggle = document.getElementById('timeframeToggle');
    
    // Paper trading sections
    const paperAccountSection = document.getElementById('paperAccountSection');
    const paperPositionsSection = document.getElementById('paperPositionsSection');
    const paperTradesSection = document.getElementById('paperTradesSection');
    const leaderboardSection = document.getElementById('leaderboardSection');
    
    if (currentMode === "backtest") {
        equityTitle.textContent = "Agent Equity Curves";
        equitySubtitle.textContent = "Comparing agent performance";
        chartSubtitle.textContent = "Total Account Value";
        decisionsTitle.textContent = "Model Decisions";
        leaderboardTitle.textContent = "Arena Leaderboard";
        sortOptions.textContent = "Sort by: PnL | Sharpe | MDD";
        contestMetricsTable.style.display = "none";
        decisionsGrid.style.display = "grid";
        timeframeToggle.style.display = "flex";
        
        // Hide paper trading sections
        paperAccountSection.style.display = "none";
        paperPositionsSection.style.display = "none";
        paperTradesSection.style.display = "none";
        leaderboardSection.style.display = "block";
        
    } else if (currentMode === "paper") {
        equityTitle.textContent = "Paper Trading Equity";
        equitySubtitle.textContent = "Real-time account performance";
        chartSubtitle.textContent = "Live Account Value";
        decisionsTitle.textContent = "Live Model Decisions";
        leaderboardTitle.textContent = "Paper Trading Leaders";
        sortOptions.textContent = "Sort by: Return | Sharpe";
        contestMetricsTable.style.display = "none";
        decisionsGrid.style.display = "grid";
        timeframeToggle.style.display = "flex";
        
        // Show paper trading sections
        paperAccountSection.style.display = "block";
        paperPositionsSection.style.display = "block";
        paperTradesSection.style.display = "block";
        leaderboardSection.style.display = "block";
        
    } else if (currentMode === "contest") {
        equityTitle.textContent = "🏆 Contest Teams (April 20 - May 1)";
        equitySubtitle.textContent = "Task V: Agentic Trading Championship";
        chartSubtitle.textContent = "Team Equity Curves";
        decisionsTitle.textContent = "Participating Teams";
        leaderboardTitle.textContent = "Contest Standings";
        sortOptions.textContent = "Sort by: CR | SR | MD";
        contestMetricsTable.style.display = "block";
        decisionsGrid.style.display = "none";  // Hide model decisions in contest mode
        timeframeToggle.style.display = "none"; // Hide timeframe toggle
        
        // Hide paper trading sections
        paperAccountSection.style.display = "none";
        paperPositionsSection.style.display = "none";
        paperTradesSection.style.display = "none";
        leaderboardSection.style.display = "block";
    }
}

/**
 * Trigger backtest run on backend (asynchronous)
 */
async function triggerBacktest() {
    const btn = document.getElementById('runBacktestBtn');
    const originalText = btn.textContent;
    
    // Get dates from input fields
    const startDateInput = document.getElementById('backtestStartDate');
    const endDateInput = document.getElementById('backtestEndDate');
    
    const startDate = startDateInput.value;
    const endDate = endDateInput.value;
    
    // Validate dates
    if (!startDate || !endDate) {
        alert('⚠️ Please select both start and end dates');
        return;
    }
    
    if (new Date(startDate) >= new Date(endDate)) {
        alert('⚠️ Start date must be before end date');
        return;
    }
    
    try {
        btn.textContent = '⏳ Starting backtest...';
        btn.disabled = true;
        
        console.log(`🚀 Triggering backtest: ${startDate} to ${endDate}...`);
        
        // Trigger backtest (non-blocking)
        const response = await fetch(`${API_BASE}/backtest/run?start_date=${startDate}&end_date=${endDate}`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            console.log('✅ Backtest started in background');
            btn.textContent = '⏳ Running... (checking status)';
            
            // Poll for completion
            await pollBacktestStatus(btn, originalText);
        } else {
            console.error('❌ Failed to start backtest:', data.error);
            alert(`❌ Failed to start backtest:\n\n${data.error}`);
            btn.textContent = originalText;
            btn.disabled = false;
        }
    } catch (error) {
        console.error('❌ Error triggering backtest:', error);
        alert(`❌ Error: ${error.message}`);
        btn.textContent = originalText;
        btn.disabled = false;
    }
}

/**
 * Poll backtest status until completion
 */
async function pollBacktestStatus(btn, originalText) {
    const maxAttempts = 60;  // 5 minutes (polling every 5 seconds)
    let attempts = 0;
    
    while (attempts < maxAttempts) {
        try {
            const response = await fetch(`${API_BASE}/backtest/status`);
            const status = await response.json();
            
            if (!status.running) {
                // Backtest finished
                if (status.error) {
                    console.error('❌ Backtest error:', status.error);
                    alert(`❌ Backtest failed:\n\n${status.error}`);
                    btn.textContent = originalText;
                    btn.disabled = false;
                } else if (status.success) {
                    console.log('✅ Backtest completed!', status.runs_count, 'runs');
                    
                    // Show success message
                    btn.textContent = '✅ Completed! Updating chart...';
                    
                    // Wait a moment for DB to sync, then reload
                    await new Promise(resolve => setTimeout(resolve, 1000));
                    
                    // Destroy old chart and fetch fresh data
                    if (chartInstance) {
                        chartInstance.destroy();
                        chartInstance = null;
                    }
                    
                    // Reload data from API
                    console.log('🔄 Fetching fresh backtest data...');
                    await loadData();
                    
                    // Show success and reset button
                    btn.textContent = '✅ Chart updated!';
                    setTimeout(() => {
                        btn.textContent = originalText;
                        btn.disabled = false;
                    }, 2000);
                }
                return;
            }
            
            // Still running - update button and wait
            attempts++;
            const dots = '.'.repeat((attempts % 3) + 1);
            btn.textContent = `⏳ Running${dots} (${Math.floor(attempts * 5 / 60)}m)`;
            
            // Wait 5 seconds before next poll
            await new Promise(resolve => setTimeout(resolve, 5000));
        } catch (error) {
            console.error('Error checking backtest status:', error);
            await new Promise(resolve => setTimeout(resolve, 5000));
            attempts++;
        }
    }
    
    // Timeout
    alert('⏱️ Backtest is taking too long (>5 minutes). It may still be running in the background.\n\nTry reloading the page in a moment.');
    btn.textContent = originalText;
    btn.disabled = false;
}

/**
 * Load backtest data
 */
async function loadData() {
    try {
        console.log('Fetching backtest results...');
        
        const response = await fetch(`${API_BASE}/api/backtest/compare/latest`);
        if (!response.ok) {
            console.error('❌ Failed to fetch backtest data:', response.status);
            return;
        }
        
        const comparison = await response.json();
        console.log('✅ Loaded backtest runs:', comparison.runs.length);
        
        if (comparison.runs && comparison.runs.length > 0) {
            // Plot the backtest equity curves
            plotBacktestComparison(comparison.runs);
            // Update leaderboard with backtest results
            updateBacktestLeaderboard(comparison);
        } else {
            console.warn('⚠️ No backtest data found');
        }
    } catch (error) {
        console.error('❌ Error loading backtest data:', error);
    }
}

/**
 * Plot backtest comparison results
 */
function plotBacktestComparison(runs) {
    // runs array has: run_id, agent_name, data (equity points), metrics
    // Filter out old Clawdy agent (keep only current agents)
    const filteredRuns = runs.filter(run => run.agent_name !== "Clawdy");
    // renderChart already normalizes, so just call it
    renderChart(filteredRuns);
}

/**
 * Update leaderboard with backtest results
 */
function updateBacktestLeaderboard(comparison) {
    const leaderboard = document.getElementById('leaderboard');
    if (!leaderboard) return;
    
    // Filter out old Clawdy agent and sort by total return
    const filtered = comparison.runs.filter(run => run.agent_name !== "Clawdy");
    const sorted = filtered.sort((a, b) => 
        (b.metrics.total_return || 0) - (a.metrics.total_return || 0)
    );
    
    const leaderboardHTML = sorted.map((run, index) => `
        <div class="leaderboard-item">
            <div class="rank">${index + 1}</div>
            <div class="agent-name">${run.agent_name}</div>
            <div class="metric">
                <span class="value">${(run.metrics.total_return || 0).toFixed(2)}%</span>
                <span class="label">Return</span>
            </div>
            <div class="metric">
                <span class="value">${(run.metrics.sharpe_ratio || 0).toFixed(2)}</span>
                <span class="label">Sharpe</span>
            </div>
            <div class="metric">
                <span class="value">${(run.metrics.max_drawdown || 0).toFixed(2)}%</span>
                <span class="label">Max DD</span>
            </div>
            <div class="metric">
                <span class="value">${run.metrics.num_trades || 0}</span>
                <span class="label">Trades</span>
            </div>
        </div>
    `).join('');
    
    leaderboard.innerHTML = leaderboardHTML;
}

/**
 * Load paper trading data (optimized with localStorage cache)
 * Charts load first, baselines load in background (non-blocking)
 */
async function loadPaperTradingData() {
    console.log('🚀 Loading paper trading data (optimized)...');
    
    const startTime = performance.now();
    
    try {
        // Fetch 3 critical items in parallel (account, positions, trades)
        const [accountResponse, positionsResponse, tradesResponse, historyResponse] = await Promise.all([
            fetch(`${API_BASE}/paper/account`),
            fetch(`${API_BASE}/paper/positions`),
            fetch(`${API_BASE}/paper/trades?limit=20`),
            fetch(`${API_BASE}/paper/portfolio-history?timeframe=1D`)
        ]);
        
        // Process account
        if (accountResponse.ok) {
            const accountData = await accountResponse.json();
            if (accountData.success) {
                updatePaperAccountDisplay(accountData.account);
                localStorage.setItem('paper_account', JSON.stringify(accountData.account));
            }
        }
        
        // Process positions
        if (positionsResponse.ok) {
            const positionsData = await positionsResponse.json();
            if (positionsData.success) {
                updatePaperPositionsDisplay(positionsData.positions);
                localStorage.setItem('paper_positions', JSON.stringify(positionsData.positions));
            }
        }
        
        // Process trades
        if (tradesResponse.ok) {
            const tradesData = await tradesResponse.json();
            if (tradesData.success) {
                updatePaperTradesDisplay(tradesData.trades);
                localStorage.setItem('paper_trades', JSON.stringify(tradesData.trades));
            }
        }
        
        // Process portfolio history and PLOT CHART IMMEDIATELY
        let equityCurve = [];
        if (historyResponse.ok) {
            const historyData = await historyResponse.json();
            if (historyData.success && historyData.equity_curve.length > 0) {
                equityCurve = historyData.equity_curve;
                localStorage.setItem('paper_equity_curve', JSON.stringify(equityCurve));
                
                // Determine date range from equity curve
                const startDate = equityCurve[0]?.timestamp;
                const endDate = equityCurve[equityCurve.length - 1]?.timestamp;
                const days = Math.ceil(
                    (new Date(endDate) - new Date(startDate)) / (1000 * 60 * 60 * 24)
                );
                
                console.log(`📊 Equity curve: ${days} days (${startDate} to ${endDate})`);
                
                // Plot with just your data (no baselines yet)
                plotPaperTradingCurve(equityCurve, {});
                console.log('✅ Chart plotted (your data only)');
            }
        }
        
        const elapsed = (performance.now() - startTime).toFixed(0);
        console.log(`✅ Critical data loaded in ${elapsed}ms`);
        
        // NOW fetch baselines in background (non-blocking)
        // They'll update the chart when ready
        console.log('📊 Fetching baselines in background...');
        fetch(`${API_BASE}/paper/baselines`)
            .then(r => r.json())
            .then(baselinesData => {
                if (baselinesData.success) {
                    const baselines = baselinesData.baselines || {};
                    console.log('✅ Baselines loaded, updating chart...');
                    
                    // Trim baselines to match equity curve date range
                    // Compare by DATE only (ignore time) to handle different timestamp formats
                    if (equityCurve.length > 0) {
                        // Extract just the date part (YYYY-MM-DD)
                        const getDate = (ts) => ts.split('T')[0];
                        
                        const firstDate = getDate(equityCurve[0].timestamp);
                        const lastDate = getDate(equityCurve[equityCurve.length - 1].timestamp);
                        
                        console.log(`📅 Equity range: ${firstDate} to ${lastDate}`);
                        
                        const trimmed = {};
                        for (const [key, curve] of Object.entries(baselines)) {
                            const filtered = curve.filter(p => {
                                const pDate = getDate(p.timestamp);
                                return pDate >= firstDate && pDate <= lastDate;
                            });
                            
                            if (filtered.length > 0) {
                                trimmed[key] = filtered;
                                console.log(`  ${key}: ${filtered.length} points (${getDate(filtered[0].timestamp)} to ${getDate(filtered[filtered.length-1].timestamp)})`);
                            }
                        }
                        
                        // Re-plot with trimmed baselines
                        if (Object.keys(trimmed).length > 0) {
                            plotPaperTradingCurve(equityCurve, trimmed);
                            localStorage.setItem('paper_baselines', JSON.stringify(trimmed));
                            console.log('📊 Chart updated with baselines (date-aligned)');
                        } else {
                            console.warn('⚠️ No baselines matched date range');
                            plotPaperTradingCurve(equityCurve, {});
                        }
                    }
                } else {
                    console.warn('⚠️ Baselines not available:', baselinesData.error);
                }
            })
            .catch(err => console.warn('⚠️ Baselines fetch failed (this is OK):', err.message));
        
        // Load leaderboard (non-critical, background)
        fetch(`${API_BASE}/runs?mode=paper`)
            .then(r => r.json())
            .then(runs => {
                if (Array.isArray(runs) && runs.length > 0) {
                    updatePaperLeaderboard(runs);
                }
            })
            .catch(err => console.warn('Leaderboard delayed:', err.message));
        
    } catch (error) {
        console.error('❌ Error loading paper data:', error);
        loadPaperTradingFromCache();
    }
}

/**
 * Load paper trading data from localStorage cache (instant)
 */
function loadPaperTradingFromCache() {
    console.log('📦 Loading paper trading data from cache...');
    
    const account = JSON.parse(localStorage.getItem('paper_account') || 'null');
    const positions = JSON.parse(localStorage.getItem('paper_positions') || 'null');
    const trades = JSON.parse(localStorage.getItem('paper_trades') || 'null');
    const equityCurve = JSON.parse(localStorage.getItem('paper_equity_curve') || 'null');
    const baselines = JSON.parse(localStorage.getItem('paper_baselines') || 'null');
    
    if (account) updatePaperAccountDisplay(account);
    if (positions) updatePaperPositionsDisplay(positions);
    if (trades) updatePaperTradesDisplay(trades);
    if (equityCurve) plotPaperTradingCurve(equityCurve, baselines || {});
    
    console.log('✅ Cache loaded');
}

/**
 * Update account display with live data
 */
function updatePaperAccountDisplay(account) {
    const accountInfo = document.getElementById('paperAccountInfo');
    if (!accountInfo) {
        // Create if doesn't exist
        return;
    }
    
    const html = `
        <div class="account-metric">
            <div class="metric-value">$${account.equity.toLocaleString(undefined, {maximumFractionDigits: 2})}</div>
            <div class="metric-label">Account Equity</div>
        </div>
        <div class="account-metric">
            <div class="metric-value">$${account.cash.toLocaleString(undefined, {maximumFractionDigits: 2})}</div>
            <div class="metric-label">Cash Available</div>
        </div>
        <div class="account-metric">
            <div class="metric-value">$${account.buying_power.toLocaleString(undefined, {maximumFractionDigits: 2})}</div>
            <div class="metric-label">Buying Power</div>
        </div>
    `;
    
    accountInfo.innerHTML = html;
    console.log('✅ Paper account display updated');
}

/**
 * Update positions display
 */
function updatePaperPositionsDisplay(positions) {
    const positionsContainer = document.getElementById('paperPositions');
    if (!positionsContainer) return;
    
    if (positions.length === 0) {
        positionsContainer.innerHTML = '<div class="no-positions">No open positions</div>';
        return;
    }
    
    const html = positions.map(pos => {
        const gainLoss = pos.unrealized_pl >= 0 ? 'gain' : 'loss';
        const icon = pos.unrealized_pl >= 0 ? '📈' : '📉';
        
        return `
            <div class="position-item">
                <div class="position-symbol">${pos.symbol}</div>
                <div class="position-qty">${pos.qty} @ $${pos.avg_fill_price.toFixed(2)}</div>
                <div class="position-value">$${pos.market_value.toLocaleString(undefined, {maximumFractionDigits: 2})}</div>
                <div class="position-pl ${gainLoss}">
                    ${icon} $${pos.unrealized_pl.toFixed(2)} (${(pos.unrealized_plpc * 100).toFixed(2)}%)
                </div>
            </div>
        `;
    }).join('');
    
    positionsContainer.innerHTML = html;
    console.log('✅ Positions updated:', positions.length, 'open');
}

/**
 * Update trades display
 */
function updatePaperTradesDisplay(trades) {
    const tradesContainer = document.getElementById('paperTrades');
    if (!tradesContainer) return;
    
    if (trades.length === 0) {
        tradesContainer.innerHTML = '<div class="no-trades">No recent trades</div>';
        return;
    }
    
    const html = trades.slice(0, 10).map(trade => {
        const buySell = trade.side === 'buy' ? '🟢 BUY' : '🔴 SELL';
        return `
            <div class="trade-item">
                <div class="trade-symbol">${trade.symbol}</div>
                <div class="trade-action">${buySell}</div>
                <div class="trade-qty">${trade.qty}</div>
                <div class="trade-price">@ $${trade.price.toFixed(2)}</div>
                <div class="trade-time">${new Date(trade.timestamp).toLocaleTimeString()}</div>
            </div>
        `;
    }).join('');
    
    tradesContainer.innerHTML = html;
    console.log('✅ Trades updated:', trades.length);
}

/**
 * Normalize equity curve to start at $100,000
 * This makes different curves directly comparable
 */
function normalizeEquityCurve(curve) {
    if (!curve || curve.length === 0) return curve;
    
    const initialEquity = curve[0].equity;
    const ratio = 100000 / initialEquity;
    
    return curve.map(point => ({
        ...point,
        equity: point.equity * ratio
    }));
}

/**
 * Break chart data across market gaps (don't connect lines across market closed times)
 * Inserts null values when gap > 4 hours between consecutive timestamps
 */
function insertMarketGaps(data) {
    if (!data || data.length < 2) {
        console.log('insertMarketGaps: No data or too short', data?.length);
        return data;
    }
    
    const result = [];
    for (let i = 0; i < data.length; i++) {
        result.push(data[i]);
        
        // Check gap to next point
        if (i < data.length - 1) {
            const current = new Date(data[i].x);
            const next = new Date(data[i + 1].x);
            const gapMs = next.getTime() - current.getTime();
            const gapHours = gapMs / (1000 * 60 * 60);
            
            // If gap > 4 hours, insert null to break the line
            if (gapHours > 4) {
                console.log(`Gap detected: ${gapHours.toFixed(1)} hours between ${current.toISOString()} and ${next.toISOString()}`);
                result.push(null);
            }
        }
    }
    
    console.log(`insertMarketGaps: ${data.length} points → ${result.length} points (added ${result.length - data.length} gaps)`);
    return result;
}

/**
 * Plot paper trading equity curve with baselines (all normalized to $100k start)
 */
function plotPaperTradingCurve(equityCurve, baselines = {}) {
    const ctx = document.getElementById('equityChart');
    if (!ctx) return;
    
    // Convert timestamps to continuous trading hour indices
    let allTimestamps = [];
    if (equityCurve && equityCurve.length > 0) {
        equityCurve.forEach(point => allTimestamps.push(point.timestamp));
    }
    if (baselines.djia) {
        baselines.djia.forEach(point => allTimestamps.push(point.timestamp));
    }
    if (baselines.buy_and_hold) {
        baselines.buy_and_hold.forEach(point => allTimestamps.push(point.timestamp));
    }
    allTimestamps = [...new Set(allTimestamps)].sort();
    
    const timestampToIndex = {};
    allTimestamps.forEach((ts, idx) => {
        timestampToIndex[ts] = idx;
    });
    
    // Store data for axis labels
    window.paperChartDataForLabels = allTimestamps.map(ts => ({timestamp: ts}));
    
    const datasets = [];
    
    // Main account equity (if available)
    if (equityCurve && equityCurve.length > 0) {
        const normalized = normalizeEquityCurve(equityCurve);
        const data = normalized.map(point => ({
            x: timestampToIndex[point.timestamp],
            y: point.equity,
            timestamp: point.timestamp
        }));
        datasets.push({
            label: 'Your Account',
            data: data,
            borderColor: '#27ae60',
            backgroundColor: '#27ae60' + '20',
            borderWidth: 3,
            tension: 0.4,
            fill: false,
            pointRadius: 0,
            pointHoverRadius: 6
        });
    }
    
    // DJIA baseline (normalized)
    if (baselines.djia && baselines.djia.length > 0) {
        const normalized = normalizeEquityCurve(baselines.djia);
        const data = normalized.map(point => ({
            x: timestampToIndex[point.timestamp],
            y: point.equity,
            timestamp: point.timestamp
        }));
        datasets.push({
            label: 'DJIA (Benchmark)',
            data: data,
            borderColor: '#e67e22',
            backgroundColor: '#e67e22' + '20',
            borderWidth: 2,
            borderDash: [5, 5],
            tension: 0.4,
            fill: false,
            pointRadius: 0,
            pointHoverRadius: 6
        });
    }
    
    // Buy-and-Hold baseline (normalized)
    if (baselines.buy_and_hold && baselines.buy_and_hold.length > 0) {
        const normalized = normalizeEquityCurve(baselines.buy_and_hold);
        const data = normalized.map(point => ({
            x: timestampToIndex[point.timestamp],
            y: point.equity,
            timestamp: point.timestamp
        }));
        datasets.push({
            label: 'buy-and-hold',
            data: data,
            borderColor: '#4a90e2',
            backgroundColor: '#4a90e2' + '20',
            borderWidth: 2,
            borderDash: [10, 5],
            tension: 0.4,
            fill: false,
            pointRadius: 0,
            pointHoverRadius: 6
        });
    }
    
    // If no data at all, show empty state
    if (datasets.length === 0) {
        console.warn('No equity curve or baseline data');
        return;
    }
    
    if (chartInstance) {
        chartInstance.destroy();
    }
    
    chartInstance = new Chart(ctx, {
        type: 'line',
        data: { datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        usePointStyle: true,
                        padding: 15,
                        font: { size: 13, weight: '600' }
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(0,0,0,0.8)',
                    padding: 12,
                    titleFont: { size: 13, weight: '600' },
                    bodyFont: { size: 12 },
                    callbacks: {
                        label: function(context) {
                            return context.dataset.label + ': $' + context.parsed.y.toFixed(2);
                        },
                        afterLabel: function(context) {
                            // Show actual timestamp in tooltip
                            if (context.raw && context.raw.timestamp) {
                                const date = new Date(context.raw.timestamp);
                                return 'Time: ' + date.toLocaleString();
                            }
                            return '';
                        }
                    }
                }
            },
            scales: {
                x: {
                    type: 'linear',
                    ticks: {
                        callback: function(value) {
                            // Get the actual date from the data
                            if (window.paperChartDataForLabels && window.paperChartDataForLabels[Math.floor(value)]) {
                                const point = window.paperChartDataForLabels[Math.floor(value)];
                                const date = new Date(point.timestamp);
                                return date.toLocaleDateString('en-US', { month: 'short', day: '2-digit' });
                            }
                            return '';
                        },
                        maxTicksLimit: 10
                    }
                },
                y: {
                    ticks: {
                        callback: function(value) {
                            return '$' + value.toFixed(0);
                        }
                    }
                }
            }
        }
    });
    
    console.log('✅ Paper trading chart rendered with', datasets.length, 'series');
}

/**
 * Update leaderboard with paper trading runs
 */
function updatePaperLeaderboard(runs) {
    const leaderboard = document.getElementById('leaderboard');
    if (!leaderboard) return;
    
    // Sort by return
    const sorted = runs.sort((a, b) => 
        (b.total_return || 0) - (a.total_return || 0)
    );
    
    const leaderboardHTML = sorted.map((run, index) => `
        <div class="leaderboard-item">
            <div class="rank">${index + 1}</div>
            <div class="agent-name">${run.agent_name}</div>
            <div class="metric">
                <span class="value">${(run.total_return || 0).toFixed(2)}%</span>
                <span class="label">Return</span>
            </div>
            <div class="metric">
                <span class="value">${(run.sharpe_ratio || 0).toFixed(2)}</span>
                <span class="label">Sharpe</span>
            </div>
            <div class="metric">
                <span class="value">${(run.max_drawdown || 0).toFixed(2)}%</span>
                <span class="label">Max DD</span>
            </div>
            <div class="metric">
                <span class="value">${run.num_trades || 0}</span>
                <span class="label">Trades</span>
            </div>
        </div>
    `).join('');
    
    leaderboard.innerHTML = leaderboardHTML || '<p>No paper trading sessions yet</p>';
}

/**
 * Load contest data and render contest UI
 */
async function loadContestData() {
    console.log('Loading contest data (using static data)...');
    
    // For now, use the static contest data defined in the script
    // When real contest data is available via API, fetch it here
    
    // Generate mock contest equity curves
    generateMockContestData();
    
    // Plot contest teams
    plotContestTeams();
    
    // Update leaderboard
    updateContestLeaderboard();
    
    // Update metrics table
    updateContestMetricsTable();
}

/**
 * Generate mock contest data with equity curves
 */
function generateMockContestData() {
    const baseDate = new Date(2026, 3, 20); // April 20, 2026
    
    contestData.teams.forEach((team, teamIdx) => {
        const equityCurve = [];
        let equity = 100000;
        
        // Generate 12 days of data (April 20 - May 1)
        for (let i = 0; i < 12; i++) {
            const date = new Date(baseDate);
            date.setDate(date.getDate() + i);
            
            // Each team has different returns
            const drift = [0.0008, 0.0006, 0.0012][teamIdx];
            const volatility = [0.018, 0.021, 0.023][teamIdx];
            const dailyReturn = drift + volatility * (Math.random() - 0.5);
            equity *= (1 + dailyReturn);
            
            equityCurve.push({
                timestamp: date.toISOString().split('T')[0],
                equity: Math.round(equity * 100) / 100,
                cash: equity * 0.3,
                positions_value: equity * 0.7,
                daily_return: dailyReturn
            });
        }
        
        team.equityCurve = equityCurve;
    });
}

/**
 * Plot contest teams (normalized to $100k start)
 */
function plotContestTeams() {
    const ctx = document.getElementById('equityChart');
    if (!ctx) return;
    
    const colors = ['#27ae60', '#4a90e2', '#e67e22'];
    
    const datasets = contestData.teams.map((team, index) => {
        // Normalize each team to start at $100k for fair comparison
        const normalized = normalizeEquityCurve(team.equityCurve);
        
        return {
            label: team.teamName,
            data: normalized.map(point => ({
                x: new Date(point.timestamp).getTime(),
                y: point.equity
            })),
            borderColor: colors[index % colors.length],
            backgroundColor: colors[index % colors.length] + '20',
            borderWidth: 2.5,
            tension: 0.4,
            fill: false,
            pointRadius: 2,
            pointHoverRadius: 6
        };
    });
    
    if (chartInstance) {
        chartInstance.destroy();
    }
    
    chartInstance = new Chart(ctx, {
        type: 'line',
        data: { datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        usePointStyle: true,
                        padding: 15,
                        font: { size: 13, weight: '600' }
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(0,0,0,0.8)',
                    padding: 12,
                    titleFont: { size: 13, weight: '600' },
                    bodyFont: { size: 12 },
                    callbacks: {
                        label: function(context) {
                            return context.dataset.label + ': $' + context.parsed.y.toFixed(2);
                        }
                    }
                }
            },
            scales: {
                x: {
                    type: 'linear',
                    ticks: {
                        callback: function(value) {
                            return new Date(value).toLocaleDateString();
                        },
                        maxTicksLimit: 6
                    }
                },
                y: {
                    ticks: {
                        callback: function(value) {
                            return '$' + value.toFixed(0);
                        }
                    }
                }
            }
        }
    });
    
    console.log('Contest teams chart rendered');
}

/**
 * Update contest leaderboard
 */
function updateContestLeaderboard() {
    const leaderboardList = document.getElementById('leaderboardList');
    
    // Sort teams by CR (cumulative return)
    const sortedTeams = [...contestData.teams].sort((a, b) => b.cr - a.cr);
    
    leaderboardList.innerHTML = sortedTeams.map((team, idx) => `
        <div class="leaderboard-item rank-${idx + 1}">
            <div class="rank">${idx + 1}.</div>
            <div class="name">${team.teamName}</div>
            <div class="return" style="color: ${team.cr >= 0 ? '#27ae60' : '#e74c3c'}">
                ${team.cr > 0 ? '+' : ''}${team.cr.toFixed(2)}%
            </div>
        </div>
    `).join('');
}

/**
 * Update contest metrics table
 */
function updateContestMetricsTable() {
    const body = document.getElementById('contestMetricsBody');
    
    // Sort teams by CR
    const sortedTeams = [...contestData.teams].sort((a, b) => b.cr - a.cr);
    
    body.innerHTML = sortedTeams.map((team, idx) => `
        <tr>
            <td class="rank-cell">${idx + 1}. ${team.teamName}</td>
            <td style="color: ${team.cr >= 0 ? '#27ae60' : '#e74c3c'}; font-weight: 700">
                ${team.cr > 0 ? '+' : ''}${team.cr.toFixed(2)}
            </td>
            <td>${team.sr.toFixed(2)}</td>
            <td class="negative">${team.md.toFixed(2)}</td>
            <td>${team.dv.toFixed(2)}</td>
            <td>${team.av.toFixed(2)}</td>
            <td style="font-weight: 700">$${team.finalEquity.toLocaleString()}</td>
        </tr>
    `).join('');
}

/**
 * Fetch and plot multiple runs
 */
async function plotRuns(runIds) {
    try {
        const query = runIds.join(',');
        const response = await fetch(`${API_BASE}/compare?run_ids=${query}`);
        
        if (!response.ok) {
            console.error('Failed to fetch comparison');
            return;
        }
        
        const data = await response.json();
        renderChart(data.runs);
    } catch (error) {
        console.error('Error plotting runs:', error);
    }
}

/**
 * Render equity chart (with normalization for fair comparison)
 */
function renderChart(runs) {
    const ctx = document.getElementById('equityChart');
    if (!ctx) return;
    
    const colors = ['#27ae60', '#4a90e2', '#e67e22'];
    
    // Convert timestamps to continuous trading hour indices
    let allTimestamps = [];
    runs.forEach(run => {
        run.data.forEach(point => {
            allTimestamps.push(point.timestamp);
        });
    });
    allTimestamps = [...new Set(allTimestamps)].sort();
    
    const timestampToIndex = {};
    allTimestamps.forEach((ts, idx) => {
        timestampToIndex[ts] = idx;
    });
    
    // Store data for axis labels
    window.chartDataForLabels = allTimestamps.map(ts => ({timestamp: ts}));
    
    const datasets = runs.map((run, index) => {
        // Normalize each run to start at $100k for fair comparison
        const normalized = normalizeEquityCurve(run.data);
        const data = normalized.map(point => ({
            x: timestampToIndex[point.timestamp],
            y: point.equity,
            timestamp: point.timestamp
        }));
        
        return {
            label: run.agent_name,
            data: data,
            borderColor: colors[index % colors.length],
            backgroundColor: colors[index % colors.length] + '20',
            borderWidth: 2.5,
            tension: 0.4,
            fill: false,
            pointRadius: 0,
            pointHoverRadius: 6
        };
    });
    
    if (chartInstance) {
        chartInstance.destroy();
    }
    
    chartInstance = new Chart(ctx, {
        type: 'line',
        data: { datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        usePointStyle: true,
                        padding: 15,
                        font: { size: 13, weight: '600' }
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(0,0,0,0.8)',
                    padding: 12,
                    titleFont: { size: 13, weight: '600' },
                    bodyFont: { size: 12 },
                    callbacks: {
                        label: function(context) {
                            return context.dataset.label + ': $' + context.parsed.y.toFixed(2);
                        },
                        afterLabel: function(context) {
                            // Show actual timestamp in tooltip
                            if (context.raw && context.raw.timestamp) {
                                const date = new Date(context.raw.timestamp);
                                return 'Time: ' + date.toLocaleString();
                            }
                            return '';
                        }
                    }
                }
            },
            scales: {
                x: {
                    type: 'linear',
                    ticks: {
                        callback: function(value) {
                            // Get the actual date from the data
                            if (window.chartDataForLabels && window.chartDataForLabels[Math.floor(value)]) {
                                const point = window.chartDataForLabels[Math.floor(value)];
                                const date = new Date(point.timestamp);
                                return date.toLocaleDateString('en-US', { month: 'short', day: '2-digit' });
                            }
                            return '';
                        },
                        maxTicksLimit: 10
                    }
                },
                y: {
                    ticks: {
                        callback: function(value) {
                            return '$' + value.toFixed(0);
                        }
                    }
                }
            }
        }
    });
    
    console.log('Chart rendered');
}

/**
 * Load mock data if API is unavailable
 */
function loadMockData() {
    console.log('Loading mock data...');
    
    // Hide loading message
    const tickerBar = document.getElementById('tickerBar');
    if (tickerBar) {
        tickerBar.innerHTML = '';  // Clear placeholder
    }
    
    const agents = [
        { name: 'DeepSeek', color: '#27ae60' },
        { name: 'Claude', color: '#4a90e2' },
        { name: 'GPT', color: '#e67e22' }
    ];
    
    const ctx = document.getElementById('equityChart');
    if (!ctx) return;
    
    const baseDate = new Date();
    baseDate.setDate(baseDate.getDate() - 30);
    
    const datasets = agents.map((agent, agentIdx) => {
        const data = [];
        let equity = 100000;
        
        for (let i = 0; i < 30; i++) {
            const date = new Date(baseDate);
            date.setDate(date.getDate() + i);
            
            const drift = 0.0003 * (agentIdx + 1);
            const volatility = 0.015;
            const dailyReturn = drift + volatility * (Math.random() - 0.5);
            equity *= (1 + dailyReturn);
            
            data.push({
                x: date.getTime(),
                y: Math.round(equity * 100) / 100
            });
        }
        
        return {
            label: agent.name,
            data: data,
            borderColor: agent.color,
            backgroundColor: agent.color + '20',
            borderWidth: 2.5,
            tension: 0.4,
            fill: false,
            pointRadius: 0,
            pointHoverRadius: 6
        };
    });
    
    if (chartInstance) {
        chartInstance.destroy();
    }
    
    chartInstance = new Chart(ctx, {
        type: 'line',
        data: { datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        usePointStyle: true,
                        padding: 15,
                        font: { size: 13, weight: '600' }
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(0,0,0,0.8)',
                    padding: 12,
                    titleFont: { size: 13, weight: '600' },
                    bodyFont: { size: 12 }
                }
            },
            scales: {
                x: {
                    type: 'linear',
                    ticks: {
                        callback: function(value) {
                            return new Date(value).toLocaleDateString();
                        },
                        maxTicksLimit: 6
                    }
                },
                y: {
                    ticks: {
                        callback: function(value) {
                            return '$' + value.toFixed(0);
                        }
                    }
                }
            }
        }
    });
    
    console.log('Mock chart rendered');
}
